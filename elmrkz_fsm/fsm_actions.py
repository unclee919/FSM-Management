import frappe
from frappe.utils import now_datetime, add_to_date, get_datetime
from math import asin, cos, pi, sin, sqrt

ACTIVE_TRACKING_STATES = ("Confirmed", "Scheduled", "On the Way", "In Progress")


def _valid_coordinate_pair(latitude, longitude):
    """Return a validated, non-zero coordinate pair or None."""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    if lat == 0.0 and lon == 0.0:
        return None
    return lat, lon


def haversine_meters(latitude_1, longitude_1, latitude_2, longitude_2):
    """Return the great-circle distance between two valid points in meters."""
    first = _valid_coordinate_pair(latitude_1, longitude_1)
    second = _valid_coordinate_pair(latitude_2, longitude_2)
    if not first or not second:
        return None
    lat1, lon1 = first
    lat2, lon2 = second
    radians = pi / 180.0
    a = (
        sin((lat2 - lat1) * radians / 2.0) ** 2
        + cos(lat1 * radians) * cos(lat2 * radians)
        * sin((lon2 - lon1) * radians / 2.0) ** 2
    )
    return 2.0 * 6371000.0 * asin(sqrt(min(1.0, max(0.0, a))))


def _arrival_radius_meters(settings):
    """Read a positive arrival radius, defaulting safely to 200 meters."""
    try:
        radius = float(getattr(settings, "arrival_radius_meters", None) or 200)
    except (TypeError, ValueError):
        radius = 200.0
    return radius if radius > 0 else 200.0

# Direct FSM lifecycle transitions. This replaces Frappe Workflow metadata so the
# technician-facing FSM Actions menu remains functional after the Workflow
# document is removed. Every transition is still checked server-side.
FSM_TRANSITIONS = {
    # Cancelled remains a legacy terminal state for existing records, but Cancel is
    # intentionally not exposed as a technician workflow action.
    "New": [("Submit", "Pending Confirmation"), ("Advance", "Queued"), ("Assign", "Assigned")],
    "Queued": [("Submit", "Pending Confirmation"), ("Assign", "Assigned")],
    "Pending Confirmation": [("Confirm", "Confirmed"), ("Assign", "Assigned")],
    "Confirmed": [("Assign", "Assigned"), ("Start Travel", "On the Way")],
    "Assigned": [("Accept", "Accepted"), ("Reject", "Rejected")],
    "Rejected": [("Reroute", "Assigned")],
    "Accepted": [("Confirm Customer", "Confirmed"), ("Start Travel", "On the Way")],
    # Arrival is normally detected from GPS. The manual Arrive action is a
    # fallback for a technician whose device cannot provide a GPS fix.
    "On the Way": [("Arrive", "Delivered")],
    # In Progress is a focused repair state. Price approval and rescheduling
    # are not valid technician actions here.
    "In Progress": [("Waiting for Part", "Waiting for Part"), ("Complete", "Completed")],
    "Waiting for Part": [("Resume Work", "In Progress")],
    "Waiting for Price Approval": [("Approve Price", "In Progress")],
    "Delayed / Scheduled": [("Reschedule", "In Progress")],
    # A technician may still start work after arrival when the repair requires
    # work before completion; otherwise Complete can be used directly.
    "Delivered": [("Start Work", "In Progress"), ("Complete", "Completed")],
    "Completed": [("Reopen Warranty", "Under Warranty (Reopened)")],
    "Under Warranty (Reopened)": [("Start Work", "In Progress")],
}

MANAGER_ONLY_ACTIONS = {"Submit", "Assign", "Reroute", "Approve Price", "Reopen Warranty"}


def _manager_user(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & {"System Manager", "FSM Manager", "Service Manager"})


def _technician_can_act(doc, user=None):
    user = user or frappe.session.user
    if _manager_user(user):
        return True
    profile = frappe.db.get_value("Technician Profile", {"user": user}, "name")
    if not profile:
        return False
    if doc.assigned_technician == profile:
        return True
    return any(row.row_assigned_technician == profile for row in (doc.items or []))


def _require_request_access(doc):
    if not _technician_can_act(doc):
        frappe.throw("You are not authorized to access this service request", frappe.PermissionError)


def _active_request_for_profile(profile_name):
    rows = frappe.get_all(
        "Service Request",
        filters={
            "assigned_technician": profile_name,
            "workflow_state": ["in", list(ACTIVE_TRACKING_STATES)],
        },
        fields=["name"],
        limit=1,
    )
    return rows[0].name if rows else None


