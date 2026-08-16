import frappe


def _value(doc, fieldname, default=None):
    return getattr(doc, fieldname, default) if hasattr(doc, fieldname) else default


def _has_classification(row):
    return any(
        _value(row, fieldname)
        for fieldname in ("custom_device_name", "custom_failure_reason", "custom_brand")
    )


def _existing_request(sales_order_name):
    return frappe.db.get_value("Service Request", {"sales_order": sales_order_name}, "name")


def create_service_request_from_sales_order(doc, method=None):
    """Create one FSM Service Request from a submitted Sales Order when its items contain FSM classification data."""
    if frappe.flags.in_patch or frappe.flags.in_install:
        return None
    if not any(_has_classification(row) for row in (doc.items or [])):
        return None
    if _existing_request(doc.name):
        return _existing_request(doc.name)

    request_items = []
    for row in doc.items or []:
        request_items.append({
            "item_code": row.item_code,
            "item_name": row.item_name,
            "description": row.description,
            "device_name": _value(row, "custom_device_name"),
            "failure_reason": _value(row, "custom_failure_reason"),
            "brand": _value(row, "custom_brand"),
            "initial_rate": row.rate or 0,
            "qty": _value(row, "qty", 1) or 1,
        })

    custom_phone = _value(doc, "custom_customer_phone")
    custom_phone_2 = _value(doc, "custom_customer_phone_2")
    primary_phone = custom_phone or _value(doc, "contact_phone") or _value(doc, "contact_mobile")
    secondary_phone = custom_phone_2 or _value(doc, "contact_phone_2")
    detailed_address = (
        _value(doc, "custom_service_address")
        or _value(doc, "shipping_address")
        or _value(doc, "shipping_address_name")
        or _value(doc, "billing_address")
        or _value(doc, "billing_address_name")
    )
    territory = _value(doc, "custom_territory") or _value(doc, "territory")
    latitude = _value(doc, "custom_latitude")
    longitude = _value(doc, "custom_longitude")
    location_link = _value(doc, "custom_location_link")
    if not location_link and latitude not in (None, "") and longitude not in (None, ""):
        try:
            if float(latitude) != 0.0 or float(longitude) != 0.0:
                location_link = f"https://www.google.com/maps/search/?api=1&query={float(latitude)},{float(longitude)}"
        except (TypeError, ValueError):
            location_link = None

    values = {
        "doctype": "Service Request",
        "customer": doc.customer,
        "customer_name": _value(doc, "customer_name"),
        "territory": territory,
        "primary_phone": primary_phone,
        "secondary_phone": secondary_phone,
        "detailed_address": detailed_address,
        "location_link": location_link,
        "latitude": latitude,
        "longitude": longitude,
        "items": request_items,
        "workflow_state": "New",
    }

    request = frappe.get_doc(values).insert(ignore_permissions=True)
    request.sales_order = doc.name
    from .assignment import assign_service_request
    assigned = assign_service_request(request)
    request.workflow_state = "Assigned" if assigned else (request.workflow_state or "Queued")
    request.save(ignore_permissions=True)
    frappe.db.commit()
    return {"service_request": request.name, "assigned_technician": assigned}
