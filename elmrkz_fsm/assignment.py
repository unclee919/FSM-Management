import re
import unicodedata
from difflib import SequenceMatcher
from math import asin, cos, pi, sin, sqrt

import frappe
from frappe.utils import add_days, get_time, now_datetime


def _valid_coordinate_pair(latitude, longitude):
    if latitude is None or longitude is None:
        return False
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return False
    return -90 <= latitude <= 90 and -180 <= longitude <= 180 and (latitude != 0.0 or longitude != 0.0)


def _driving_maps_link(origin_latitude, origin_longitude, destination_latitude, destination_longitude):
    if not _valid_coordinate_pair(destination_latitude, destination_longitude):
        return None
    if _valid_coordinate_pair(origin_latitude, origin_longitude):
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={float(origin_latitude)},{float(origin_longitude)}"
            f"&destination={float(destination_latitude)},{float(destination_longitude)}"
            "&travelmode=driving"
        )
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={float(destination_latitude)},{float(destination_longitude)}"
    )


def calculate_distance(lat1, lon1, lat2, lon2):
    if not _valid_coordinate_pair(lat1, lon1) or not _valid_coordinate_pair(lat2, lon2):
        return None
    p = pi / 180
    a = 0.5 - cos((lat2 - lat1) * p) / 2 + cos(lat1 * p) * cos(lat2 * p) * (1 - cos((lon2 - lon1) * p)) / 2
    return 12742 * asin(sqrt(max(0, a)))


