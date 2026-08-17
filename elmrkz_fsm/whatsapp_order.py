import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, flt
import json

@frappe.whitelist(allow_guest=True)
def ingest_whatsapp_order(**kwargs):
    payload = frappe.local.form_dict or frappe.request.get_json() or kwargs
    req_secret = frappe.get_request_header('X-FSM-API-Secret') or payload.get('secret')
    if req_secret != 'elmrkz_bridge_secure_2026':
        frappe.throw(_('Invalid or missing API secret'), frappe.PermissionError)
    
    settings = frappe.get_single('FSM Settings')
    if not settings.get('enable_whatsapp_order_ingestion'):
        frappe.throw(_('WhatsApp Order Ingestion is disabled in FSM Settings'), frappe.ValidationError)
    
    company = settings.get('whatsapp_default_company')
    warehouse = settings.get('whatsapp_default_warehouse')
    default_item_code = settings.get('whatsapp_default_item') or 'FSM Service Visit'
    default_service_fee = flt(settings.get('whatsapp_default_service_fee') or 250.0)
    
    if not company or not warehouse:
        frappe.throw(_('Default Company and Warehouse must be configured in FSM Settings'), frappe.ValidationError)
        
    phone = (payload.get('customer_phone') or '+201016761856').strip()
    clean_phone = ''.join([c for c in phone if c.isdigit() or c == '+'])
    customer_name = payload.get('customer_name') or 'WhatsApp Customer'
    delivery_address = payload.get('delivery_address') or 'Cairo, Egypt'
    delivery_date = payload.get('delivery_date') or nowdate()
    delivery_time = payload.get('delivery_time') or ''
    territory = payload.get('territory') or 'Cairo'
    location_link = payload.get('location_link') or payload.get('map_link') or ''
    latitude = flt(payload.get('latitude') or 0.0)
    longitude = flt(payload.get('longitude') or 0.0)
    
    issues = payload.get('issues') or payload.get('items') or [
        {
            'item_code': default_item_code,
            'device': payload.get('device') or 'General Appliance',
            'brand': payload.get('brand') or '',
            'failure_reason': payload.get('failure_reason') or payload.get('notes') or 'Standard Service Request',
            'qty': 1,
            'rate': default_service_fee,
            'attachments': payload.get('attachments') or []
        }
    ]
    
    frappe.set_user('Administrator')
    
    # 1. Customer & Contact Upsert
    customer = None
    contact_name = frappe.db.get_value('Contact', {'phone': clean_phone}, 'name') or frappe.db.get_value('Contact', {'mobile_no': clean_phone}, 'name')
    if contact_name:
        contact = frappe.get_doc('Contact', contact_name)
        for link in contact.links:
            if link.link_doctype == 'Customer':
                customer = link.link_name
                break
                
    if not customer:
        customer = frappe.db.get_value('Customer', {'mobile_no': clean_phone}, 'name') or frappe.db.get_value('Customer', {'customer_primary_contact': contact_name}, 'name')
        
    if not customer:
        cust_group = frappe.db.get_value('Customer Group', {'is_group': 0}, 'name') or 'Commercial'
        terr = frappe.db.get_value('Territory', {'name': territory}, 'name') or 'Cairo'
        cust = frappe.get_doc({
            'doctype': 'Customer',
            'customer_name': customer_name,
            'customer_type': 'Individual',
            'customer_group': cust_group,
            'territory': terr,
            'mobile_no': clean_phone
        })
        cust.insert(ignore_permissions=True)
        customer = cust.name
        
    if not contact_name:
        contact = frappe.get_doc({
            'doctype': 'Contact',
            'first_name': customer_name,
            'phone': clean_phone,
            'mobile_no': clean_phone,
            'links': [{'link_doctype': 'Customer', 'link_name': customer}]
        })
        contact.insert(ignore_permissions=True)
        
    # 2. Address Upsert
    address_name = None
    existing_addresses = frappe.get_all('Dynamic Link', {'link_doctype': 'Customer', 'link_name': customer, 'parenttype': 'Address'}, ['parent'])
    if existing_addresses:
        address_name = existing_addresses[0].parent
    else:
        addr = frappe.get_doc({
            'doctype': 'Address',
            'address_title': customer_name + ' Address',
            'address_type': 'Billing',
            'address_line1': delivery_address,
            'city': 'Cairo',
            'country': 'Egypt',
            'links': [{'link_doctype': 'Customer', 'link_name': customer}]
        })
        addr.insert(ignore_permissions=True)
        address_name = addr.name
        
    ts_str = now_datetime().strftime('%Y%m%d%H%M%S')
    unique_po = 'WA-' + clean_phone + '-' + ts_str
    
    so_items = []
    sr_items = []
    all_attachments = []
    
    item_meta = frappe.get_meta('Sales Order Item')
    
    for issue in issues:
        code = issue.get('item_code') or default_item_code
        if not frappe.db.exists('Item', code):
            code = default_item_code
            
        qty = flt(issue.get('qty') or 1)
        rate = flt(issue.get('rate') or default_service_fee)
        device = issue.get('device') or 'Appliance'
        brand = issue.get('brand') or ''
        failure = issue.get('failure_reason') or issue.get('notes') or 'Service Request'
        
        desc = 'Device: ' + device + ' | Brand: ' + brand + ' | Issue: ' + failure
        
        row = {
            'item_code': code,
            'qty': qty,
            'delivery_date': delivery_date,
            'warehouse': warehouse,
            'rate': rate,
            'price_list_rate': rate,
            'description': desc
        }
        
        if item_meta.has_field('device_name'):
            row['device_name'] = device
        if item_meta.has_field('failure_reason'):
            row['failure_reason'] = failure
            
        so_items.append(row)
        sr_items.append({
            'item_code': code,
            'item_name': device + ' - ' + brand,
            'description': failure,
            'qty': qty,
            'rate': rate
        })
        
        if issue.get('attachments'):
            all_attachments.extend(issue.get('attachments'))
            
    if payload.get('attachments'):
        all_attachments.extend(payload.get('attachments'))
        
    price_list = settings.get('whatsapp_default_price_list') or 'Standard Selling'
    currency = payload.get('currency') or settings.get('whatsapp_default_currency') or 'EGP'
    
    notes_lines = ['WhatsApp Order', 'Phone: ' + phone, 'Address: ' + delivery_address, 'Delivery Time: ' + delivery_time, 'Notes: ' + str(payload.get('notes', ''))]
    if all_attachments:
        notes_lines.append('Attachments: ' + json.dumps(all_attachments))
    notes_text = chr(10).join(notes_lines)
        
    # 3. Create Sales Order with custom FSM address, contact, and delivery time fields
    so_doc = {
        'doctype': 'Sales Order',
        'customer': customer,
        'company': company,
        'selling_price_list': price_list,
        'currency': currency,
        'conversion_rate': 1.0,
        'delivery_date': delivery_date,
        'items': so_items,
        'po_no': unique_po,
        'notes': notes_text,
        'custom_customer_phone': clean_phone,
        'custom_service_address': delivery_address,
        'custom_territory': territory if frappe.db.exists('Territory', territory) else 'Cairo',
        'custom_location_link': location_link,
        'custom_latitude': latitude,
        'custom_longitude': longitude,
        'custom_delivery_time': delivery_time
    }
    
    so = frappe.get_doc(so_doc)
    so.flags.ignore_permissions = True
    so.flags.ignore_mandatory = True
    so.customer_address = address_name
    so.shipping_address_name = address_name
    
    so.insert(ignore_permissions=True)
    
    for att in all_attachments:
        if isinstance(att, dict) and att.get('file_url'):
            try:
                file_url = att.get('file_url')
                frappe.get_doc({
                    'doctype': 'File',
                    'file_url': file_url,
                    'file_name': att.get('file_name') or 'whatsapp_media',
                    'attached_to_doctype': 'Sales Order',
                    'attached_to_name': so.name,
                    'is_private': 0
                }).insert(ignore_permissions=True)
            except Exception:
                pass
                
    if settings.get('whatsapp_auto_submit_order'):
        try:
            so.submit()
        except Exception:
            pass
            
    # 4. Create Service Request (FSM Module)
    sr_name = None
    if frappe.db.exists('DocType', 'Service Request'):
        try:
            sr_doc = {
                'doctype': 'Service Request',
                'customer': customer,
                'customer_name': customer_name,
                'primary_phone': clean_phone,
                'detailed_address': delivery_address,
                'territory': territory if frappe.db.exists('Territory', territory) else 'Cairo',
                'location_link': location_link,
                'latitude': latitude,
                'longitude': longitude,
                'scheduled_date': delivery_date,
                'scheduled_time': delivery_time or '10:00:00',
                'sales_order': so.name,
                'items': sr_items
            }
            if all_attachments and len(all_attachments) > 0 and isinstance(all_attachments[0], dict):
                sr_doc['attachment_media'] = all_attachments[0].get('file_url')
                
            sr = frappe.get_doc(sr_doc)
            sr.flags.ignore_permissions = True
            sr.flags.ignore_mandatory = True
            sr.insert(ignore_permissions=True)
            sr_name = sr.name
        except Exception as e:
            frappe.log_error(title='WhatsApp Service Request Creation Error', message=str(e))
            
    frappe.db.commit()
    return {
        'status': 'success',
        'sales_order': so.name,
        'service_request': sr_name,
        'docstatus': so.docstatus,
        'customer': customer,
        'address': address_name,
        'total': so.grand_total,
        'items_count': len(so_items),
        'message': 'Sales Order ' + so.name + ' and Service Request ' + (sr_name or 'N/A') + ' successfully created with delivery time.'
    }
