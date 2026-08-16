import re
import frappe
from frappe import _
from .assignment import assign_service_request

def _authorized():
    expected = frappe.conf.get("fsm_api_secret")
    supplied = frappe.get_request_header("X-FSM-API-Secret")
    return bool(expected and supplied and supplied == expected)

def _coords(link):
    if not link:
        return None, None
    # Matches decimal coordinates in a Google Maps link or similar.
    m = re.search(r"([-+]?\d{1,3}\.\d+)[, ]+([-+]?\d{1,3}\.\d+)", str(link))
    if not m:
        return None, None
    latitude, longitude = float(m.group(1)), float(m.group(2))
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        frappe.throw(_("Location link contains invalid latitude or longitude"), frappe.ValidationError)
    return latitude, longitude

@frappe.whitelist(allow_guest=True)
def create_service_request(**payload):
    if not _authorized():
        frappe.throw(_("Invalid API secret"), frappe.PermissionError)
    
    latitude, longitude = _coords(payload.get("location_link"))
    if latitude is not None:
        payload["latitude"], payload["longitude"] = latitude, longitude
        
    doc = frappe.get_doc({"doctype": "Service Request", **payload})
    doc.workflow_state = "New"
    doc.insert(ignore_permissions=True)
    
    if doc.assigned_technician is None:
        result = assign_service_request(doc)
        doc.workflow_state = "Assigned" if result else (doc.workflow_state or "Queued")
        doc.save(ignore_permissions=True)
    elif doc.workflow_state == "New":
        doc.workflow_state = "Assigned"
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    return {"name": doc.name, "workflow_state": doc.workflow_state, "assigned_technician": doc.assigned_technician}


@frappe.whitelist()
def get_health_summary():
    """Verify operational health metrics programmatically."""
    from elmrkz_fsm.elmrkz_fsm.report.fsm_operations_health.fsm_operations_health import execute as execute_health
    columns, data = execute_health()
    return {"columns": columns, "data": data}

