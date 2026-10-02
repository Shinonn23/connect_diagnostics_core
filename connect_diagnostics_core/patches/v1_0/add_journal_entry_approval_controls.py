# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install additive evidence fields for the native Journal Entry workflow."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS

WORKFLOW_NAME = "Connect Journal Entry Approval"
TRANSITION_TASKS = {
    "Connect Journal Entry Capture Maker": "Capture Journal Entry Maker",
    "Connect Journal Entry Capture Checker": "Capture Journal Entry Checker",
    "Connect Journal Entry Capture Approver": "Capture Journal Entry Approver",
    "Connect Journal Entry Clear Approval": "Clear Journal Entry Approval",
    "Connect Journal Entry Submit Execution": "Authorize Journal Entry Submit",
    "Connect Journal Entry Cancel Execution": "Authorize Journal Entry Cancel",
}
EXPECTED_STATES = {
    "Journal Entry Draft",
    "Journal Entry Pending Review",
    "Journal Entry Reviewed",
    "Journal Entry Approved",
    "Journal Entry Returned",
    "Journal Entry Rejected",
    "Journal Entry Submitted",
    "Journal Entry Cancelled",
}
EXPECTED_ACTIONS = {
    "Send Journal Entry for Review",
    "Review Journal Entry",
    "Return Journal Entry",
    "Approve Journal Entry",
    "Reject Journal Entry",
    "Resubmit Journal Entry for Review",
    "Submit Journal Entry",
    "Cancel Journal Entry",
}
EXPECTED_STATE_FINGERPRINT = {
    ("Journal Entry Draft", "0", "Accounts User"),
    ("Journal Entry Pending Review", "0", "Accounts Manager"),
    ("Journal Entry Reviewed", "0", "C-Level Approver"),
    ("Journal Entry Approved", "0", "C-Level Approver"),
    ("Journal Entry Returned", "0", "Accounts User"),
    ("Journal Entry Rejected", "0", "C-Level Approver"),
    ("Journal Entry Submitted", "1", "Accounts Manager"),
    ("Journal Entry Cancelled", "2", "Accounts Manager"),
}
EXPECTED_TRANSITION_FINGERPRINT = {
    (
        "Journal Entry Draft",
        "Send Journal Entry for Review",
        "Journal Entry Pending Review",
        "Accounts User",
        1,
        "Connect Journal Entry Capture Maker",
    ),
    (
        "Journal Entry Pending Review",
        "Review Journal Entry",
        "Journal Entry Reviewed",
        "Accounts Manager",
        0,
        "Connect Journal Entry Capture Checker",
    ),
    (
        "Journal Entry Pending Review",
        "Return Journal Entry",
        "Journal Entry Returned",
        "Accounts Manager",
        0,
        "Connect Journal Entry Clear Approval",
    ),
    (
        "Journal Entry Reviewed",
        "Approve Journal Entry",
        "Journal Entry Approved",
        "C-Level Approver",
        0,
        "Connect Journal Entry Capture Approver",
    ),
    (
        "Journal Entry Reviewed",
        "Return Journal Entry",
        "Journal Entry Returned",
        "C-Level Approver",
        0,
        "Connect Journal Entry Clear Approval",
    ),
    (
        "Journal Entry Reviewed",
        "Reject Journal Entry",
        "Journal Entry Rejected",
        "C-Level Approver",
        0,
        "",
    ),
    (
        "Journal Entry Approved",
        "Return Journal Entry",
        "Journal Entry Returned",
        "C-Level Approver",
        0,
        "Connect Journal Entry Clear Approval",
    ),
    (
        "Journal Entry Returned",
        "Resubmit Journal Entry for Review",
        "Journal Entry Pending Review",
        "Accounts User",
        1,
        "Connect Journal Entry Capture Maker",
    ),
    (
        "Journal Entry Approved",
        "Submit Journal Entry",
        "Journal Entry Submitted",
        "Accounts Manager",
        0,
        "Connect Journal Entry Submit Execution",
    ),
    (
        "Journal Entry Submitted",
        "Cancel Journal Entry",
        "Journal Entry Cancelled",
        "Accounts Manager",
        0,
        "Connect Journal Entry Cancel Execution",
    ),
}


def _fields() -> dict[str, Any]:
    return {"Journal Entry": CUSTOM_FIELDS["Journal Entry"]}


