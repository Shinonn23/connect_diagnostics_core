# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Idempotent Regulatory roles, permissions, and Product Registration workflow."""

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

from connect_diagnostics_core.setup.customer_onboarding import ensure_workflow

REGULATORY_VIEWER = "Regulatory Viewer"
REGULATORY_OPERATOR = "Regulatory Operator"
REGULATORY_APPROVER = "Regulatory Approver"
MANAGED_ROLES = (REGULATORY_VIEWER, REGULATORY_OPERATOR, REGULATORY_APPROVER)

PRODUCT_REGISTRATION = "Medical Device Product Registration"
ESTABLISHMENT_REGISTRATION = "Medical Device Establishment Registration"
REGULATORY_DOCUMENT = "Medical Device Regulatory Document"
REGISTRATION_ACTION = "Medical Device Registration Action"
REGULATORY_SETTINGS = "Medical Device Regulatory Settings"
REGULATORY_OVERRIDE = "Medical Device Regulatory Override"
REGULATORY_ALERT_LOG = "Medical Device Regulatory Alert Log"
MANAGED_DOCTYPES = (
    ESTABLISHMENT_REGISTRATION,
    PRODUCT_REGISTRATION,
    REGULATORY_DOCUMENT,
    REGISTRATION_ACTION,
    REGULATORY_SETTINGS,
    REGULATORY_OVERRIDE,
    REGULATORY_ALERT_LOG,
)

WORKFLOW_NAME = "Medical Device Product Registration Approval"
WORKFLOW_STATE_FIELD = "regulatory_workflow_state"
WORKFLOW_STATES = {
    "Registration Draft": "Info",
    "Registration Data Verification": "Warning",
    "Registration Active": "Success",
    "Registration Superseded": "Dark",
    "Registration Cancelled": "Danger",
}
WORKFLOW_ACTIONS = (
    "Submit for verification",
    "Activate registration",
    "Supersede registration",
    "Cancel registration",
)
WORKFLOW_DOCUMENT_STATES = (
    {
        "state": "Registration Draft",
        "doc_status": "0",
        "allow_edit": REGULATORY_OPERATOR,
        "update_field": "official_status",
        "update_value": "Draft",
    },
    {
        "state": "Registration Data Verification",
        "doc_status": "0",
        "allow_edit": REGULATORY_APPROVER,
        "update_field": "official_status",
        "update_value": "Draft",
    },
    {
        "state": "Registration Active",
        "doc_status": "0",
        "allow_edit": REGULATORY_APPROVER,
        "update_field": "official_status",
        "update_value": "Active",
    },
    {
        "state": "Registration Superseded",
        "doc_status": "0",
        "allow_edit": REGULATORY_APPROVER,
        "update_field": "official_status",
        "update_value": "Superseded",
    },
    {
        "state": "Registration Cancelled",
        "doc_status": "0",
        "allow_edit": REGULATORY_APPROVER,
        "update_field": "official_status",
        "update_value": "Cancelled",
    },
)
WORKFLOW_TRANSITIONS = (
    {
        "state": "Registration Draft",
        "action": "Submit for verification",
        "next_state": "Registration Data Verification",
        "allowed": REGULATORY_OPERATOR,
    },
    {
        "state": "Registration Data Verification",
        "action": "Activate registration",
        "next_state": "Registration Active",
        "allowed": REGULATORY_APPROVER,
    },
    {
        "state": "Registration Active",
        "action": "Supersede registration",
        "next_state": "Registration Superseded",
        "allowed": REGULATORY_APPROVER,
    },
    {
        "state": "Registration Active",
        "action": "Cancel registration",
        "next_state": "Registration Cancelled",
        "allowed": REGULATORY_APPROVER,
    },
)

PERMISSION_FIELDS = (
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "share",
    "print",
    "email",
)
VIEWER_PERMISSIONS = {"read": 1, "report": 1, "export": 1, "print": 1, "email": 1}
OPERATOR_PERMISSIONS = {**VIEWER_PERMISSIONS, "create": 1, "write": 1}
APPROVER_PERMISSIONS = {**OPERATOR_PERMISSIONS, "delete": 1, "share": 1}


