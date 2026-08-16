import frappe

def execute():
    # Backfill missing assigned_at timestamps for historical assigned/scheduled/dispatched/in progress requests using creation time
    frappe.db.sql("""
        update `tabService Request`
        set assigned_at = creation
        where workflow_state in ('Assigned', 'Scheduled', 'Dispatched', 'In Progress')
          and (assigned_at is null or assigned_at = '')
    """)
    frappe.db.commit()
