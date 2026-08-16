import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = [
        {"fieldname": "assigned_technician", "label": _("Technician"), "fieldtype": "Link", "options": "Technician Profile", "width": 180},
        {"fieldname": "total_requests", "label": _("Total Requests"), "fieldtype": "Int", "width": 110},
        {"fieldname": "active_requests", "label": _("Active Requests"), "fieldtype": "Int", "width": 115},
        {"fieldname": "completed_requests", "label": _("Completed"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cancelled_requests", "label": _("Cancelled"), "fieldtype": "Int", "width": 100},
        {"fieldname": "last_activity", "label": _("Last Activity"), "fieldtype": "Datetime", "width": 155},
    ]
    conditions = ["sr.docstatus < 2", "sr.assigned_technician is not null", "sr.assigned_technician != ''"]
    values = {}
    if filters.from_date:
        conditions.append("sr.scheduled_date >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("sr.scheduled_date <= %(to_date)s")
        values["to_date"] = filters.to_date
    if filters.territory:
        conditions.append("sr.territory = %(territory)s")
        values["territory"] = filters.territory
    if filters.assigned_technician:
        conditions.append("sr.assigned_technician = %(assigned_technician)s")
        values["assigned_technician"] = filters.assigned_technician

    data = frappe.db.sql(
        f"""
        select
            sr.assigned_technician,
            count(sr.name) as total_requests,
            sum(case when sr.workflow_state not in ('Completed', 'Cancelled', 'Delivered') then 1 else 0 end) as active_requests,
            sum(case when sr.workflow_state = 'Completed' then 1 else 0 end) as completed_requests,
            sum(case when sr.workflow_state = 'Cancelled' then 1 else 0 end) as cancelled_requests,
            max(sr.modified) as last_activity
        from `tabService Request` sr
        where {' and '.join(conditions)}
        group by sr.assigned_technician
        order by active_requests desc, last_activity desc
        """,
        values,
        as_dict=True,
    )
    return columns, data
