import frappe


def seed():
    fields = [
        ('Service Request', 'sales_order', 'Sales Order', 'Link', 'Sales Order', 'workflow_state'),
        ('Service Request', 'sales_invoice', 'Sales Invoice', 'Link', 'Sales Invoice', 'workflow_state'),
        ('Service Request', 'tracking_expires_at', 'Tracking Expires At', 'Datetime', None, 'workflow_state'),
        ('Service Request', 'payment_method', 'Payment Method', 'Select', 'Cash\nTransfer', 'workflow_state'),
        ('Service Request', 'inspection_fee', 'Inspection Fee', 'Currency', None, 'workflow_state'),
        ('Service Request', 'labor_rate', 'Labor Rate', 'Currency', None, 'workflow_state'),
        ('Service Request', 'cash_collected', 'Cash Collected', 'Currency', None, 'workflow_state'),
        ('Service Request', 'transfer_payment_proof', 'Transfer Payment Proof', 'Attach', None, 'payment_method'),
        ('Service Request', 'completion_total', 'Completion Total', 'Currency', None, 'transfer_payment_proof'),
        ('Service Request', 'completion_submitted_at', 'Completion Submitted At', 'Datetime', None, 'completion_total'),
        ('Service Request', 'spare_part_request_status', 'Spare Part Request Status', 'Select', 'None\nPending Approval\nApproved\nRejected\nCompleted', 'parts'),
        ('FSM Settings', 'default_service_item', 'Default Service Item', 'Link', 'Item', None),
        ('Sales Order Item', 'custom_device_name', 'Device Name', 'Data', None, 'description'),
        ('Sales Order Item', 'custom_failure_reason', 'Failure Reason', 'Data', None, 'custom_device_name'),
        ('Sales Order Item', 'custom_brand', 'Brand', 'Data', None, 'custom_failure_reason'),
    ]
    created = 0
    for dt, fieldname, label, fieldtype, options, insert_after in fields:
        name = f'{dt}-{fieldname}'
        if frappe.db.exists('Custom Field', name):
            existing = frappe.get_doc('Custom Field', name)
            if existing.module != 'Elmrkz Fsm':
                existing.module = 'Elmrkz Fsm'
                existing.save(ignore_permissions=True)
            continue
        doc = {
            'doctype': 'Custom Field',
            'dt': dt,
            'module': 'Elmrkz Fsm',
            'fieldname': fieldname,
            'label': label,
            'fieldtype': fieldtype,
            'insert_after': insert_after or 'item_name',
            'in_list_view': 1 if dt == 'Sales Order Item' else 0,
            'columns': 4 if dt == 'Sales Order Item' else 0,
        }
        if options:
            doc['options'] = options
        frappe.get_doc(doc).insert(ignore_permissions=True)
        created += 1
    payment_field_name = 'Service Request-payment_method'
    if frappe.db.exists('Custom Field', payment_field_name):
        payment_field = frappe.get_doc('Custom Field', payment_field_name)
        changed = False
        if payment_field.options != 'Cash\nTransfer':
            payment_field.options = 'Cash\nTransfer'
            changed = True
        if payment_field.module != 'Elmrkz Fsm':
            payment_field.module = 'Elmrkz Fsm'
            changed = True
        if changed:
            payment_field.save(ignore_permissions=True)
    frappe.db.commit()
    return {'created': created}


def execute():
    return seed()


if __name__ == '__main__':
    seed()