def is_within_shift(settings):
    now = now_datetime().time()
    start = get_time(settings.default_shift_start_time)
    end = get_time(settings.default_shift_end_time)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _positive_setting(settings, fieldname, default):
    try:
        value = float(getattr(settings, fieldname, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _percentage_setting(settings, fieldname, default):
    try:
        value = float(getattr(settings, fieldname, default) or default)
    except (TypeError, ValueError):
        return default / 100
    return min(100, max(0, value)) / 100


def get_completion_rate(technician_name, settings):
    lookback_days = int(_positive_setting(settings, "completion_rate_lookback_days", 30))
    start_date = add_days(now_datetime(), -lookback_days)
    total = frappe.db.count("Service Request", filters={"assigned_technician": technician_name, "creation": [">", start_date]})
    if total == 0:
        return _percentage_setting(settings, "new_technician_completion_rate_percent", 50)
    completed = frappe.db.count("Service Request", filters={"assigned_technician": technician_name, "workflow_state": "Completed", "creation": [">", start_date]})
    return completed / total


def get_route_suitability(tech_name, req_lat, req_lon, settings):
    scheduled = frappe.get_all("Service Request", filters={"assigned_technician": tech_name, "workflow_state": "Scheduled", "scheduled_date": now_datetime().date()}, fields=["latitude", "longitude"])
    if not scheduled:
        return 1.0
    distances = [calculate_distance(req_lat, req_lon, row.latitude, row.longitude) for row in scheduled]
    distances = [distance for distance in distances if distance is not None]
    distance_scale = _positive_setting(settings, "route_suitability_distance_km", 20)
    return max(0, 1 - (min(distances) / distance_scale)) if distances else 0.0


def _normalise(value):
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _category(value):
    value = _normalise(value)
    if value in {"devicename", "device", "equipment", "item"}:
        return "device_name"
    if value in {"failurereason", "failure", "fault", "problem"}:
        return "failure_reason"
    if value in {"brand", "manufacturer"}:
        return "brand"
    return value


def _matches(value, candidates):
    value = _normalise(value)
    if not value:
        return False
    for candidate in candidates:
        candidate = _normalise(candidate)
        if not candidate:
            continue
        if value == candidate or value in candidate or candidate in value:
            return True
        ratio = SequenceMatcher(None, value, candidate).ratio()
        if len(value) >= 10 and len(candidate) >= 10 and ratio >= 0.80:
            return True
        if len(value) >= 5 and len(candidate) >= 5 and ratio >= 0.82:
            return True
    return False


def _technician_skills(tech_name):
    result = {"device_name": [], "failure_reason": [], "brand": []}
    rows = frappe.get_all("Technician Skill", filters={"parent": tech_name}, fields=["skill_category", "skill_value", "skill_aliases"])
    for row in rows:
        category = _category(row.skill_category)
        if category not in result:
            continue
        result[category].append(row.skill_value)
        result[category].extend([alias.strip() for alias in (row.skill_aliases or "").split(",") if alias.strip()])
    return result


def _item_skill_score(item, skills):
    values = {
        "device_name": getattr(item, "device_name", None),
        "failure_reason": getattr(item, "failure_reason", None),
        "brand": getattr(item, "brand", None),
    }
    present = {category: value for category, value in values.items() if value}
    if not present:
        return 1.0
    device_match = _matches(values["device_name"], skills["device_name"])
    matched = 0
    for category, value in present.items():
        # A matching Device Name means the technician can service that device
        # regardless of failure reason or brand unless a more specific skill is supplied.
        if category in {"failure_reason", "brand"} and device_match:
            matched += 1
        elif _matches(value, skills[category]):
            matched += 1
    return matched / len(present)


def _assignment_items(service_request):
    return [{
        "item_code": row.item_code,
        "item_name": row.item_name,
        "description": row.description,
        "device_name": row.device_name,
        "failure_reason": row.failure_reason,
        "brand": getattr(row, "brand", None),
        "initial_rate": row.initial_rate,
        "row_assigned_technician": row.row_assigned_technician,
    } for row in (service_request.items or [])]


def _assignment_message(service_request, items=None, technician_name=None):
    technician_name = technician_name or service_request.assigned_technician
    technician = frappe.db.get_value(
        "Technician Profile",
        technician_name,
        ["current_latitude", "current_longitude", "last_ping_time"],
        as_dict=True,
    ) if technician_name else None
    distance_km = None
    technician_latitude = technician.current_latitude if technician else None
    technician_longitude = technician.current_longitude if technician else None
    if technician:
        distance_km = calculate_distance(
            service_request.latitude,
            service_request.longitude,
            technician_latitude,
            technician_longitude,
        )
    driving_maps_link = _driving_maps_link(
        technician_latitude,
        technician_longitude,
        service_request.latitude,
        service_request.longitude,
    )
    return {
        "docname": service_request.name,
        "service_request": service_request.name,
        "sales_order": getattr(service_request, "sales_order", None),
        "customer": service_request.customer_name or service_request.customer,
        "customer_phone": service_request.primary_phone,
        "customer_secondary_phone": service_request.secondary_phone,
        "address": service_request.detailed_address,
        "territory": service_request.territory,
        "location_link": service_request.location_link,
        "latitude": service_request.latitude,
        "longitude": service_request.longitude,
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
        "technician_latitude": technician_latitude,
        "technician_longitude": technician_longitude,
        "driving_maps_link": driving_maps_link,
        "technician_last_ping_time": technician.last_ping_time if technician else None,
        "attachment_media": service_request.attachment_media,
        "workflow_state": service_request.workflow_state or "New",
        "items": items if items is not None else _assignment_items(service_request),
    }


def _eligible_technicians(settings):
    # Requests created outside the configured shift must wait. They are not
    # assigned to an offline or merely nearby technician.
    if not is_within_shift(settings):
        return []
    return frappe.get_all(
        "Technician Profile",
        filters={"availability_status": "Available"},
        fields=["*"],
    )


def _score_technician(tech, service_request, settings, item):
    skills = _technician_skills(tech.name)
    skill_score = _item_skill_score(item, skills)
    distance = calculate_distance(service_request.latitude, service_request.longitude, tech.current_latitude, tech.current_longitude)
    proximity_scale = _positive_setting(settings, "proximity_score_distance_km", 50)
    workload_capacity = _positive_setting(settings, "maximum_open_requests_per_technician", 10)
    proximity_score = max(0, 1 - (distance / proximity_scale)) if distance is not None else 0
    availability_score = 1.0 if tech.availability_status == "Available" else 0.5
    open_count = frappe.db.count("Service Request", filters={"assigned_technician": tech.name, "workflow_state": ["not in", ["Delivered", "Completed", "Cancelled"]]})
    workload_score = max(0, 1 - (open_count / workload_capacity))
    completion_score = get_completion_rate(tech.name, settings)
    territory_score = 1.0 if service_request.territory == tech.territory else 0.0
    route_score = get_route_suitability(tech.name, service_request.latitude, service_request.longitude, settings)
    scores = {
        "Geographic Proximity": proximity_score,
        "Skill Match": skill_score,
        "Availability Score": availability_score,
        "Workload Balance": workload_score,
        "Completion Rate": completion_score,
        "Territory Match": territory_score,
        "Route Suitability": route_score,
    }
    total = 0
    for criterion in settings.assignment_criteria:
        if not criterion.enabled:
            continue
        name = criterion.criterion or ""
        aliases = {
            "القرب الجغرافي من موقع العميل": "Geographic Proximity",
            "تطابق التخصص/المهارة": "Skill Match",
            "توفر الفني": "Availability Score",
            "عدد الطلبات المفتوحة الحالية": "Workload Balance",
            "نسبة الإنجاز السابقة": "Completion Rate",
            "انتماؤه لمنطقة الخدمة": "Territory Match",
            "ملاءمة طريقه مع طلبات أخرى": "Route Suitability",
        }
        name = aliases.get(name, name)
        if name in scores:
            total += float(criterion.weight or 0) * scores[name]
    return total


def _record_assignment_notification(service_request, tech_user):
    if not frappe.db.exists("DocType", "Notification Log"):
        return
    existing = frappe.db.get_value(
        "Notification Log",
        {"for_user": tech_user, "document_type": "Service Request", "document_name": service_request.name},
        "name",
    )
    technician_name = frappe.db.get_value("Technician Profile", {"user": tech_user}, "name")
    payload = _assignment_message(service_request, technician_name=technician_name)
    distance = f"{payload['distance_km']} km away" if payload.get("distance_km") is not None else "distance pending GPS update"
    customer = payload.get("customer") or service_request.name
    sales_order = payload.get("sales_order") or "no Sales Order reference"
    if existing:
        notification = frappe.get_doc("Notification Log", existing)
        notification.update({
            "type": "Alert",
            "subject": f"New assignment: {sales_order} — {customer}",
            "email_content": f"Sales Order: {sales_order}. Service Request: {service_request.name}. Customer: {customer}. Distance: {distance}.",
            "read": 0,
        })
        notification.save(ignore_permissions=True)
    else:
        notification = frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": tech_user,
                "type": "Alert",
                "document_type": "Service Request",
                "document_name": service_request.name,
                "subject": f"New assignment: {sales_order} — {customer}",
                "email_content": f"Sales Order: {sales_order}. Service Request: {service_request.name}. Customer: {customer}. Distance: {distance}.",
                "read": 0,
            }
        ).insert(ignore_permissions=True)
    frappe.publish_realtime(
        "notification",
        message={
            "type": "Alert",
            "name": notification.name,
            "notification_name": notification.name,
            "document_type": "Service Request",
            "document_name": service_request.name,
            "subject": notification.subject,
            "for_user": tech_user,
        },
        user=tech_user,
    )


