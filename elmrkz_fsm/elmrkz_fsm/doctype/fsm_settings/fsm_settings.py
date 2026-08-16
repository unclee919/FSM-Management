import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class FSMSettings(Document):
    def validate(self):
        total = sum((row.weight or 0) for row in self.assignment_criteria if row.enabled)
        if round(total, 6) != 100:
            frappe.throw(
                f"Enabled assignment criterion weights must total exactly 100%; current total is {total}"
            )

        for fieldname, label in (
            ("proximity_score_distance_km", "Proximity Score Distance"),
            ("maximum_open_requests_per_technician", "Maximum Open Requests per Technician"),
            ("route_suitability_distance_km", "Route Suitability Distance"),
            ("completion_rate_lookback_days", "Completion Rate Lookback"),
            ("technician_response_timeout_minutes", "Technician Response Timeout"),
            ("queue_backlog_warning_threshold", "Queue Backlog Warning Threshold"),
            ("tracking_stale_after_minutes", "Tracking Stale After"),
        ):
            if flt(self.get(fieldname)) <= 0:
                frappe.throw(f"{label} must be greater than zero")

        baseline = flt(self.get("new_technician_completion_rate_percent"))
        if baseline < 0 or baseline > 100:
            frappe.throw("New Technician Completion Rate must be between 0 and 100")

        validate_whatsapp_defaults(self)


def validate_whatsapp_defaults(settings):
    """Validate the settings required to create WhatsApp Sales Orders.

    This is shared by the DocType save hook and the ingestion endpoint so an
    existing invalid record cannot bypass the same rules through the API.
    Validation is enforced when WhatsApp order ingestion is enabled.
    """
    if not cint(settings.get("enable_whatsapp_order_ingestion")):
        return

    service_fee = flt(settings.get("whatsapp_default_service_fee"))
    if service_fee <= 0:
        frappe.throw("Default Service Visit Fee must be greater than zero when WhatsApp Order Ingestion is enabled")

    company = settings.get("whatsapp_default_company")
    if not company:
        frappe.throw("Default Company is required when WhatsApp Order Ingestion is enabled")
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Default Company '{company}' does not exist")

    warehouse = settings.get("whatsapp_default_warehouse")
    if not warehouse:
        frappe.throw("Default Warehouse is required when WhatsApp Order Ingestion is enabled")

    warehouse_row = frappe.db.get_value(
        "Warehouse",
        warehouse,
        ["company", "is_group", "disabled"],
        as_dict=True,
    )
    if not warehouse_row:
        frappe.throw(f"Default Warehouse '{warehouse}' does not exist")
    if cint(warehouse_row.disabled):
        frappe.throw(f"Default Warehouse '{warehouse}' is disabled")
    if cint(warehouse_row.is_group):
        frappe.throw(f"Default Warehouse '{warehouse}' is a group warehouse and cannot receive Sales Order items")
    if warehouse_row.company != company:
        frappe.throw(
            f"Default Warehouse '{warehouse}' belongs to company '{warehouse_row.company}', not '{company}'"
        )

    item_code = settings.get("whatsapp_default_item_code")
    if not item_code:
        frappe.throw("Default Service Item is required when WhatsApp Order Ingestion is enabled")

    item_row = frappe.db.get_value("Item", item_code, ["disabled"], as_dict=True)
    if not item_row:
        frappe.throw(f"Default Service Item '{item_code}' does not exist")
    if cint(item_row.disabled):
        frappe.throw(f"Default Service Item '{item_code}' is disabled")

    return {
        "company": company,
        "warehouse": warehouse,
        "item_code": item_code,
        "service_fee": service_fee,
    }


# Backward-compatible alias for callers that use a descriptive name.
validate_whatsapp_order_settings = validate_whatsapp_defaults
