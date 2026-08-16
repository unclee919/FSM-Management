import frappe
import json
import os

def sync_permissions():
    doctypes = [
        "Service Request",
        "Technician Profile",
        "FSM Settings",
        "Technician Location Log",
        "FSM Spare Part Request",
        "FSM Assignment Criterion",
        "Technician Skill"
    ]
    
    app_path = "/home/frappe/frappe-bench/apps/elmrkz_fsm/elmrkz_fsm/elmrkz_fsm/doctype"
    
    for dt_name in doctypes:
        # Get permissions from Custom DocPerm (which are the latest)
        custom_perms = frappe.get_all("Custom DocPerm", filters={"parent": dt_name}, fields="*")
        if not custom_perms:
            continue
            
        # Clean up perms for JSON (remove DB-specific fields)
        cleaned_perms = []
        for p in custom_perms:
            p_dict = p.copy()
            for key in ["name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "idx", "docstatus"]:
                p_dict.pop(key, None)
            cleaned_perms.append(p_dict)
            
        # Find the JSON file
        folder_name = frappe.scrub(dt_name)
        json_path = os.path.join(app_path, folder_name, f"{folder_name}.json")
        
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
            
            data["permissions"] = cleaned_perms
            
            with open(json_path, "w") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            print(f"Synced permissions for {dt_name} to {json_path}")
        else:
            print(f"JSON not found for {dt_name} at {json_path}")

if __name__ == "__main__":
    sync_permissions()
