import frappe

def execute():
    if frappe.db.table_exists("Service Request") and frappe.db.has_column("Service Request", "assigned_at"):
        try:
            frappe.db.sql("""
                update `tabService Request`
                set assigned_at = creation
                where assigned_at is null
            """)
        except Exception:
            pass
