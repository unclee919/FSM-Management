import frappe
from frappe.model.document import Document


class TechnicianReport(Document):
    def validate(self):
        if not self.posting_date:
            self.posting_date = frappe.utils.nowdate()
        if self.service_request and not self.customer:
            self.customer = frappe.db.get_value("Service Request", self.service_request, "customer")