def ensure_configuration() -> None:
    """Create the complete Regulatory setup without assigning users or owners."""
    ensure_roles()
    ensure_permissions()
    ensure_workflow_masters()
    ensure_settings()
    ensure_workflow(
        workflow_name=WORKFLOW_NAME,
        document_type=PRODUCT_REGISTRATION,
        workflow_state_field=WORKFLOW_STATE_FIELD,
        states=WORKFLOW_DOCUMENT_STATES,
        transitions=WORKFLOW_TRANSITIONS,
        send_email_alert=0,
        is_active=1,
    )
    for doctype in MANAGED_DOCTYPES:
        frappe.clear_cache(doctype=doctype)


def ensure_settings() -> None:
    """Seed expiry thresholds only for a previously unconfigured site."""
    if frappe.db.exists("Singles", {"doctype": REGULATORY_SETTINGS}):
        return
    settings = cast(Document, frappe.get_single(REGULATORY_SETTINGS))
    for days, severity, action in (
        (365, "Info", "Create Renewal Action"),
        (180, "Info", "Reminder"),
        (120, "Warning", "Internal Review Reminder"),
        (60, "Warning", "Escalate"),
        (30, "Critical", "Escalate Affected Teams"),
        (14, "Critical", "Weekly Reminder"),
        (7, "Critical", "Daily Reminder"),
        (0, "Expired", "Trigger Compliance Check"),
    ):
        settings.append(
            "expiry_alert_rules",
            {"days_before_expiry": days, "severity": severity, "action": action},
        )
    settings.save(ignore_permissions=True)


def ensure_roles() -> None:
    for role_name in MANAGED_ROLES:
        if frappe.db.exists("Role", role_name):
            role = frappe.get_doc("Role", role_name)
            if role.get("disabled") or not role.get("desk_access") or not role.get("is_custom"):
                role.update({"disabled": 0, "desk_access": 1, "is_custom": 1})
                role.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {"doctype": "Role", "role_name": role_name, "disabled": 0, "desk_access": 1, "is_custom": 1}
        ).insert(ignore_permissions=True)


def ensure_permissions() -> None:
    for doctype in MANAGED_DOCTYPES:
        setup_custom_perms(doctype)
        _ensure_permission(doctype, REGULATORY_VIEWER, VIEWER_PERMISSIONS)
        _ensure_permission(doctype, REGULATORY_OPERATOR, OPERATOR_PERMISSIONS)
        _ensure_permission(doctype, REGULATORY_APPROVER, APPROVER_PERMISSIONS)


def _ensure_permission(doctype: str, role: str, desired: dict[str, int]) -> None:
    matches = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": 0},
        pluck="name",
        order_by="creation asc",
    )
    permission = (
        frappe.get_doc("Custom DocPerm", matches[0])
        if matches
        else frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "role": role, "permlevel": 0})
    )
    for duplicate in matches[1:]:
        frappe.delete_doc("Custom DocPerm", duplicate, force=True, ignore_permissions=True)
    values = {fieldname: desired.get(fieldname, 0) for fieldname in PERMISSION_FIELDS}
    if not permission.is_new() and all(
        permission.get(fieldname) == value for fieldname, value in values.items()
    ):
        return
    permission.update(values)
    if permission.is_new():
        permission.insert(ignore_permissions=True)
    else:
        permission.save(ignore_permissions=True)


def ensure_workflow_masters() -> None:
    for state_name, style in WORKFLOW_STATES.items():
        if frappe.db.exists("Workflow State", state_name):
            state = frappe.get_doc("Workflow State", state_name)
            if state.get("style") != style:
                state.set("style", style)
                state.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {"doctype": "Workflow State", "workflow_state_name": state_name, "style": style}
        ).insert(ignore_permissions=True)
    for action_name in WORKFLOW_ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action_name}).insert(
                ignore_permissions=True
            )
