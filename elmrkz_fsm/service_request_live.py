"""Deprecated compatibility surface for the former live Service Request handler.

Canonical implementation: ``elmrkz_fsm.elmrkz_fsm.doctype.service_request.service_request``.
The exported functions deliberately retain this module's historical dotted paths
until all remote callers and legacy browser assets have migrated.
"""

import frappe

from elmrkz_fsm.elmrkz_fsm.doctype.service_request import service_request as _canonical

ServiceRequest = _canonical.ServiceRequest
_normalize_payment_method = _canonical._normalize_payment_method
_get_assigned_technician_for_session = _canonical._get_assigned_technician_for_session
_technician_owns_request = _canonical._technician_owns_request
_valid_coordinate_pair = _canonical._valid_coordinate_pair
_append_action_location = _canonical._append_action_location


@frappe.whitelist()
def get_pending_assignments():
    return _canonical.get_pending_assignments()


@frappe.whitelist()
def get_assignment_notification(notification_name=None, document_name=None):
    return _canonical.get_assignment_notification(
        notification_name=notification_name,
        document_name=document_name,
    )


@frappe.whitelist()
def accept_assignment(name, latitude=None, longitude=None):
    return _canonical.accept_assignment(
        name=name,
        latitude=latitude,
        longitude=longitude,
    )


@frappe.whitelist()
def reject_assignment(name, reason=None, latitude=None, longitude=None):
    return _canonical.reject_assignment(
        name=name,
        reason=reason,
        latitude=latitude,
        longitude=longitude,
    )


def validate_service_request(doc, method=None):
    return _canonical.validate_service_request(doc, method=method)
