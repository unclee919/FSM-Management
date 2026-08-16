import frappe

class ServiceRequestPart(frappe.model.document.Document):
    def validate(self):
        self.amount = (self.qty or 0) * (self.rate or 0)