def _maps_url(doc):
    """Return a Google Maps driving-navigation URL when both points are valid.

    Google can display two markers for arbitrary coordinates without finding a
    road. The explicit dir_action=navigate and travelmode=driving parameters
    force the car-navigation route UI when the points are connected to a road.
    """
    try:
        customer_lat = float(doc.latitude)
        customer_lon = float(doc.longitude)
    except (TypeError, ValueError):
        return None
    if customer_lat == 0.0 and customer_lon == 0.0:
        return None

    technician = None
    if doc.assigned_technician:
        technician = frappe.db.get_value(
            "Technician Profile",
            doc.assigned_technician,
            ["current_latitude", "current_longitude"],
            as_dict=True,
        )
    try:
        technician_lat = float(technician.current_latitude) if technician and technician.current_latitude is not None else None
        technician_lon = float(technician.current_longitude) if technician and technician.current_longitude is not None else None
    except (TypeError, ValueError):
        technician_lat = technician_lon = None

    has_technician_origin = (
        technician_lat is not None and technician_lon is not None
        and (technician_lat != 0.0 or technician_lon != 0.0)
    )
    if has_technician_origin:
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={technician_lat:.6f},{technician_lon:.6f}"
            f"&destination={customer_lat:.6f},{customer_lon:.6f}"
            "&travelmode=driving&dir_action=navigate"
        )
    return f"https://www.google.com/maps/search/?api=1&query={customer_lat:.6f},{customer_lon:.6f}"


def _validate_coordinates(latitude, longitude):
    lat = float(latitude)
    lon = float(longitude)
    if not -90 <= lat <= 90:
        frappe.throw("Latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        frappe.throw("Longitude must be between -180 and 180")
    return lat, lon


def _persist_technician_location(profile_name, latitude, longitude, event_trigger):
    lat, lon = _validate_coordinates(latitude, longitude)
    profile = frappe.get_doc("Technician Profile", profile_name)
    ping_time = now_datetime()
    maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    frappe.db.set_value(
        "Technician Profile",
        profile.name,
        {
            "current_latitude": lat,
            "current_longitude": lon,
            "google_maps_link": maps_link,
            "last_ping_time": ping_time,
        },
    )
    if frappe.db.exists("DocType", "Technician Location Log"):
        frappe.get_doc(
            {
                "doctype": "Technician Location Log",
                "technician": profile.name,
                "timestamp": ping_time,
                "latitude": lat,
                "longitude": lon,
                "location_link": maps_link,
                "event_trigger": event_trigger,
            }
        ).insert(ignore_permissions=True)
    return {
        "ok": True,
        "profile_name": profile.name,
        "latitude": lat,
        "longitude": lon,
        "google_maps_link": maps_link,
        "last_ping_time": ping_time,
    }


def _log_location(doc, event_trigger, latitude=None, longitude=None):
    if not doc.assigned_technician:
        return
    tech = frappe.db.get_value(
        "Technician Profile",
        doc.assigned_technician,
        ["current_latitude", "current_longitude"],
        as_dict=True,
    ) or {}
    lat = latitude if latitude is not None else tech.get("current_latitude")
    lon = longitude if longitude is not None else tech.get("current_longitude")
    if lat is None or lon is None:
        return
    if frappe.db.exists("DocType", "Technician Location Log"):
        frappe.get_doc(
            {
                "doctype": "Technician Location Log",
                "technician": doc.assigned_technician,
                "timestamp": now_datetime(),
                "latitude": lat,
                "longitude": lon,
                "location_link": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                "event_trigger": event_trigger,
            }
        ).insert(ignore_permissions=True)


def _append_action_history(doc, action, latitude=None, longitude=None):
    """Persist one technician location row for each FSM button action."""
    if not doc.meta.has_field("action_locations") or not doc.assigned_technician:
        return False
    profile = frappe.db.get_value(
        "Technician Profile",
        doc.assigned_technician,
        ["current_latitude", "current_longitude"],
        as_dict=True,
    ) or {}
    lat = latitude if latitude is not None else profile.get("current_latitude")
    lon = longitude if longitude is not None else profile.get("current_longitude")
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0.0 or lon != 0.0)):
        return False
    timestamp = now_datetime()
    previous = (doc.action_locations or [])[-1] if doc.action_locations else None
    elapsed_minutes = None
    if previous and previous.timestamp:
        elapsed_minutes = round((timestamp - get_datetime(previous.timestamp)).total_seconds() / 60.0, 2)
    doc.append("action_locations", {
        "action": action,
        "technician": doc.assigned_technician,
        "latitude": lat,
        "longitude": lon,
        "timestamp": timestamp,
        "google_maps_link": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
        "elapsed_minutes": elapsed_minutes,
    })
    return True


