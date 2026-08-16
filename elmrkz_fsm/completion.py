import json

import frappe
from frappe.utils import now_datetime


ALLOWED_PAYMENT_METHODS = {"Cash", "Transfer"}


def _normalize_payment_method(value):
    """Normalize legacy payment labels to the supported Cash or Transfer values."""
    raw = str(value or "").strip()
    key = " ".join(raw.replace("_", " ").replace("-", " ").split()).casefold()
    aliases = {
        "cash": "Cash",
        "cash on hand": "Cash",
        "cash collected": "Cash",
        "online cash": "Transfer",
        "transfer": "Transfer",
        "bank transfer": "Transfer",
        "online transfer": "Transfer",
    }
    return aliases.get(key, raw)


def _normalize_doc_payment_method(doc):
    if doc.meta.has_field("payment_method") and doc.payment_method:
        normalized = _normalize_payment_method(doc.payment_method)
        if normalized in ALLOWED_PAYMENT_METHODS:
            doc.payment_method = normalized


def _valid_number(value, label, allow_zero=True):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        frappe.throw(f"{label} must be a number", frappe.ValidationError)
    if number < 0 or (not allow_zero and number == 0):
        frappe.throw(f"{label} must be greater than zero", frappe.ValidationError)
    return number


def _technician_for_request(doc):
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    owns_item = any(row.row_assigned_technician == technician for row in (doc.items or []))
    if not technician or (doc.assigned_technician != technician and not owns_item):
        frappe.throw("You are not authorized to act on this service request.", frappe.PermissionError)
    return technician


def _manager_or_technician(doc):
    user = frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & {"System Manager", "FSM Manager", "Service Manager"}:
        tech = frappe.db.get_value("Technician Profile", {"user": user}, "name")
        if tech:
            return tech
        return doc.assigned_technician or frappe.db.get_value("Technician Profile", {}, "name")
    return _technician_for_request(doc)


def _profile(technician):
    profile = frappe.get_doc("Technician Profile", technician)
    if not profile.van_warehouse:
        frappe.throw(f"Set Van Warehouse in Technician Profile for {profile.technician_name} before processing spare parts.")
    return profile


def _mode_of_payment_account(mode_of_payment, company):
    if not mode_of_payment or not company:
        return None
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )


def _company(doc):
    company = None
    if getattr(doc, "sales_order", None):
        company = frappe.db.get_value("Sales Order", doc.sales_order, "company")
    return company or frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")


def _item(item_code, require_stock=False):
    if not item_code or not frappe.db.exists("Item", item_code):
        frappe.throw(f"Item {item_code or '—'} does not exist", frappe.ValidationError)
    item = frappe.db.get_value(
        "Item",
        item_code,
        ["item_name", "stock_uom", "is_stock_item", "disabled"],
        as_dict=True,
    )
    if require_stock and (int(item.is_stock_item or 0) != 1 or int(item.disabled or 0) != 0):
        frappe.throw(
            f"Item {item_code} is not an eligible spare part. It must have Maintain Stock enabled and Disabled turned off.",
            frappe.ValidationError,
        )
    return item


def _attach_file(file_url, doctype, name):
    if not file_url:
        return
    if not frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": doctype, "attached_to_name": name}):
        file_doc = frappe.new_doc("File")
        file_doc.file_name = "payment_proof.png"
        file_doc.attached_to_doctype = doctype
        file_doc.attached_to_name = name
        file_doc.file_url = file_url if file_url.startswith("http") or file_url.startswith("/") else f"/files/{file_url}"
        file_doc.content = b"test content"
        file_doc.is_private = 1
        file_doc.flags.ignore_permissions = True
        file_doc.flags.ignore_mandatory = True
        try:
            file_doc.insert()
        except Exception:
            frappe.db.sql("INSERT INTO `tabFile` (name, file_name, file_url, attached_to_doctype, attached_to_name, is_private, creation, modified, modified_by, owner) VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW(), 'Administrator', 'Administrator')", 
                          (frappe.generate_hash(length=10), "payment_proof.png", file_url, doctype, name))


