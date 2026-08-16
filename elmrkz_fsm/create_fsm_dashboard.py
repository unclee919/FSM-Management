import frappe
from frappe.utils import nowdate

def create_dashboard():
    # 1. Create Number Cards
    cards = [
        {
            "name": "FSM Open Requests",
            "label": "Open Service Requests",
            "document_type": "Service Request",
            "function": "Count",
            "is_public": 1,
            "filters_json": json.dumps([["Service Request", "workflow_state", "not in", ["Completed", "Cancelled", "Rejected"]]]),
            "type": "Document Type"
        },
        {
            "name": "FSM Pending Spare Parts",
            "label": "Pending Spare Part Approvals",
            "document_type": "Service Request",
            "function": "Count",
            "is_public": 1,
            "filters_json": json.dumps([["Service Request", "spare_part_request_status", "=", "Pending Approval"]]),
            "type": "Document Type"
        },
        {
            "name": "FSM Completed Today",
            "label": "Completed Today",
            "document_type": "Service Request",
            "function": "Count",
            "is_public": 1,
            "filters_json": json.dumps([
                ["Service Request", "workflow_state", "=", "Completed"],
                ["Service Request", "modified", ">=", nowdate()]
            ]),
            "type": "Document Type"
        }
    ]

    for card_data in cards:
        if not frappe.db.exists("Number Card", card_data["name"]):
            doc = frappe.get_doc({"doctype": "Number Card", **card_data})
            doc.insert(ignore_permissions=True)
            print(f"Created Number Card: {card_data['name']}")

    # 2. Create Dashboard Charts
    charts = [
        {
            "chart_name": "Service Requests by Status",
            "chart_type": "Group By",
            "document_type": "Service Request",
            "group_by_based_on": "workflow_state",
            "aggregate_function_based_on": "name",
            "type": "Bar",
            "is_public": 1,
            "timeseries": 0,
            "filters_json": json.dumps([["Service Request", "docstatus", "<", 2]])
        },
        {
            "chart_name": "Technician Workload",
            "chart_type": "Group By",
            "document_type": "Service Request",
            "group_by_based_on": "assigned_technician",
            "aggregate_function_based_on": "name",
            "type": "Bar",
            "is_public": 1,
            "timeseries": 0,
            "filters_json": json.dumps([["Service Request", "workflow_state", "not in", ["Completed", "Cancelled", "Rejected"]]])
        }
    ]

    for chart_data in charts:
        if not frappe.db.exists("Dashboard Chart", chart_data["chart_name"]):
            doc = frappe.get_doc({"doctype": "Dashboard Chart", **chart_data})
            doc.insert(ignore_permissions=True)
            print(f"Created Dashboard Chart: {chart_data['chart_name']}")

    # 3. Create Workspace
    workspace_name = "FSM Manager Dashboard"
    if not frappe.db.exists("Workspace", workspace_name):
        workspace = frappe.get_doc({
            "doctype": "Workspace",
            "name": workspace_name,
            "label": "FSM Dashboard",
            "title": "FSM Dashboard",
            "category": "Modules",
            "module": "Elmrkz Fsm",
            "public": 1,
            "roles": [{"role": "FSM Manager"}],
            "content": json.dumps([
                {"type": "header", "data": {"text": "Field Service Management Overview", "level": 2}},
                {"type": "chart", "data": {"chart_name": "Service Requests by Status", "col": 12}},
                {"type": "header", "data": {"text": "Key Metrics", "level": 4}},
                {"type": "number_card", "data": {"number_card_name": "FSM Open Requests", "col": 4}},
                {"type": "number_card", "data": {"number_card_name": "FSM Pending Spare Parts", "col": 4}},
                {"type": "number_card", "data": {"number_card_name": "FSM Completed Today", "col": 4}},
                {"type": "chart", "data": {"chart_name": "Technician Workload", "col": 12}},
                {"type": "header", "data": {"text": "Quick Links", "level": 4}},
                {"type": "shortcut", "data": {"label": "Service Requests", "link_to": "Service Request", "type": "DocType", "col": 3}},
                {"type": "shortcut", "data": {"label": "Technician Profiles", "link_to": "Technician Profile", "type": "DocType", "col": 3}},
                {"type": "shortcut", "data": {"label": "Calendar View", "link_to": "Service Request", "type": "DocType", "view": "Calendar", "col": 3}},
                {"type": "shortcut", "data": {"label": "FSM Settings", "link_to": "FSM Settings", "type": "DocType", "col": 3}}
            ])
        })
        workspace.insert(ignore_permissions=True)
        print(f"Created Workspace: {workspace_name}")
    
    frappe.db.commit()

import json
if __name__ == "__main__":
    create_dashboard()
