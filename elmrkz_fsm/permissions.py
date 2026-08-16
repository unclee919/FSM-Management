import frappe


def _is_manager(user):
    user = user or frappe.session.user
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & {"System Manager", "FSM Manager", "Service Manager"})


def _profile_name(user):
    return frappe.db.get_value("Technician Profile", {"user": user}, "name")


def service_request_query(user=None, doctype=None):
    user = user or frappe.session.user
    if _is_manager(user):
        return "1=1"
    profile = _profile_name(user)
    if not profile:
        return "1=0"
    profile_sql = frappe.db.escape(profile)
    return (
        f"(`tabService Request`.assigned_technician={profile_sql} "
        f"OR `tabService Request`.name IN ("
        "SELECT parent FROM `tabService Request Item` "
        "WHERE parenttype='Service Request' AND row_assigned_technician="
        f"{profile_sql}))"
    )


def service_request_has_permission(doc, ptype="read", user=None, debug=False):
    user = user or frappe.session.user
    if _is_manager(user):
        return True
    profile = _profile_name(user)
    if not profile:
        return False
    if doc is None:
        return ptype in {"read", "print"}
    if ptype in {"read", "print"}:
        return doc.assigned_technician == profile or any(
            row.row_assigned_technician == profile for row in (doc.items or [])
        )
    if ptype == "write":
        return doc.assigned_technician == profile or any(
            row.row_assigned_technician == profile for row in (doc.items or [])
        )
    return False


def technician_profile_query(user=None, doctype=None):
    user = user or frappe.session.user
    if _is_manager(user):
        return "1=1"
    profile = _profile_name(user)
    return f"name={frappe.db.escape(profile)}" if profile else "1=0"


def technician_profile_has_permission(doc, ptype="read", user=None, debug=False):
    user = user or frappe.session.user
    if _is_manager(user):
        return True
    profile = _profile_name(user)
    if not profile:
        return False
    if doc is None:
        return ptype in {"read", "print"}
    return doc.name == profile and ptype in {"read", "write", "print"}