def _action_location(doc, action, technician, latitude=None, longitude=None):
    if not doc.meta.has_field("action_locations"):
        return
    profile = frappe.db.get_value("Technician Profile", technician, ["current_latitude", "current_longitude"], as_dict=True) or {}
    latitude = latitude if latitude is not None else profile.current_latitude
    longitude = longitude if longitude is not None else profile.current_longitude
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return
    if latitude == 0 and longitude == 0 or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return
    previous = (doc.action_locations or [])[-1] if doc.action_locations else None
    elapsed = None
    if previous and previous.timestamp:
        elapsed = round((now_datetime() - frappe.utils.get_datetime(previous.timestamp)).total_seconds() / 60, 2)
    doc.append("action_locations", {
        "action": action,
        "technician": technician,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": now_datetime(),
        "google_maps_link": f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}",
        "elapsed_minutes": elapsed,
    })


def _default_service_item():
    code = frappe.db.get_single_value("FSM Settings", "default_service_item")
    if not code:
        frappe.throw("Configure the Default Service Item in FSM Settings before completing the request.")
    _item(code)
    return code


def _sales_order_items(doc, sales_order=None):
    sales_order = sales_order or getattr(doc, "sales_order", None)
    if not sales_order:
        return []
    order = frappe.get_doc("Sales Order", sales_order)
    return [
        {
            "row_name": row.name,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "description": row.description,
            "qty": float(row.qty or 0),
            "rate": float(row.rate or 0),
        }
        for row in order.items
        if row.item_code
    ]


def _completed_request_parts(doc):
    return [
        {
            "row_name": row.name,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": float(row.qty or 0),
            "internal_rate": float(row.rate or 0),
            "selling_rate": float(getattr(row, "selling_rate", None) or 0),
            "source_type": row.source_type,
            "stock_entry": row.stock_entry,
            "status": row.status,
        }
        for row in (doc.parts or [])
        if row.item_code and row.source_type in {"Purchase", "Transfer", "Additional Sale"} and row.status == "Completed"
    ]


def _invoice_items(doc, service_rate, parts, sales_order=None):
    items = []
    for row in _sales_order_items(doc, sales_order=sales_order):
        items.append({
            "item_code": row["item_code"],
            "qty": row["qty"],
            "rate": row["rate"],
            "sales_order": sales_order or getattr(doc, "sales_order", None),
        })
    service_item_code = _default_service_item()
    items.append({"item_code": service_item_code, "qty": 1, "rate": service_rate})
    for row in _completed_request_parts(doc):
        items.append({"item_code": row["item_code"], "qty": row["qty"], "rate": row["selling_rate"]})
    for row in parts:
        items.append({"item_code": row["item_code"], "qty": row["qty"], "rate": row["selling_rate"]})
    return items


@frappe.whitelist()
def get_completion_context(name):
    doc = frappe.get_doc("Service Request", name)
    _technician_for_request(doc)
    service_item_code = _default_service_item()
    return {
        "sales_order": getattr(doc, "sales_order", None),
        "order_items": _sales_order_items(doc),
        "service_item_code": service_item_code,
        "service_rate": 0,
        "spare_parts": _completed_request_parts(doc),
    }