@frappe.whitelist()
def get_location_tracking_config():
    profile_name = frappe.db.get_value(
        "Technician Profile", {"user": frappe.session.user}, "name"
    )
    settings = frappe.get_single("FSM Settings")
    interval = int(settings.live_location_update_interval_minutes or 5)
    interval = max(1, min(interval, 60))
    enabled = bool(settings.live_location_tracking_enabled)
    active_request = _active_request_for_profile(profile_name) if profile_name else None
    return {
        "enabled": enabled,
        "interval_minutes": interval,
        "active": bool(active_request),
        "active_service_request": active_request,
        "profile_name": profile_name,
    }


@frappe.whitelist()
def log_technician_location(profile_name, latitude, longitude, event_trigger="Background Tracking"):
    profile = frappe.get_doc("Technician Profile", profile_name)
    if profile.user != frappe.session.user and not _manager_user():
        frappe.throw("You are not authorized to update this technician location", frappe.PermissionError)
    settings = frappe.get_single("FSM Settings")
    if not settings.live_location_tracking_enabled and not _manager_user():
        return {"ok": False, "reason": "Background location tracking is disabled"}
    if not _active_request_for_profile(profile.name) and not _manager_user() and event_trigger != "Manager Remote Fetch":
        return {"ok": False, "reason": "No active service request is assigned"}
    result = _persist_technician_location(profile.name, latitude, longitude, event_trigger)
    frappe.db.commit()
    return result


@frappe.whitelist()
def manager_update_technician_location(profile_name, latitude, longitude):
    if not _manager_user():
        frappe.throw("Only FSM Managers or System Managers can fetch a technician location", frappe.PermissionError)
    result = _persist_technician_location(profile_name, latitude, longitude, "Manager Manual Fetch")
    frappe.db.commit()
    return result


@frappe.whitelist()
def request_technician_location(profile_name):
    if not _manager_user():
        frappe.throw("Only FSM Managers or System Managers can request a technician location", frappe.PermissionError)
    profile = frappe.get_doc("Technician Profile", profile_name)
    if not profile.user:
        return {"ok": False, "reason": "This technician profile has no linked user"}
    requested_at = now_datetime()
    frappe.publish_realtime(
        event="fsm_location_request",
        message={"profile_name": profile.name, "requested_at": requested_at},
        user=profile.user,
    )
    return {"ok": True, "profile_name": profile.name, "user": profile.user, "requested_at": requested_at}


@frappe.whitelist()
def check_technician_location_request(profile_name, requested_at):
    if not _manager_user():
        frappe.throw("Only FSM Managers or System Managers can check a technician location request", frappe.PermissionError)
    profile = frappe.db.get_value(
        "Technician Profile",
        profile_name,
        ["user", "current_latitude", "current_longitude", "google_maps_link", "last_ping_time"],
        as_dict=True,
    )
    if not profile:
        return {"ok": False, "reason": "The technician profile could not be found."}
    current_ping = profile.last_ping_time
    requested_time = get_datetime(requested_at)
    updated = bool(current_ping and requested_time and current_ping > requested_time)
    if updated:
        return {
            "ok": True,
            "updated": True,
            "latitude": profile.current_latitude,
            "longitude": profile.current_longitude,
            "google_maps_link": profile.google_maps_link,
            "last_ping_time": current_ping,
        }
    return {
        "ok": True,
        "updated": False,
        "reason": "No new GPS response was received. The technician may be offline, signed out, have denied GPS permission, or have an unavailable GPS signal. The last valid location was kept unchanged.",
        "last_ping_time": current_ping,
    }


@frappe.whitelist()
def get_assignable_technicians():
    if not _manager_user():
        frappe.throw("Only an FSM Manager or System Manager can list technicians", frappe.PermissionError)
    return frappe.get_all(
        "Technician Profile",
        fields=["name", "technician_name", "user", "availability_status", "current_latitude", "current_longitude"],
        filters={"user": ["is", "set"]},
        order_by="technician_name asc, name asc",
        limit_page_length=200,
    )


@frappe.whitelist()
def manager_assign_technician(name, technician):
    if not _manager_user():
        frappe.throw("Only an FSM Manager or System Manager can assign technicians", frappe.PermissionError)
    doc = frappe.get_doc("Service Request", name)
    if doc.workflow_state in {"Completed", "Cancelled", "Delivered", "On the Way", "In Progress"}:
        frappe.throw("This request is already active or closed and cannot be manually reassigned from this screen")
    from elmrkz_fsm.assignment import assign_service_request_to_technician
    payload = assign_service_request_to_technician(doc, technician)
    frappe.db.commit()
    return payload