def assign_service_request_to_technician(service_request, technician_name, item_names=None):
    """Assign a request manually and send the exact same pending notification as auto-assignment."""
    profile = frappe.get_doc("Technician Profile", technician_name)
    if not profile.user:
        frappe.throw("The selected technician has no linked User account")
    if item_names:
        selected = set(item_names)
        for row in service_request.items or []:
            if row.name in selected:
                row.row_assigned_technician = technician_name
    else:
        service_request.assigned_technician = technician_name
        for row in service_request.items or []:
            row.row_assigned_technician = technician_name
    service_request.assigned_technician = technician_name
    service_request.assigned_at = now_datetime()
    service_request.workflow_state = "Assigned"
    service_request.save(ignore_permissions=True)
    _record_assignment_notification(service_request, profile.user)
    payload = _assignment_message(service_request, technician_name=technician_name)
    frappe.publish_realtime(event="fsm_new_assignment", message=payload, user=profile.user)
    return payload


def assign_service_request(service_request):
    settings = frappe.get_doc("FSM Settings", "FSM Settings")
    technicians = _eligible_technicians(settings)
    if not technicians:
        if getattr(service_request, "workflow_state", None) in {"New", "Pending Confirmation", "Confirmed", "Rejected"}:
            service_request.workflow_state = "Queued"
        return None

    groups = {}
    rows = list(service_request.items or [])
    if not rows:
        rows = [None]
    for item in rows:
        best = max(technicians, key=lambda tech: _score_technician(tech, service_request, settings, item))
        if item is not None:
            item.row_assigned_technician = best.name
        groups.setdefault(best.name, []).append(item)

    primary = next(iter(groups))
    service_request.assigned_technician = primary
    if getattr(service_request, "flags", None) is not None:
        service_request.flags.assignment_groups = groups

    for tech_name, assigned_rows in groups.items():
        tech_user = frappe.db.get_value("Technician Profile", tech_name, "user")
        if not tech_user:
            continue
        payload_items = _assignment_items(service_request)
        if any(row is not None for row in assigned_rows):
            selected_names = {row.name for row in assigned_rows}
            payload_items = [row for row in payload_items if row.get("row_assigned_technician") == tech_name or not row.get("row_assigned_technician")]
        _record_assignment_notification(service_request, tech_user)
        frappe.publish_realtime(event="fsm_new_assignment", message=_assignment_message(service_request, payload_items, tech_name), user=tech_user)
    return primary


def assign_queued_service_requests():
    """Assign queued requests when the configured shift is active."""
    settings = frappe.get_doc("FSM Settings", "FSM Settings")
    if not is_within_shift(settings):
        return {"processed": 0, "assigned": 0, "reason": "Outside configured shift"}

    rows = frappe.get_all(
        "Service Request",
        filters={"workflow_state": "Queued"},
        fields=["name"],
        order_by="creation asc",
        limit_page_length=100,
    )
    assigned = 0
    for row in rows:
        doc = frappe.get_doc("Service Request", row.name)
        technician = assign_service_request(doc)
        if technician:
            doc.workflow_state = "Assigned"
            doc.save(ignore_permissions=True)
            assigned += 1
    frappe.db.commit()
    return {"processed": len(rows), "assigned": assigned}
