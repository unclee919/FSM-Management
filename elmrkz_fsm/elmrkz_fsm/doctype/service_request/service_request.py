import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate, nowdate

class ServiceRequest(Document):
    def validate(self):
        # Normalize legacy labels before Frappe validates the Select field.
        # Older test and imported requests may still contain Cash on Hand.
        _normalize_payment_method(self)
        for row in self.parts or []:
            row.amount = (row.qty or 0) * (row.rate or 0)
            
        # Ensure scheduled_datetime is always populated automatically
        if not self.scheduled_date:
            self.scheduled_date = nowdate()
        if not self.scheduled_time:
            self.scheduled_time = "09:00:00"
        self.scheduled_datetime = f"{self.scheduled_date} {self.scheduled_time}"

def _normalize_payment_method(doc):
    """Normalize legacy labels before a Service Request save validates Select fields."""
    if not doc.meta.has_field("payment_method") or not doc.payment_method:
        return
    raw = " ".join(str(doc.payment_method).replace("_", " ").replace("-", " ").split()).casefold()
    aliases = {
        "cash": "Cash",
        "cash on hand": "Cash",
        "cash collected": "Cash",
        "online cash": "Transfer",
        "transfer": "Transfer",
        "bank transfer": "Transfer",
        "online transfer": "Transfer",
    }
    normalized = aliases.get(raw)
    if normalized:
        doc.payment_method = normalized

def _get_assigned_technician_for_session(doc):
    technician = frappe.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    assigned_to_item = any(
        row.row_assigned_technician == technician for row in (doc.items or [])
    )
    if not technician or (doc.assigned_technician != technician and not assigned_to_item):
        frappe.throw("You are not authorized to act on this assignment.", frappe.PermissionError)
    return technician

def _technician_owns_request(doc, technician):
    return doc.assigned_technician == technician or any(
        row.row_assigned_technician == technician for row in (doc.items or [])
    )

def _valid_coordinate_pair(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (TypeError, ValueError):
        return False

def _append_action_location(doc, action, technician_name, latitude=None, longitude=None):
    """Append a schema-valid, immutable technician-action location record."""
    if not doc.meta.has_field("action_locations"):
        return
    if not _valid_coordinate_pair(latitude, longitude):
        profile = frappe.db.get_value(
            "Technician Profile",
            technician_name,
            ["current_latitude", "current_longitude"],
            as_dict=True,
        ) or {}
        latitude = profile.get("current_latitude")
        longitude = profile.get("current_longitude")
    if not _valid_coordinate_pair(latitude, longitude):
        return
    latitude, longitude = float(latitude), float(longitude)
    previous = (doc.action_locations or [])[-1] if doc.action_locations else None
    timestamp = now_datetime()
    elapsed_minutes = None
    if previous and previous.timestamp:
        elapsed_minutes = round(
            (timestamp - frappe.utils.get_datetime(previous.timestamp)).total_seconds() / 60.0,
            2,
        )
    doc.append("action_locations", {
        "action": action,
        "technician": technician_name,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": timestamp,
        "google_maps_link": f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}",
        "elapsed_minutes": elapsed_minutes,
    })

@frappe.whitelist()
def get_pending_assignments():
    """Return unaccepted assignments for the logged-in technician as a realtime fallback."""
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    if not technician:
        return []
    from elmrkz_fsm.assignment import _assignment_message
    requests = frappe.get_all(
        "Service Request",
        filters={"workflow_state": "Assigned"},
        fields=["name"],
        order_by="creation asc",
        limit_page_length=50,
    )
    pending = []
    for row in requests:
        doc = frappe.get_doc("Service Request", row.name)
        if not _technician_owns_request(doc, technician):
            continue
        selected_items = [
            {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "device_name": item.device_name,
                "failure_reason": item.failure_reason,
                "brand": getattr(item, "brand", None),
                "initial_rate": item.initial_rate,
                "row_assigned_technician": item.row_assigned_technician,
            }
            for item in (doc.items or [])
            if item.row_assigned_technician in {None, "", technician}
        ]
        payload = _assignment_message(doc, selected_items or None, technician_name=technician)
        payload["pending"] = True
        payload["queue_created"] = doc.creation
        pending.append(payload)
    return pending

@frappe.whitelist()
def get_assignment_notification(notification_name=None, document_name=None):
    """Resolve a standard bell click to the FSM modal while the assignment is unacted."""
    log = None
    if notification_name:
        log = frappe.get_doc("Notification Log", notification_name)
        if log.for_user != frappe.session.user:
            frappe.throw("You are not authorized to open this notification", frappe.PermissionError)
        if log.document_type != "Service Request" or not log.document_name:
            return {}
        document_name = log.document_name
    if not document_name:
        return {}
    doc = frappe.get_doc("Service Request", document_name)
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    if not technician or not _technician_owns_request(doc, technician):
        frappe.throw("This notification is not assigned to your technician account", frappe.PermissionError)
    if doc.workflow_state != "Assigned":
        return {"pending": False, "route": "/app/service-request/" + doc.name, "docname": doc.name}
    from elmrkz_fsm.assignment import _assignment_message
    payload = _assignment_message(doc, technician_name=technician)
    payload["pending"] = True
    return payload

@frappe.whitelist()
def accept_assignment(name, latitude=None, longitude=None):
    doc = frappe.get_doc("Service Request", name)
    technician = _get_assigned_technician_for_session(doc)
    if doc.workflow_state in {"Completed", "Cancelled", "Delivered"}:
        frappe.throw("This assignment is no longer actionable.", frappe.ValidationError)
    _append_action_location(doc, "Accept", technician, latitude, longitude)
    _normalize_payment_method(doc)
    doc.workflow_state = "Accepted"
    doc.save(ignore_permissions=True)
    from elmrkz_fsm.assignment_sync import sync_standard_assignees
    sync_standard_assignees(doc, doc.assigned_technician)
    frappe.get_doc("Service Request", name).add_comment(
        "Comment", text=f"Assignment Accepted by technician {frappe.session.user}"
    )
    frappe.db.commit()
    return {"name": name, "workflow_state": "Accepted"}

@frappe.whitelist()
def reject_assignment(name, reason=None, latitude=None, longitude=None):
    doc = frappe.get_doc("Service Request", name)
    technician = _get_assigned_technician_for_session(doc)
    previous_technician = doc.assigned_technician
    _append_action_location(doc, "Reject", technician, latitude, longitude)
    _normalize_payment_method(doc)
    from elmrkz_fsm.assignment_sync import remove_standard_assignees
    remove_standard_assignees(doc, previous_technician)
    doc.assigned_technician = None
    doc.workflow_state = "Rejected"
    doc.save(ignore_permissions=True)
    doc.add_comment("Comment", text=f"Assignment Rejected. Reason: {reason or 'Not specified'}")
    from elmrkz_fsm.assignment import assign_service_request
    reassigned_to = assign_service_request(doc)
    workflow_state = "Assigned" if reassigned_to else "Queued"
    doc.assigned_technician = reassigned_to
    doc.workflow_state = workflow_state
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"reassigned_to": reassigned_to, "workflow_state": workflow_state}

def validate_service_request(doc, method=None):
    doc.validate()
