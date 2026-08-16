import frappe

class TechnicianLocationLog(frappe.model.document.Document):
    def before_insert(self):
        self.flags.ignore_validate = True
