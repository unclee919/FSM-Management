import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = [
        {"fieldname": "name", "label": _("Service Request"), "fieldtype": "Link", "options": "Service Request", "width": 150},
        {"fieldname": "workflow_state", "label": _("Workflow State"), "fieldtype": "Data", "width": 130},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "territory", "label": _("Territory"), "fieldtype": "Link", "options": "Territory", "width": 130},
        {"fieldname": "assigned_technician", "label": _("Assigned Technician"), "fieldtype": "Link", "options": "Technician Profile", "width": 160},
        {"fieldname": "scheduled_datetime", "label": _("Scheduled For"), "fieldtype": "Datetime", "width": 155},
        {"fieldname": "primary_phone", "label": _("Primary Phone"), "fieldtype": "Data", "width": 130},
        {"fieldname": "modified", "label": _("Last Updated"), "fieldtype": "Datetime", "width": 155},
    ]
    query_filters = {}
    if filters.from_date:
        query_filters["scheduled_date"] = [">=", filters.from_date]
    if filters.to_date:
        query_filters.setdefault("scheduled_date", ["between", [filters.from_date or "1900-01-01", filters.to_date]])
        if not filters.from_date:
            query_filters["scheduled_date"] = ["<=", filters.to_date]
    for fieldname in ("workflow_state", "assigned_technician", "territory"):
        if filters.get(fieldname):
            query_filters[fieldname] = filters[fieldname]

    data = frappe.get_list(
        "Service Request",
        filters=query_filters,
        fields=[column["fieldname"] for column in columns],
        order_by="scheduled_datetime asc, modified desc",
        limit_page_length=1000,
    )
    return columns, data