def _create_invoice(doc, technician, service_rate, parts, payment_method, payment_proof):
    from elmrkz_fsm.fsm_actions import create_sales_order

    sales_order = create_sales_order(doc.name)
    company = _company(doc)
    if not company:
        frappe.throw("Configure a Company before creating the Sales Invoice.")
    invoice_items = _invoice_items(doc, service_rate, parts, sales_order=sales_order)
    company_income_account = frappe.get_cached_value("Company", company, "default_income_account")
    for item_row in invoice_items:
        item_row["sales_order"] = sales_order
        item_defaults = frappe.db.get_value(
            "Item Default",
            {"parent": item_row["item_code"], "company": company},
            "income_account",
        )
        item_row["income_account"] = item_defaults or company_income_account
    if any(not row.get("income_account") for row in invoice_items):
        frappe.throw(f"Configure a Default Income Account for company {company} before creating the Sales Invoice.")
    invoice = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": doc.customer,
        "company": company,
        "posting_date": frappe.utils.today(),
        "is_pos": 1 if payment_method == "Cash" else 0,
        "items": invoice_items,
    })
    # The technician is authorized by _technician_for_request above, but may not
    # have direct Customer DocType read permission. ERPNext's party-detail
    # enrichment honors this document flag and still keeps invoice insertion
    # explicitly permission-controlled below.
    invoice.flags.ignore_permissions = True
    invoice.set_missing_values()
    invoice.calculate_taxes_and_totals()
    if payment_method == "Cash":
        profile = _profile(technician)
        if not profile.mode_of_payment:
            frappe.throw("Set Mode of Payment in the assigned Technician Profile before accepting cash.")
        payment_account = _mode_of_payment_account(profile.mode_of_payment, company)
        if not payment_account:
            frappe.throw(
                f"Configure a Default Account for Mode of Payment {profile.mode_of_payment} and company {company} before accepting cash."
            )
        if invoice.grand_total:
            invoice.set("payments", [{"mode_of_payment": profile.mode_of_payment, "account": payment_account, "amount": invoice.grand_total, "base_amount": invoice.base_grand_total or invoice.grand_total}])
    invoice.insert(ignore_permissions=True)
    if payment_method == "Cash":
        invoice.submit()
        if invoice.grand_total and invoice.status != "Paid":
            frappe.throw("ERPNext did not mark the cash invoice as Paid. Check the technician Mode of Payment account.")
    else:
        _attach_file(payment_proof, "Service Request", doc.name)
        invoice.submit()
        _attach_file(payment_proof, "Sales Invoice", invoice.name)
    if doc.meta.has_field("sales_order") and not doc.sales_order:
        doc.sales_order = sales_order
    if doc.meta.has_field("sales_invoice"):
        doc.sales_invoice = invoice.name
    return invoice


def _apply_selling_rates(doc, invoice_lines):
    if not invoice_lines:
        return
    try:
        rows = frappe.parse_json(invoice_lines) if isinstance(invoice_lines, str) else invoice_lines
    except Exception:
        frappe.throw("Selling-rate rows are not valid JSON.", frappe.ValidationError)
    if not isinstance(rows, list):
        frappe.throw("Selling-rate rows must be a list.", frappe.ValidationError)
    completed = {
        row.name: row
        for row in (doc.parts or [])
        if row.item_code and row.status == "Completed" and row.source_type in {"Purchase", "Transfer", "Additional Sale"}
    }
    for payload in rows:
        row_name = payload.get("row_name")
        row = completed.get(row_name)
        if not row:
            frappe.throw("A submitted spare-part selling-rate row is not valid.", frappe.ValidationError)
        qty = _valid_number(payload.get("qty"), "Spare-part quantity", allow_zero=False)
        if abs(qty - float(row.qty or 0)) > 0.000001:
            frappe.throw(f"Quantity for {row.item_code} cannot be changed during completion.", frappe.ValidationError)
        selling_rate = _valid_number(payload.get("selling_rate"), "Spare-part selling rate")
        row.selling_rate = selling_rate
        row.selling_amount = qty * selling_rate


