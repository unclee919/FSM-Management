import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime


def _status(ok, attention_label=_("Attention")):
    return _("Healthy") if ok else attention_label


def _queue_health(settings):
    rows = []
    try:
        from frappe.utils.background_jobs import get_queues, get_redis_conn
        from rq import Worker

        connection = get_redis_conn()
        queues = get_queues(connection)
        workers = Worker.all(connection=connection)
        warning_threshold = int(settings.queue_backlog_warning_threshold or 25)
        rows.append(
            {
                "component": _("Redis Queue"),
                "status": _("Healthy"),
                "current_value": _("Connected"),
                "threshold": "",
                "details": _("{0} active worker(s) detected.").format(len(workers)),
            }
        )
        rows.append(
            {
                "component": _("Background Workers"),
                "status": _status(bool(workers)),
                "current_value": len(workers),
                "threshold": _("At least 1"),
                "details": _("RQ workers reachable through the configured Redis queue."),
            }
        )
        for queue in queues:
            depth = queue.count
            rows.append(
                {
                    "component": _("Queue: {0}").format(queue.name),
                    "status": _status(depth < warning_threshold),
                    "current_value": depth,
                    "threshold": warning_threshold,
                    "details": _("Queued jobs awaiting execution."),
                }
            )
    except Exception as error:
        rows.append(
            {
                "component": _("Redis Queue"),
                "status": _("Error"),
                "current_value": _("Unavailable"),
                "threshold": "",
                "details": frappe.as_unicode(error),
            }
        )
    return rows


def _scheduler_health():
    from frappe.utils.scheduler import is_scheduler_inactive

    inactive = is_scheduler_inactive(verbose=False)
    job_meta = frappe.get_meta("Scheduled Job Type")
    fields = ["name", "method", "frequency"]
    if job_meta.has_field("last_execution"):
        fields.append("last_execution")
    jobs = frappe.get_all(
        "Scheduled Job Type",
        filters={"method": ["like", "elmrkz_fsm.%"]},
        fields=fields,
    )
    detail = _("{0} FSM scheduled job definition(s) found.").format(len(jobs))
    if jobs and "last_execution" in fields:
        latest = max((job.last_execution for job in jobs if job.last_execution), default=None)
        if latest:
            detail = _("{0} FSM scheduled job definition(s); latest execution: {1}.").format(len(jobs), latest)
    return {
        "component": _("Frappe Scheduler"),
        "status": _status(not inactive),
        "current_value": _("Enabled") if not inactive else _("Inactive"),
        "threshold": "",
        "details": detail,
    }


def _tracking_health(settings):
    stale_after = int(settings.tracking_stale_after_minutes or 15)
    cutoff = add_to_date(now_datetime(), minutes=-stale_after)
    active_states = ["Assigned", "Accepted", "Customer Confirmed", "On the Way", "In Progress"]
    active_requests = frappe.get_all(
        "Service Request",
        filters={"workflow_state": ["in", active_states], "assigned_technician": ["is", "set"]},
        fields=["name", "assigned_technician"],
    )
    technicians = {request.assigned_technician for request in active_requests if request.assigned_technician}
    if not technicians:
        return {
            "component": _("Technician Tracking Freshness"),
            "status": _("Healthy"),
            "current_value": 0,
            "threshold": stale_after,
            "details": _("No technician currently has an active assigned request."),
        }
    profiles = frappe.get_all(
        "Technician Profile",
        filters={"name": ["in", list(technicians)]},
        fields=["name", "last_ping_time"],
    )
    stale = [profile.name for profile in profiles if not profile.last_ping_time or profile.last_ping_time < cutoff]
    return {
        "component": _("Technician Tracking Freshness"),
        "status": _status(not stale),
        "current_value": _("{0} stale of {1} active").format(len(stale), len(technicians)),
        "threshold": _("{0} minutes").format(stale_after),
        "details": _("Stale technician profile(s): {0}").format(", ".join(stale) if stale else _("None")),
    }


def _assignment_health(settings):
    response_timeout = int(settings.technician_response_timeout_minutes or 10)
    cutoff = add_to_date(now_datetime(), minutes=-response_timeout)
    overdue = frappe.db.count(
        "Service Request",
        filters={"workflow_state": "Assigned", "assigned_at": ["<", cutoff]},
    )
    without_timestamp = frappe.db.count(
        "Service Request",
        filters={"workflow_state": "Assigned", "assigned_at": ["is", "not set"]},
    )
    average_minutes = frappe.db.sql(
        """
        select round(avg(timestampdiff(minute, assigned_at, now())), 1)
        from `tabService Request`
        where workflow_state = 'Assigned' and assigned_at is not null
        """,
        as_list=True,
    )[0][0]
    detail = _("{0} assigned request(s) exceed the response timeout.").format(overdue)
    if without_timestamp:
        detail += " " + _("{0} legacy assigned request(s) have no assignment timestamp.").format(without_timestamp)
    return {
        "component": _("Assignment Response Latency"),
        "status": _status(not overdue),
        "current_value": _("Average age: {0} minutes; overdue: {1}").format(average_minutes or 0, overdue),
        "threshold": _("{0} minutes").format(response_timeout),
        "details": detail,
    }


def execute(filters=None):
    settings = frappe.get_doc("FSM Settings")
    columns = [
        {"fieldname": "component", "label": _("Component"), "fieldtype": "Data", "width": 230},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "current_value", "label": _("Current Value"), "fieldtype": "Data", "width": 190},
        {"fieldname": "threshold", "label": _("Threshold"), "fieldtype": "Data", "width": 150},
        {"fieldname": "details", "label": _("Details"), "fieldtype": "Data", "width": 520},
    ]
    data = _queue_health(settings)
    data.append(_scheduler_health())
    data.append(_tracking_health(settings))
    data.append(_assignment_health(settings))
    return columns, data
