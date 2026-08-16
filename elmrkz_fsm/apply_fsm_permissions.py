import frappe
from frappe.permissions import add_permission, reset_perms

def apply_permissions():
    # Define roles
    TECH = "FSM Technician"
    MGR = "FSM Manager"

    # DocType: { Role: [perm_level, read, write, create, delete, submit, cancel, amend, report, export, import, print, email, share, set_user_permissions] }
    # Frappe default perm levels are usually 0.
    
    perms = {
        "Service Request": {
            TECH: [0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Technician Profile": {
            TECH: [0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "FSM Settings": {
            MGR:  [0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1]
        },
        "Sales Order": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Sales Invoice": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Stock Entry": {
            TECH: [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Material Request": {
            TECH: [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Notification Log": {
            TECH: [0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0]
        },
        "File": {
            TECH: [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Workspace": {
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Number Card": {
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Dashboard Chart": {
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Calendar View": {
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Warehouse": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Item": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Item Price": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Payment Entry": {
            TECH: [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        },
        "Address": {
            TECH: [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Contact": {
            TECH: [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Communication": {
            TECH: [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        },
        "Mode of Payment": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0]
        },
        "Customer": {
            TECH: [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0],
            MGR:  [0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
        }
    }

    fields = ["permlevel", "read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "print", "email", "share", "set_user_permissions"]

    for doctype, role_perms in perms.items():
        # Clear existing custom perms for these roles on this doctype to avoid duplicates
        frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": ["in", list(role_perms.keys())]})
        
        for role, values in role_perms.items():
            docperm = frappe.get_doc({
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                **{fields[i]: values[i] for i in range(len(fields))}
            })
            docperm.insert(ignore_permissions=True)
            print(f"Applied permissions for {role} on {doctype}")

    frappe.clear_cache(doctype="Service Request")
    frappe.clear_cache(doctype="Technician Profile")
    frappe.clear_cache(doctype="Sales Order")
    frappe.clear_cache(doctype="Sales Invoice")
    frappe.clear_cache(doctype="Stock Entry")
    frappe.clear_cache(doctype="Material Request")
    frappe.db.commit()

if __name__ == "__main__":
    apply_permissions()