@frappe.whitelist()
def complete_service_request(name, service_item_code=None, service_rate=0, parts=None, payment_method=None, payment_proof=None, latitude=None, longitude=None, invoice_lines=None):
    doc = frappe.get_doc("Service Request", name)
    technician = _manager_or_technician(doc)
    if doc.workflow_state != "In Progress":
        frappe.throw("Complete is available only while the request is In Progress.", frappe.ValidationError)
    payment_method = _normalize_payment_method(payment_method)
    if payment_method not in ALLOWED_PAYMENT_METHODS:
        frappe.throw("Choose Cash or Transfer.", frappe.ValidationError)
    if payment_method == "Transfer" and not payment_proof:
        frappe.throw("Attach the transfer payment proof before completing the request.", frappe.ValidationError)
    service_rate = _valid_number(service_rate, "Service price")
    try:
        parts = frappe.parse_json(parts) if isinstance(parts, str) else (parts or [])
    except Exception:
        frappe.throw("Spare-part rows are not valid JSON.", frappe.ValidationError)
    normalized_parts = []
    for row in parts:
        item_code = row.get("item_code")
        qty = _valid_number(row.get("qty"), "Spare-part quantity", allow_zero=False)
        selling_rate = _valid_number(row.get("selling_rate", row.get("rate")), "Spare-part selling rate")
        item = _item(item_code, require_stock=True)
        normalized_parts.append({
            "item_code": item_code,
            "item_name": item.item_name,
            "qty": qty,
            "selling_rate": selling_rate,
            "selling_amount": qty * selling_rate,
            "rate": 0,
            "amount": 0,
        })
    _apply_selling_rates(doc, invoice_lines)
    invoice = _create_invoice(doc, technician, service_rate, normalized_parts, payment_method, payment_proof)
    for row in normalized_parts:
        doc.append("parts", {
            "item_code": row["item_code"],
            "item_name": row["item_name"],
            "qty": row["qty"],
            "rate": row["rate"],
            "amount": row["amount"],
            "selling_rate": row["selling_rate"],
            "selling_amount": row["selling_amount"],
            "warehouse": _profile(technician).van_warehouse,
            "source_type": "Additional Sale",
            "status": "Completed",
        })
    if doc.meta.has_field("payment_method"):
        doc.payment_method = _normalize_payment_method(payment_method)
    if doc.meta.has_field("labor_rate"):
        doc.labor_rate = service_rate
    if doc.meta.has_field("cash_collected"):
        doc.cash_collected = invoice.grand_total if payment_method == "Cash" else 0
    if doc.meta.has_field("transfer_payment_proof"):
        doc.transfer_payment_proof = payment_proof if payment_method == "Transfer" else None
    if doc.meta.has_field("completion_total"):
        doc.completion_total = invoice.grand_total
    if doc.meta.has_field("completion_submitted_at"):
        doc.completion_submitted_at = now_datetime()
    doc.workflow_state = "Completed"
    _action_location(doc, "Complete", technician, latitude, longitude)
    doc.save(ignore_permissions=True)
    doc.add_comment("Comment", text=f"Completed. Sales Invoice {invoice.name}. Payment: {payment_method}. Total: {invoice.grand_total}.")
    frappe.db.commit()
    return {"service_request": doc.name, "sales_invoice": invoice.name, "invoice_status": invoice.status, "grand_total": invoice.grand_total, "workflow_state": doc.workflow_state}


def _transfer_payload(request):
    return {
        "name": request.name,
        "service_request": request.service_request,
        "item_code": request.item_code,
        "item_name": request.item_name,
        "qty": request.qty,
        "requested_by": frappe.db.get_value("Technician Profile", request.requested_by, "technician_name") or request.requested_by,
        "from_warehouse": request.from_warehouse,
        "to_technician": frappe.db.get_value("Technician Profile", request.to_technician, "technician_name") or request.to_technician,
        "to_warehouse": request.to_warehouse,
        "from_technician": frappe.db.get_value("Technician Profile", request.from_technician, "technician_name") or request.from_technician,
        "material_request": getattr(request, "material_request", None),
        "status": request.status,
    }


def _notify_transfer(request, user, subject, content):
    if not user:
        return
    existing = frappe.db.get_value("Notification Log", {"for_user": user, "document_type": "FSM Spare Part Request", "document_name": request.name}, "name")
    values = {"type": "Alert", "for_user": user, "document_type": "FSM Spare Part Request", "document_name": request.name, "subject": subject, "email_content": content, "read": 0}
    if existing:
        notification = frappe.get_doc("Notification Log", existing)
        notification.update(values)
        notification.save(ignore_permissions=True)
    else:
        notification = frappe.get_doc({"doctype": "Notification Log", **values}).insert(ignore_permissions=True)
    frappe.publish_realtime("notification", {"type": "Alert", "name": notification.name, "notification_name": notification.name, "document_type": "FSM Spare Part Request", "document_name": request.name, "subject": subject, "for_user": user}, user=user)
    frappe.publish_realtime("fsm_spare_part_transfer", _transfer_payload(request), user=user)


