import frappe


def _reference_names(service_request):
    refs = [("Service Request", service_request.name)]
    sales_order = getattr(service_request, "sales_order", None)
    if sales_order:
        refs.append(("Sales Order", sales_order))
    return refs


def sync_standard_assignees(service_request, technician_profile_name):
    """Create standard Frappe ToDo assignments for the approved technician."""
    user = frappe.db.get_value("Technician Profile", technician_profile_name, "user")
    if not user or user in {"Guest", "Administrator"}:
        return {"user": user, "created": 0}

    created = 0
    for reference_type, reference_name in _reference_names(service_request):
        exists = frappe.db.exists(
            "ToDo",
            {
                "allocated_to": user,
                "reference_type": reference_type,
                "reference_name": reference_name,
                "status": "Open",
            },
        )
        if exists:
            continue
        frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": user,
                "reference_type": reference_type,
                "reference_name": reference_name,
                "status": "Open",
                "priority": "Medium",
                "description": f"FSM assignment approved for {service_request.name}",
                "assigned_by": frappe.session.user if frappe.session.user != "Guest" else None,
            }
        ).insert(ignore_permissions=True)
        created += 1
    return {"user": user, "created": created}


def remove_standard_assignees(service_request, technician_profile_name=None):
    """Close FSM ToDos for this request when it is rejected or reassigned."""
    user = None
    if technician_profile_name:
        user = frappe.db.get_value("Technician Profile", technician_profile_name, "user")
    for reference_type, reference_name in _reference_names(service_request):
        filters = {
            "reference_type": reference_type,
            "reference_name": reference_name,
            "status": "Open",
        }
        if user:
            filters["allocated_to"] = user
        todos = frappe.get_all("ToDo", filters=filters, fields=["name", "description"])
        for todo in todos:
            if not (todo.description or "").startswith("FSM assignment"):
                continue
            frappe.db.set_value("ToDo", todo.name, "status", "Closed")
    return True
