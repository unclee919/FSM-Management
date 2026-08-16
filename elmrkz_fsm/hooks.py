app_name = "elmrkz_fsm"
app_title = "Elmrkz Field Service Management"
app_publisher = "Elmrkz"
app_description = "Secure configurable field service management"
app_email = "admin@elmrkz.cloud"
app_license = "mit"
fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["FSM Technician", "FSM Manager"]]]},
    {"dt": "Custom DocPerm", "filters": [["role", "in", ["FSM Technician", "FSM Manager"]]]},
    {"dt": "Workspace", "filters": [["name", "in", ["FSM Dashboard", "FSM Management", "FSM Technical"]]]},
    {"dt": "Custom Field", "filters": [["module", "=", "Elmrkz Fsm"]]},
    {"dt": "Number Card", "filters": [["name", "in", ["Open Service Requests", "Pending Spare Part Approvals", "Completed Today"]]]},
    {"dt": "Dashboard Chart", "filters": [["chart_name", "in", ["Service Requests by Status", "Technician Workload"]]]},
    {"dt": "Calendar View", "filters": [["name", "=", "Service Request Calendar"]]}
]
doc_events = {
    "Service Request": {
        "validate": "elmrkz_fsm.elmrkz_fsm.doctype.service_request.service_request.validate_service_request",
    },
    "Sales Order": {
        "on_submit": "elmrkz_fsm.sales_order.create_service_request_from_sales_order",
    },
}
permission_query_conditions = {
    "Service Request": "elmrkz_fsm.permissions.service_request_query",
    "Technician Profile": "elmrkz_fsm.permissions.technician_profile_query",
}
has_permission = {
    "Service Request": "elmrkz_fsm.permissions.service_request_has_permission",
    "Technician Profile": "elmrkz_fsm.permissions.technician_profile_has_permission",
}
scheduler_events = {
    "hourly": [
        "elmrkz_fsm.fsm_actions.expire_tracking_links",
        "elmrkz_fsm.assignment.assign_queued_service_requests",
    ],
    "cron": {
        "*/5 * * * *": [
            "elmrkz_fsm.fsm_actions.check_arrival_proximity",
        ],
    },
}
after_migrate = "elmrkz_fsm.install.after_migrate"
doctype_js = {
    "Service Request": "public/js/service_request_v7.js",
    "Technician Profile": "public/js/technician_profile.js",
}
app_include_js = [
    "/assets/elmrkz_fsm/js/fsm_notifications_v5.js",
    "/assets/elmrkz_fsm/js/fsm_location_tracker.js",
]