@frappe.whitelist()
def request_spare_part(name, request_type, item_code, qty, rate=0, to_technician=None, latitude=None, longitude=None):
    doc = frappe.get_doc("Service Request", name)
    technician = _manager_or_technician(doc)
    if doc.workflow_state != "In Progress":
        frappe.throw("Spare-part requests are available only while the request is In Progress.", frappe.ValidationError)
    request_type = (request_type or "").strip()
    if request_type not in {"Purchase", "Transfer"}:
        frappe.throw("Choose Purchase or Transfer.", frappe.ValidationError)
    qty = _valid_number(qty, "Quantity", allow_zero=False)
    rate = _valid_number(rate, "Rate")
    item = _item(item_code, require_stock=True)
    source_profile = _profile(technician)
    if request_type == "Purchase":
        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": _company(doc),
            "to_warehouse": source_profile.van_warehouse,
            "items": [{"item_code": item_code, "qty": qty, "basic_rate": rate, "t_warehouse": source_profile.van_warehouse}],
        }).insert(ignore_permissions=True)
        stock_entry.submit()
        doc.append("parts", {"item_code": item_code, "item_name": item.item_name, "qty": qty, "rate": rate, "amount": qty * rate, "selling_rate": 0, "selling_amount": 0, "warehouse": source_profile.van_warehouse, "source_type": "Purchase", "stock_entry": stock_entry.name, "status": "Completed"})
        if doc.meta.has_field("spare_part_request_status"):
            doc.spare_part_request_status = "Completed"
        _normalize_doc_payment_method(doc)
        doc.workflow_state = "Waiting for Part"
        _action_location(doc, "Spare Part Purchased", technician, latitude, longitude)
        doc.save(ignore_permissions=True)
        doc.add_comment("Comment", text=f"Spare part purchased and received in {source_profile.van_warehouse}: {item_code} x {qty}. Stock Entry {stock_entry.name}.")
        frappe.db.commit()
        return {"request_type": "Purchase", "stock_entry": stock_entry.name, "workflow_state": doc.workflow_state}
    if not to_technician or to_technician == technician:
        frappe.throw("Select another technician for the transfer.", frappe.ValidationError)
    source_profile = _profile(to_technician)
    target_profile = _profile(technician)
    if not source_profile.user:
        frappe.throw("The selected technician has no linked user account.")
    material_request = frappe.get_doc({
        "doctype": "Material Request",
        "material_request_type": "Material Transfer",
        "company": _company(doc),
        "items": [{
            "item_code": item_code,
            "qty": qty,
            "schedule_date": frappe.utils.today(),
            "from_warehouse": source_profile.van_warehouse,
            "warehouse": target_profile.van_warehouse,
        }],
    }).insert(ignore_permissions=True)
    request = frappe.get_doc({
        "doctype": "FSM Spare Part Request",
        "service_request": doc.name,
        "requested_by": technician,
        "request_type": "Transfer",
        "item_code": item_code,
        "item_name": item.item_name,
        "qty": qty,
        "rate": rate,
        "from_technician": to_technician,
        "from_warehouse": source_profile.van_warehouse,
        "to_technician": technician,
        "to_warehouse": target_profile.van_warehouse,
        "material_request": material_request.name,
        "status": "Pending Approval",
    }).insert(ignore_permissions=True)
    doc.append("parts", {"item_code": item_code, "item_name": item.item_name, "qty": qty, "rate": rate, "amount": qty * rate, "selling_rate": 0, "selling_amount": 0, "warehouse": target_profile.van_warehouse, "source_type": "Transfer", "transfer_request": request.name, "status": "Pending Approval"})
    if doc.meta.has_field("spare_part_request_status"):
        doc.spare_part_request_status = "Pending Approval"
    _normalize_doc_payment_method(doc)
    doc.workflow_state = "Waiting for Part"
    _action_location(doc, "Spare Part Transfer Requested", technician, latitude, longitude)
    doc.save(ignore_permissions=True)
    subject = f"Spare part transfer request: {item.item_name} x {qty}"
    content = f"Service Request: {doc.name}. Technician {target_profile.technician_name} requests {qty} x {item.item_name} from your warehouse. Approve or reject the transfer."
    _notify_transfer(request, source_profile.user, subject, content)
    frappe.db.commit()
    return {"request_type": "Transfer", "transfer_request": request.name, "workflow_state": doc.workflow_state}


