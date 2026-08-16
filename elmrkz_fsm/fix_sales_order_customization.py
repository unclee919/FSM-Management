import frappe

def fix():
    name='Sales Order-custom_is_maintenance_order'
    if not frappe.db.exists('Custom Field', name):
        frappe.get_doc({'doctype':'Custom Field','dt':'Sales Order','fieldname':'custom_is_maintenance_order','label':'Is Maintenance Order','fieldtype':'Check','default':0,'insert_after':'customer'}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype='Sales Order')
    frappe.db.commit()
    return {'custom_field':name,'exists':frappe.db.exists('Custom Field',name)}