@frappe.whitelist()
def transition_service_request(name, action, latitude=None, longitude=None):
    doc = frappe.get_doc("Service Request", name)
    if action in MANAGER_ONLY_ACTIONS:
        if not _manager_user():
            frappe.throw("Only an FSM Manager or System Manager can perform this action", frappe.PermissionError)
    else:
        _require_request_access(doc)

    state = doc.workflow_state or "New"
    if action == "Complete":
        frappe.throw("Use the Complete dialog to enter service price, spare parts, and payment details.", frappe.ValidationError)
    if action == "Waiting for Spare Part":
        frappe.throw("Use the Waiting for Spare Part dialog to choose Purchase or Transfer.", frappe.ValidationError)
    transition = next((item for item in FSM_TRANSITIONS.get(state, []) if item[0] == action), None)
    if not transition:
        frappe.throw(f"Action {action} is not available from {state}", frappe.ValidationError)
    next_state = transition[1]
    doc.workflow_state = next_state
    doc.save(ignore_permissions=True)
    doc.add_comment("Comment", text=f"FSM action: {action} ({state} → {next_state}) by {frappe.session.user}")

    if latitude is not None and longitude is not None and doc.assigned_technician:
        _persist_technician_location(doc.assigned_technician, latitude, longitude, action)
    else:
        _log_location(doc, action)
    if _append_action_history(doc, action, latitude, longitude):
        doc.save(ignore_permissions=True)
    if next_state == "On the Way" and doc.meta.has_field("tracking_expires_at"):
        doc.db_set("tracking_expires_at", add_to_date(now_datetime(), hours=24))
    if next_state == "Delivered" and doc.meta.has_field("tracking_expires_at"):
        doc.db_set("tracking_expires_at", None)
    frappe.db.commit()
    return {
        "name": doc.name,
        "workflow_state": next_state,
        "next_actions": [{"action": item[0], "next_state": item[1]} for item in FSM_TRANSITIONS.get(next_state, [])],
        "maps_url": _maps_url(doc),
    }


@frappe.whitelist()
def log_location(name, latitude, longitude, event_trigger="Manual Update"):
    doc = frappe.get_doc("Service Request", name)
    _require_request_access(doc)
    if not doc.assigned_technician:
        frappe.throw("This service request has no assigned technician")
    result = _persist_technician_location(
        doc.assigned_technician, latitude, longitude, event_trigger
    )
    frappe.db.commit()
    result["service_request"] = doc.name
    result["maps_url"] = _maps_url(doc)
    return result


@frappe.whitelist()
def create_sales_order(name):
    doc = frappe.get_doc("Service Request", name)
    _require_request_access(doc)
    if doc.meta.has_field("sales_order") and doc.sales_order:
        return doc.sales_order
    if not doc.customer:
        frappe.throw("Service Request must have a Customer before Sales Order creation")
    items = []
    for row in doc.items:
        if row.item_code:
            item = {"item_code": row.item_code, "qty": 1, "rate": row.initial_rate or 0}
            if getattr(row, "device_name", None):
                item["custom_device_name"] = row.device_name
            if getattr(row, "failure_reason", None):
                item["custom_failure_reason"] = row.failure_reason
            if getattr(row, "brand", None):
                item["custom_brand"] = row.brand
            items.append(item)
    if not items:
        default_item = frappe.db.get_single_value("FSM Settings", "default_service_item")
        if default_item:
            items = [{"item_code": default_item, "qty": 1, "rate": 0}]
    if not items:
        frappe.throw("Configure default_service_item or add an item before creating a Sales Order")
    latitude = getattr(doc, "latitude", None)
    longitude = getattr(doc, "longitude", None)
    location_link = getattr(doc, "location_link", None)
    if latitude is not None and longitude is not None:
        try:
            valid_coords = (float(latitude) != 0.0 or float(longitude) != 0.0)
        except (TypeError, ValueError):
            valid_coords = False
        if valid_coords:
            location_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    so_values = {
        "doctype": "Sales Order",
        "customer": doc.customer,
        "transaction_date": frappe.utils.today(),
        "delivery_date": frappe.utils.today(),
        "items": items,
        "custom_customer_phone": getattr(doc, "primary_phone", None),
        "custom_customer_phone_2": getattr(doc, "secondary_phone", None),
        "custom_service_address": getattr(doc, "detailed_address", None),
        "custom_territory": getattr(doc, "territory", None),
        "custom_location_link": location_link,
        "custom_latitude": latitude,
        "custom_longitude": longitude,
    }
    so = frappe.get_doc(so_values).insert(ignore_permissions=True)
    if doc.meta.has_field("sales_order"):
        doc.db_set("sales_order", so.name)
    frappe.db.commit()
    return so.name


