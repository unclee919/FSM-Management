import frappe
import json

def verify_permissions():
    TECH_USER = "tech@elmrkz.cloud"
    MGR_USER = "Administrator" # Or another manager user if available
    
    doctypes = ["Service Request", "Technician Profile", "FSM Settings", "Sales Order", "Sales Invoice", "Stock Entry", "Material Request"]
    results = {"FSM Technician": {}, "FSM Manager": {}}

    def check_user_perms(user, role_name):
        frappe.set_user(user)
        user_results = {}
        for dt in doctypes:
            user_results[dt] = {
                "read": frappe.has_permission(dt, "read"),
                "write": frappe.has_permission(dt, "write"),
                "create": frappe.has_permission(dt, "create"),
                "submit": frappe.has_permission(dt, "submit")
            }
        return user_results

    # Check Technician
    results["FSM Technician"] = check_user_perms(TECH_USER, "FSM Technician")
    
    # Check Manager
    results["FSM Manager"] = check_user_perms(MGR_USER, "FSM Manager")

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    verify_permissions()
