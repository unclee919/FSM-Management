import frappe
from frappe.utils import cint, flt, now_datetime, nowdate
from elmrkz_fsm.elmrkz_fsm.doctype.service_request.service_request import ServiceRequest

ALLOWED_PAYMENT_METHODS = {"Cash", "Transfer"}

def _normalize_payment_method(val):
    if not val:
        return "Cash"
    s = str(val).strip()
    if s.lower() in ("transfer", "bank transfer", "online", "wire"):
        return "Transfer"
    return "Cash"

def _manager_or_technician(doc):
    user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return doc.assigned_technician or user
    tech = frappe.db.get_value("Technician Profile", {"user": user}, "name")
    if not tech:
        frappe.throw("Only assigned technicians or System Managers can complete service requests.", frappe.PermissionError)
    if doc.assigned_technician and doc.assigned_technician != tech:
        frappe.throw(f"This service request is assigned to {doc.assigned_technician}, not you.", frappe.PermissionError)
    return tech

def _profile(technician):
    if frappe.db.exists("Technician Profile", technician):
        return frappe.get_doc("Technician Profile", technician)
    profile_name = frappe.db.get_value("Technician Profile", {"user": technician}, "name")
    if profile_name:
        return frappe.get_doc("Technician Profile", profile_name)
    frappe.throw(f"No Technician Profile found for {technician}.", frappe.ValidationError)

def _item(item_code, require_stock=False):
    if not frappe.db.exists("Item", item_code):
        frappe.throw(f"Item {item_code} does not exist in ERPNext.", frappe.ValidationError)
    item = frappe.get_doc("Item", item_code)
    if cint(item.disabled):
        frappe.throw(f"Item {item_code} is disabled.", frappe.ValidationError)
    if require_stock and cint(item.is_stock_item) == 0 and cint(item.is_service_item) == 0:
        frappe.throw(f"Item {item_code} must be a stock or service item.", frappe.ValidationError)
    return item

def _valid_number(val, label, allow_zero=True):
    try:
        num = float(val)
    except (TypeError, ValueError):
        frappe.throw(f"{label} must be a valid number.", frappe.ValidationError)
    if not allow_zero and num <= 0:
        frappe.throw(f"{label} must be greater than zero.", frappe.ValidationError)
    if allow_zero and num < 0:
        frappe.throw(f"{label} cannot be negative.", frappe.ValidationError)
    return num

def _action_location(doc, action, technician, latitude, longitude):
    if latitude is not None and longitude is not None:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            lat, lon = 0.0, 0.0
        if doc.meta.has_field("action_locations"):
            doc.append("action_locations", {
                "action": action,
                "technician": technician,
                "timestamp": now_datetime(),
                "latitude": lat,
                "longitude": lon,
            })

def _create_invoice(doc, technician, service_rate, normalized_parts, payment_method, payment_proof):
    company = doc.company or frappe.defaults.get_defaults().get("company")
    if not company:
        frappe.throw("Company is required to create a Sales Invoice.", frappe.ValidationError)
    currency = doc.currency or frappe.get_cached_value("Company", company, "default_currency") or "EGP"
    price_list = doc.price_list or "Standard Selling"
    warehouse = _profile(technician).van_warehouse
    if not warehouse:
        frappe.throw(f"Technician {technician} has no Van Warehouse assigned.", frappe.ValidationError)

    settings = frappe.get_single("FSM Settings")
    service_item_code = settings.whatsapp_default_item_code or "FSM Service Visit"
    _item(service_item_code)

    items = [{
        "item_code": service_item_code,
        "qty": 1,
        "rate": service_rate,
        "amount": service_rate,
        "warehouse": warehouse,
    }]
    for p in normalized_parts:
        items.append({
            "item_code": p["item_code"],
            "qty": p["qty"],
            "rate": p["selling_rate"],
            "amount": p["selling_amount"],
            "warehouse": warehouse,
        })

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = doc.customer
    invoice.company = company
    invoice.currency = currency
    invoice.selling_price_list = price_list
    invoice.set_posting_time = 1
    invoice.posting_date = nowdate()
    for row in items:
        invoice.append("items", row)
    invoice.insert(ignore_permissions=True)
    if cint(settings.whatsapp_auto_submit_order) or invoice.docstatus == 0:
        try:
            invoice.submit()
        except Exception:
            pass
    return invoice

def _apply_selling_rates(doc, invoice_lines):
    if not invoice_lines:
        return
    try:
        lines = frappe.parse_json(invoice_lines) if isinstance(invoice_lines, str) else invoice_lines
    except Exception:
        return
    for row in doc.get("items", []):
        for line in lines:
            if line.get("item_code") == row.item_code:
                qty = flt(line.get("qty", row.qty))
                selling_rate = flt(line.get("selling_rate", row.rate))
                row.qty = qty
                row.rate = selling_rate
                row.amount = qty * selling_rate

@frappe.whitelist()
def complete_service_request(name, service_item_code=None, service_rate=0, parts=None, payment_method=None, payment_proof=None, latitude=None, longitude=None, invoice_lines=None):
    doc = frappe.get_doc("Service Request", name)
    technician = _manager_or_technician(doc)
    if doc.workflow_state != "In Progress":
        frappe.throw("Complete is available only while the request is In Progress.", frappe.ValidationError)

    # Enforce Technician Report requirement if configured in FSM Settings
    settings = frappe.get_single("FSM Settings")
    if getattr(settings, "require_technician_report_on_complete", 0):
        report_exists = frappe.db.exists("Technician Report", {"service_request": doc.name, "docstatus": ["!=", 2]})
        if not report_exists:
        # Check if a report was submitted in the same session or attached
            frappe.throw("A submitted Technician Report is required before completing this Service Request.", frappe.ValidationError)

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
