# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Preflight and add controls for the direct Stock Entry approval route."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS

CANONICAL_WORKFLOW = "Connect Stock Transfer Approval"
TASKS = {
    "Connect Stock Transfer Review Snapshot": "Capture Print Action: Checked",
    "Connect Stock Transfer Approval Snapshot": "Capture Print Action: Authorized",
    "Connect Stock Transfer Approval Reset": "Clear Stock Transfer Approval Snapshots",
}
KNOWN_STATES = {
    "Stock Transfer Draft",
    "Stock Transfer Pending Approval",
    "Stock Transfer Pending Review",
    "Stock Transfer Reviewed",
    "Stock Transfer Returned",
    "Stock Transfer Approved",
    "Stock Transfer Rejected",
    "Stock Transfer Submitted",
    "Stock Transfer Cancelled",
    "Stock Entry Submitted",
    "Stock Entry Cancelled",
    "Emergency Stock Movement Pending Review",
    "Emergency Stock Movement Approved",
    "Emergency Stock Movement Rejected",
    "Emergency Stock Movement Submitted",
    "Emergency Stock Movement Cancelled",
}
FIELD_PROPERTIES = (
    "label",
    "fieldtype",
    "options",
    "hidden",
    "read_only",
    "allow_on_submit",
    "no_copy",
    "is_system_generated",
)


def _validate_workflow_collision() -> None:
    active = frappe.get_all(
        "Workflow",
        filters={"document_type": "Stock Entry", "is_active": 1},
        pluck="name",
    )
    unexpected = [name for name in active if name != CANONICAL_WORKFLOW]
    if unexpected:
        frappe.throw(
            _("Stock Entry Workflow collision requires owner disposition: {0}").format(
                ", ".join(unexpected)
            )
        )
    if not frappe.db.exists("Workflow", CANONICAL_WORKFLOW):
        return

    workflow = frappe.get_doc("Workflow", CANONICAL_WORKFLOW)
    if workflow.document_type != "Stock Entry":
        frappe.throw(_("Connect Stock Transfer Approval is owned by an unexpected DocType."))
    unknown_states = [row.state for row in workflow.states if row.state not in KNOWN_STATES]
    if unknown_states:
        frappe.throw(_("Stock Entry Workflow contains unowned states: {0}").format(", ".join(unknown_states)))

    pending_emergency = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": "Stock Entry",
            "status": "Open",
            "workflow_state": ["like", "Emergency Stock Movement%"],
        },
        pluck="name",
    )
    if pending_emergency:
        frappe.throw(
            _("Open Emergency Stock Movement Workflow Actions require owner disposition: {0}").format(
                ", ".join(pending_emergency)
            )
        )


def _ensure_transition_task(name: str, task_name: str) -> None:
    expected = [(task_name, 1, 0)]
    if frappe.db.exists("Workflow Transition Tasks", name):
        doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != expected:
            frappe.throw(
                _("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(name)
            )
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Transition Tasks",
            "name": name,
            "tasks": [{"task": task_name, "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def _validate_custom_field_collisions(fields: list[dict]) -> None:
    for field in fields:
        existing = frappe.db.get_value(
            "Custom Field",
            {"dt": "Stock Entry", "fieldname": field["fieldname"]},
            FIELD_PROPERTIES,
            as_dict=True,
        )
        if not existing:
            continue
        incompatible = [
            property_name
            for property_name in FIELD_PROPERTIES
            if (existing.get(property_name) or 0) != (field.get(property_name) or 0)
        ]
        if incompatible:
            frappe.throw(
                _("Custom Field Stock Entry-{0} conflicts with the approved configuration: {1}").format(
                    field["fieldname"], ", ".join(incompatible)
                )
            )


def execute() -> None:
    _validate_workflow_collision()
    fields = [
        field
        for field in CUSTOM_FIELDS["Stock Entry"]
        if field["fieldname"] in {"approval_critical_digest", "approval_reviewer_user", "approval_authorized_user"}
    ]
    _validate_custom_field_collisions(fields)
    create_custom_fields({"Stock Entry": fields}, update=False, ignore_validate=True)
    for name, task_name in TASKS.items():
        _ensure_transition_task(name, task_name)


def rollback() -> None:
    """Keep additive evidence fields/tasks; configuration rollback uses the reviewed fixture backup."""
    return
