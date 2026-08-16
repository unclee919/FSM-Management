import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def add_calendar_support():
    # 1. Add scheduled_datetime field
    if not frappe.db.exists("Custom Field", "Service Request-scheduled_datetime"):
        create_custom_field("Service Request", {
            "fieldname": "scheduled_datetime",
            "label": "Scheduled Datetime",
            "fieldtype": "Datetime",
            "insert_after": "scheduled_time",
            "read_only": 1,
            "hidden": 1
        })
        print("Added scheduled_datetime field to Service Request")

    # 2. Sync existing records
    frappe.db.sql("""
        UPDATE `tabService Request`
        SET scheduled_datetime = CONCAT(scheduled_date, ' ', COALESCE(scheduled_time, '00:00:00'))
        WHERE scheduled_date IS NOT NULL
    """)
    print("Synced existing Service Request records")

    # 3. Create Calendar View
    if not frappe.db.exists("Calendar View", "Service Request Calendar"):
        doc = frappe.get_doc({
            "doctype": "Calendar View",
            "name": "Service Request Calendar",
            "reference_doctype": "Service Request",
            "start_date_field": "scheduled_datetime",
            "end_date_field": "scheduled_datetime",
            "subject_field": "customer_name"
        })
        doc.insert(ignore_permissions=True)
        print("Created Service Request Calendar View")
    else:
        doc = frappe.get_doc("Calendar View", "Service Request Calendar")
        doc.start_date_field = "scheduled_datetime"
        doc.end_date_field = "scheduled_datetime"
        doc.save(ignore_permissions=True)
        print("Updated Service Request Calendar View")

    frappe.db.commit()

if __name__ == "__main__":
    add_calendar_support()
