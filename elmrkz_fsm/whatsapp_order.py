import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from elmrkz_fsm.elmrkz_fsm.doctype.fsm_settings.fsm_settings import (
    validate_whatsapp_defaults,
)


@frappe.whitelist(allow_guest=True)
def ingest_whatsapp_order(*args, **kwargs):
    """
    Ingest a confirmed WhatsApp chatbot order payload.

    The endpoint validates the shared FSM Settings record before doing any
    customer or Sales Order writes. This prevents a malformed service fee,
    warehouse, company, or service item from producing a partial order.
    """
    payload = {}
    if args:
        for arg in args:
            if isinstance(arg, dict):
                payload.update(arg)
            elif isinstance(arg, str):
                try:
                    parsed = json.loads(arg)
                    if isinstance(parsed, dict):
                        payload.update(parsed)
                except Exception:
                    pass
    if kwargs:
        payload.update(kwargs)

    if not payload.get("items") and frappe.request and frappe.request.data:
        try:
            body_data = json.loads(frappe.request.data)
            if isinstance(body_data, dict):
                payload.update(body_data)
        except Exception:
            pass

    # Check API Secret from header or payload.
    req_secret = None
    if frappe.request:
        req_secret = frappe.request.headers.get("X-FSM-API-Secret")
    if not req_secret:
        req_secret = payload.get("secret")

    expected_secret = "elmrkz_bridge_secure_2026"
    if req_secret != expected_secret:
        frappe.throw(_("Invalid or missing API secret"), frappe.PermissionError)

    settings = frappe.get_single("FSM Settings")
    if not settings.get("enable_whatsapp_order_ingestion"):
        frappe.throw(_("WhatsApp Order Ingestion is disabled in FSM Settings"), frappe.ValidationError)

    validated_defaults = validate_whatsapp_defaults(settings)
    company = validated_defaults["company"]
    warehouse = validated_defaults["warehouse"]
    default_item_code = validated_defaults["item_code"]
    default_service_fee = validated_defaults["service_fee"]

    phone = payload.get("customer_phone") or "+201016761856"
    customer_name = payload.get("customer_name") or "Real WhatsApp User"
    items = payload.get("items") or [
        {
            "item_code": default_item_code,
            "qty": 1,
            "rate": default_service_fee,
        }
    ]
    address = payload.get("delivery_address") or "Cairo, Egypt"

    # 1. Resolve Customer by Phone.
    customer = None
    contact_name = frappe.db.get_value("Contact", {"phone": phone}, "name")
    if contact_name:
        contact = frappe.get_doc("Contact", contact_name)
        for link in contact.links:
            if link.link_doctype == "Customer":
                customer = link.link_name
                break

    if not customer:
        customer = frappe.db.get_value("Customer", {"mobile_no": phone}, "name")

    if not customer:
        cust_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "Rest of the World"
        cust = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_type": "Individual",
                "customer_group": cust_group,
                "territory": territory,
                "mobile_no": phone,
            }
        )
        cust.insert(ignore_permissions=True)
        customer = cust.name
        frappe.db.commit()

    price_list = settings.get("whatsapp_default_price_list")
    if not price_list:
        frappe.throw(_("Default Price List is required when WhatsApp Order Ingestion is enabled"), frappe.ValidationError)

    company_currency = frappe.get_cached_value("Company", company, "default_currency") or "EGP"
    currency = payload.get("currency") or settings.get("whatsapp_default_currency") or company_currency
    tax_template = settings.get("whatsapp_default_tax_template")
    payment_terms = settings.get("whatsapp_default_payment_terms")
    auto_submit = bool(settings.get("whatsapp_auto_submit_order"))

    so_items = []
    for item in items:
        code = item.get("item_code") or default_item_code
        if not frappe.db.exists("Item", code):
            frappe.throw(_("WhatsApp item {0} does not exist").format(code), frappe.ValidationError)

        qty = flt(item.get("qty") or 1)
        rate = flt(item.get("rate") or default_service_fee)
        if qty <= 0:
            frappe.throw(_("WhatsApp item quantity must be greater than zero"), frappe.ValidationError)
        if rate <= 0:
            frappe.throw(_("WhatsApp item rate must be greater than zero"), frappe.ValidationError)

        so_items.append(
            {
                "item_code": code,
                "qty": qty,
                "delivery_date": nowdate(),
                "warehouse": warehouse,
                "rate": rate,
                "price_list_rate": rate,
            }
        )

    unique_po = f"WA-{phone.replace('+', '')}-{now_datetime().strftime('%Y%m%d%H%M%S')}"

    so_doc = {
        "doctype": "Sales Order",
        "customer": customer,
        "company": company,
        "selling_price_list": price_list,
        "currency": currency,
        "conversion_rate": 1.0,
        "delivery_date": nowdate(),
        "items": so_items,
        "po_no": unique_po,
        "notes": (
            "Generated from WhatsApp Chatbot (LEAD_COMPLETION).\n"
            f"Phone: {phone}\n"
            f"Address: {address}\n"
            f"Location: {payload.get('location_link', '')}\n"
            f"Notes: {payload.get('notes', '')}"
        ),
    }

    if tax_template:
        so_doc["taxes_and_charges"] = tax_template
    if payment_terms:
        so_doc["payment_terms_template"] = payment_terms

    so = frappe.get_doc(so_doc)
    so.insert(ignore_permissions=True)

    if auto_submit:
        so.submit()

    frappe.db.commit()

    return {
        "status": "success",
        "sales_order": so.name,
        "docstatus": so.docstatus,
        "customer": customer,
        "total": so.grand_total,
        "currency": currency,
        "message": f"Sales Order {so.name} successfully created as {'Submitted' if so.docstatus == 1 else 'Draft'}.",
    }