def _preflight() -> None:
    conflicts = []
    workflow_state = frappe.db.get_value(
        "Custom Field",
        {"dt": "Journal Entry", "fieldname": "workflow_state"},
        [
            "fieldtype",
            "options",
            "hidden",
            "allow_on_submit",
            "no_copy",
            "is_system_generated",
            "ignore_user_permissions",
        ],
        as_dict=True,
    )
    if workflow_state and (
        workflow_state.fieldtype,
        workflow_state.options or "",
        int(workflow_state.hidden or 0),
        int(workflow_state.allow_on_submit or 0),
        int(workflow_state.no_copy or 0),
        int(workflow_state.is_system_generated or 0),
        int(workflow_state.ignore_user_permissions or 0),
    ) != ("Link", "Workflow State", 1, 1, 1, 1, 1):
        conflicts.append("workflow_state")
    for definition in CUSTOM_FIELDS["Journal Entry"]:
        name = str(definition["fieldname"])
        if name == "workflow_state":
            continue
        row = frappe.db.get_value(
            "Custom Field",
            {"dt": "Journal Entry", "fieldname": name},
            [
                "fieldtype",
                "options",
                "hidden",
                "read_only",
                "allow_on_submit",
                "no_copy",
                "is_system_generated",
                "unique",
                "ignore_user_permissions",
            ],
            as_dict=True,
        )
        if row and (
            row.fieldtype,
            row.options or "",
            int(row.hidden or 0),
            int(row.read_only or 0),
            int(row.allow_on_submit or 0),
            int(row.no_copy or 0),
            int(row.is_system_generated or 0),
            int(row.unique or 0),
            int(row.ignore_user_permissions or 0),
        ) != (
            definition["fieldtype"],
            definition.get("options") or "",
            int(definition.get("hidden") or 0),
            int(definition.get("read_only") or 0),
            int(definition.get("allow_on_submit") or 0),
            int(definition.get("no_copy") or 0),
            int(definition.get("is_system_generated") or 0),
            int(definition.get("unique") or 0),
            int(definition.get("ignore_user_permissions") or 0),
        ):
            conflicts.append(name)
    workflows = frappe.get_all(
        "Workflow",
        filters={"document_type": "Journal Entry"},
        fields=["name", "is_active"],
    )
    collisions = [row.name for row in workflows if row.name != WORKFLOW_NAME]
    if collisions:
        frappe.throw(_("Journal Entry Workflow collision: {0}").format(", ".join(sorted(collisions))))
    owned_exists = bool(frappe.db.exists("Workflow", WORKFLOW_NAME))
    if owned_exists:
        workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
        states = {row.state for row in workflow.states}
        actions = {row.action for row in workflow.transitions}
        state_fingerprint = {
            (row.state, str(row.doc_status), row.allow_edit or "") for row in workflow.states
        }
        transition_fingerprint = {
            (
                row.state,
                row.action,
                row.next_state,
                row.allowed,
                int(row.allow_self_approval or 0),
                row.transition_tasks or "",
            )
            for row in workflow.transitions
        }
        if (
            workflow.document_type != "Journal Entry"
            or states != EXPECTED_STATES
            or actions != EXPECTED_ACTIONS
            or state_fingerprint != EXPECTED_STATE_FINGERPRINT
            or transition_fingerprint != EXPECTED_TRANSITION_FINGERPRINT
        ):
            frappe.throw(
                _("{0} conflicts with the approved configuration fingerprint.").format(WORKFLOW_NAME)
            )
    if frappe.db.exists("Workflow Action", {"reference_doctype": "Journal Entry", "status": "Open"}):
        frappe.throw(_("Journal Entry approval has open Workflow Actions"))
    populations = {status: frappe.db.count("Journal Entry", {"docstatus": status}) for status in (0, 1, 2)}
    if not owned_exists and any(populations.values()):
        frappe.throw(
            _(
                "Journal Entry approval activation requires an empty target or an approved legacy disposition; "
                "found draft={0}, submitted={1}, cancelled={2}."
            ).format(populations[0], populations[1], populations[2])
        )
    for name, task_name in TRANSITION_TASKS.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            continue
        task_doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in task_doc.tasks]
        if actual != [(task_name, 1, 0)]:
            conflicts.append(name)
    if conflicts:
        frappe.throw(_("Journal Entry approval field collision: {0}").format(", ".join(conflicts)))


def _ensure_transition_tasks() -> None:
    for name, task_name in TRANSITION_TASKS.items():
        if frappe.db.exists("Workflow Transition Tasks", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Workflow Transition Tasks",
                "name": name,
                "tasks": [{"task": task_name, "enabled": 1, "asynchronous": 0}],
            }
        ).insert(ignore_permissions=True)


def execute() -> None:
    _preflight()
    create_custom_fields(_fields(), update=False, ignore_validate=True)
    _ensure_transition_tasks()
