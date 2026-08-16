import frappe


DEFAULT_SCORING_SETTINGS = {
    "proximity_score_distance_km": 50,
    "maximum_open_requests_per_technician": 10,
    "route_suitability_distance_km": 20,
    "completion_rate_lookback_days": 30,
    "new_technician_completion_rate_percent": 50,
    "technician_response_timeout_minutes": 10,
    "queue_backlog_warning_threshold": 25,
    "tracking_stale_after_minutes": 15,
}


DEFAULT_ASSIGNMENT_CRITERIA = [
    ("Geographic Proximity", 1, 25),
    ("Skill Match", 2, 25),
    ("Availability Score", 3, 15),
    ("Workload Balance", 4, 10),
    ("Completion Rate", 5, 10),
    ("Territory Match", 6, 10),
    ("Route Suitability", 7, 5),
]

CRITERION_ALIASES = {
    "القرب الجغرافي من موقع العميل": "Geographic Proximity",
    "تطابق التخصص/المهارة": "Skill Match",
    "توفر الفني": "Availability Score",
    "عدد الطلبات المفتوحة الحالية": "Workload Balance",
    "نسبة الإنجاز السابقة": "Completion Rate",
    "انتماؤه لمنطقة الخدمة": "Territory Match",
    "ملاءمة طريقه مع طلبات أخرى": "Route Suitability",
}


def _canonical_criterion(value):
    return CRITERION_ALIASES.get(value, value)


def after_install():
    seed_defaults()
    _seed_custom_fields()


def after_migrate():
    seed_defaults()
    _seed_custom_fields()


def _seed_custom_fields():
    from elmrkz_fsm.seed_fsm_custom_fields import seed
    seed()


def seed_defaults():
    if not frappe.db.exists("FSM Settings", "FSM Settings"):
        doc = frappe.get_doc(
            {
                "doctype": "FSM Settings",
                "company_latitude": 0,
                "company_longitude": 0,
                "company_radius_km": 25,
                "default_shift_start_time": "08:00:00",
                "default_shift_end_time": "18:00:00",
                "queue_off_shift_orders": 1,
            }
        )
        doc.insert(ignore_permissions=True)

    doc = frappe.get_doc("FSM Settings")
    for fieldname, default in DEFAULT_SCORING_SETTINGS.items():
        if not getattr(doc, fieldname, None):
            doc.set(fieldname, default)

    existing = {_canonical_criterion(row.criterion) for row in doc.assignment_criteria}
    for criterion, priority, weight in DEFAULT_ASSIGNMENT_CRITERIA:
        if criterion not in existing:
            doc.append(
                "assignment_criteria",
                {
                    "criterion": criterion,
                    "priority": priority,
                    "enabled": 1,
                    "weight": weight,
                },
            )
    doc.save(ignore_permissions=True)
    frappe.db.commit()


if __name__ == "__main__":
    seed_defaults()
