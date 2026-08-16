import frappe
from frappe.model.document import Document


class FSMSparePartRequest(Document):
    def validate(self):
        if self.qty is not None and float(self.qty) <= 0:
            frappe.throw("Quantity must be greater than zero.")
        if self.request_type == "Transfer" and self.from_technician == self.to_technician:
            frappe.throw("Source and target technicians must be different.")