@frappe.whitelist()
def create_sales_invoice(name):
    doc = frappe.get_doc("Service Request", name)
    _require_request_access(doc)
    if doc.meta.has_field("sales_invoice") and doc.sales_invoice:
        return doc.sales_invoice
    if not doc.customer:
        frappe.throw("Service Request must have a Customer before Sales Invoice creation")
    so = create_sales_order(name)
    invoice = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": doc.customer,
            "items": [
                {"item_code": r.item_code, "qty": r.qty or 1, "rate": r.rate or 0}
                for r in doc.parts
                if r.item_code
            ],
        }
    )
    if not invoice.items:
        so_doc = frappe.get_doc("Sales Order", so)
        invoice.set(
            "items",
            [{"item_code": r.item_code, "qty": r.qty, "rate": r.rate} for r in so_doc.items],
        )
    invoice.insert(ignore_permissions=True)
    if doc.meta.has_field("sales_invoice"):
        doc.db_set("sales_invoice", invoice.name)
    frappe.db.commit()
    return invoice.name


@frappe.whitelist()
def available_actions(name):
    doc = frappe.get_doc("Service Request", name)
    _require_request_access(doc)
    return [
        {"action": action, "next_state": next_state}
        for action, next_state in FSM_TRANSITIONS.get(doc.workflow_state or "New", [])
    ]


@frappe.whitelist()
def map_url(name):
    doc = frappe.get_doc("Service Request", name)
    _require_request_access(doc)
    return _maps_url(doc)


def check_arrival_proximity():
    """Automatically move On the Way requests to Delivered when GPS arrives.

    This job is intentionally deterministic and idempotent. Invalid or zero
    coordinates are ignored, and a request already moved out of On the Way is
    never processed again. The configured arrival radius is independent from
    the company operating radius used by assignment.
    """
    settings = frappe.get_single("FSM Settings")
    radius_m = _arrival_radius_meters(settings)
    rows = frappe.get_all(
        "Service Request",
        filters={
            "workflow_state": "On the Way",
            "assigned_technician": ["is", "set"],
        },
        fields=["name", "assigned_technician", "latitude", "longitude"],
        limit_page_length=500,
    )
    processed = 0
    delivered = 0
    skipped = 0

    for row in rows:
        processed += 1
        distance_m = haversine_meters(
            row.latitude,
            row.longitude,
            frappe.db.get_value("Technician Profile", row.assigned_technician, "current_latitude"),
            frappe.db.get_value("Technician Profile", row.assigned_technician, "current_longitude"),
        )
        if distance_m is None or distance_m > radius_m:
            skipped += 1
            continue

        # Re-read the document before changing it so a manual action or a
        # previous worker run cannot cause a duplicate arrival transition.
        doc = frappe.get_doc("Service Request", row.name)
        if (doc.workflow_state or "New") != "On the Way":
            skipped += 1
            continue
        if not _append_action_history(doc, "Auto Arrived"):
            skipped += 1
            continue
        doc.workflow_state = "Delivered"
        doc.save(ignore_permissions=True)
        doc.add_comment(
            "Comment",
            text=f"FSM action: Auto Arrived (On the Way → Delivered), GPS distance {round(distance_m, 1)} m, radius {round(radius_m, 1)} m",
        )
        if doc.meta.has_field("tracking_expires_at"):
            doc.db_set("tracking_expires_at", None)
        technician_user = frappe.db.get_value("Technician Profile", row.assigned_technician, "user")
        payload = {
            "name": doc.name,
            "service_request": doc.name,
            "workflow_state": "Delivered",
            "distance_meters": round(distance_m, 1),
            "arrival_radius_meters": round(radius_m, 1),
        }
        if technician_user:
            frappe.publish_realtime(event="fsm_auto_arrived", message=payload, user=technician_user)
        delivered += 1

    frappe.db.commit()
    return {
        "processed": processed,
        "delivered": delivered,
        "skipped": skipped,
        "arrival_radius_meters": radius_m,
    }


def expire_tracking_links():
    if not frappe.db.has_column("Service Request", "tracking_expires_at"):
        return
    for name in frappe.get_all(
        "Service Request",
        filters={"tracking_expires_at": ["<", now_datetime()]},
        pluck="name",
    ):
        frappe.db.set_value("Service Request", name, "tracking_expires_at", None)
    frappe.db.commit()