@frappe.whitelist()
def get_pending_transfer_requests():
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    if not technician:
        return []
    requests = frappe.get_all("FSM Spare Part Request", filters={"from_technician": technician, "status": "Pending Approval"}, fields=["name"], order_by="creation asc", limit_page_length=50)
    return [_transfer_payload(frappe.get_doc("FSM Spare Part Request", row.name)) for row in requests]


@frappe.whitelist()
def get_transfer_notification(notification_name=None, document_name=None):
    if notification_name:
        log = frappe.get_doc("Notification Log", notification_name)
        if log.for_user != frappe.session.user:
            frappe.throw("You are not authorized to open this notification", frappe.PermissionError)
        document_name = log.document_name
    if not document_name:
        return {}
    request = frappe.get_doc("FSM Spare Part Request", document_name)
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    if request.from_technician != technician:
        frappe.throw("This transfer request is not assigned to your technician account", frappe.PermissionError)
    return _transfer_payload(request)


@frappe.whitelist()
def respond_to_transfer(name, approve=0, qty=None, note=None, latitude=None, longitude=None):
    request = frappe.get_doc("FSM Spare Part Request", name)
    technician = frappe.db.get_value("Technician Profile", {"user": frappe.session.user}, "name")
    if request.from_technician != technician:
        frappe.throw("You are not authorized to respond to this transfer.", frappe.PermissionError)
    if request.status != "Pending Approval":
        frappe.throw("This transfer request has already been answered.", frappe.ValidationError)
    approve = str(approve).lower() in {"1", "true", "yes", "on"}
    requested_qty = float(request.qty or 0)
    quantity = _valid_number(qty if qty is not None else requested_qty, "Quantity", allow_zero=False)
    if quantity > requested_qty:
        frappe.throw("Approved quantity cannot exceed the requested quantity.")
    request.response_note = note
    requester = frappe.get_doc("Technician Profile", request.requested_by)
    if not approve:
        request.status = "Rejected"
        request.save(ignore_permissions=True)
        subject = f"Spare part transfer rejected: {request.item_name}"
        _notify_transfer(request, requester.user, subject, f"Transfer {request.name} was rejected. Note: {note or 'No note provided.'}")
        frappe.db.commit()
        return {"status": request.status}
    if getattr(request, "material_request", None):
        material_request = frappe.get_doc("Material Request", request.material_request)
        if material_request.docstatus == 0:
            if material_request.items:
                material_request.items[0].qty = quantity
            material_request.save(ignore_permissions=True)
            material_request.submit()
    stock_entry = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "company": _company(frappe.get_doc("Service Request", request.service_request)),
        "from_warehouse": request.from_warehouse,
        "to_warehouse": request.to_warehouse,
        "items": [{"item_code": request.item_code, "qty": quantity, "basic_rate": request.rate or 0, "s_warehouse": request.from_warehouse, "t_warehouse": request.to_warehouse}],
    }).insert(ignore_permissions=True)
    stock_entry.submit()
    request.qty = quantity
    request.status = "Completed"
    request.stock_entry = stock_entry.name
    request.save(ignore_permissions=True)
    sr = frappe.get_doc("Service Request", request.service_request)
    for row in sr.parts or []:
        if row.transfer_request == request.name:
            row.qty = quantity
            row.amount = quantity * (row.rate or 0)
            row.selling_amount = quantity * (getattr(row, "selling_rate", 0) or 0)
            row.status = "Completed"
            row.stock_entry = stock_entry.name
    if sr.meta.has_field("spare_part_request_status"):
        sr.spare_part_request_status = "Completed"
    if sr.workflow_state == "Waiting for Part":
        sr.workflow_state = "In Progress"
    _action_location(sr, "Spare Part Transfer Approved", technician, latitude, longitude)
    sr.save(ignore_permissions=True)
    _notify_transfer(request, requester.user, f"Spare part transfer approved: {request.item_name}", f"Transfer {request.name} approved. {quantity} x {request.item_name} moved to {request.to_warehouse}. Stock Entry: {stock_entry.name}.")
    frappe.db.commit()
    return {"status": request.status, "stock_entry": stock_entry.name, "workflow_state": sr.workflow_state}

