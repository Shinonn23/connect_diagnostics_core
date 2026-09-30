# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guarded local.test installation of the temporary Purchase Invoice route."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _

EXPECTED_FINGERPRINT = "f1ff2f961f021ba1cc7a3d042c38a21ff28c4760c4c6e0dafd93d3d95207f031"
TRIAL_FINGERPRINT = "3ea81f3361ed26a1cff28b4a3c4d759e44e142b8c6bf72a7bc26e14c3eb75956"
TASKS = {
    "Connect Purchase Invoice Source Verification": "Capture Purchase Invoice Source Verification",
    "Connect Purchase Invoice Accounting Approval": "Capture Purchase Invoice Accounting Approval",
    "Connect Purchase Invoice Approval Reset": "Clear Purchase Invoice Approval Snapshots",
    "Connect Purchase Invoice Submit": "Authorize Purchase Invoice Submit",
    "Connect Purchase Invoice Cancel": "Authorize Purchase Invoice Cancel",
}
EXPECTED_TRANSITION_TASKS = {
    (
        "Purchase Invoice Draft",
        "Submit Purchase Invoice for Review",
        "Purchase Invoice Pending Source Verification",
    ): None,
    (
        "Purchase Invoice Pending Source Verification",
        "Verify Purchase Invoice Source",
        "Purchase Invoice Pending Accounting Approval",
    ): "Connect Purchase Invoice Source Verification",
    (
        "Purchase Invoice Pending Source Verification",
        "Return Purchase Invoice",
        "Purchase Invoice Returned",
    ): "Connect Purchase Invoice Approval Reset",
    (
        "Purchase Invoice Pending Source Verification",
        "Reject Purchase Invoice",
        "Purchase Invoice Rejected",
    ): None,
    (
        "Purchase Invoice Pending Accounting Approval",
        "Approve Purchase Invoice",
        "Purchase Invoice Approved",
    ): "Connect Purchase Invoice Accounting Approval",
    (
        "Purchase Invoice Pending Accounting Approval",
        "Return Purchase Invoice",
        "Purchase Invoice Returned",
    ): "Connect Purchase Invoice Approval Reset",
    (
        "Purchase Invoice Pending Accounting Approval",
        "Reject Purchase Invoice",
        "Purchase Invoice Rejected",
    ): None,
    (
        "Purchase Invoice Approved",
        "Post Purchase Invoice",
        "Purchase Invoice Submitted",
    ): "Connect Purchase Invoice Submit",
    (
        "Purchase Invoice Approved",
        "Return Purchase Invoice",
        "Purchase Invoice Returned",
    ): "Connect Purchase Invoice Approval Reset",
    (
        "Purchase Invoice Returned",
        "Resubmit Purchase Invoice",
        "Purchase Invoice Pending Source Verification",
    ): None,
    (
        "Purchase Invoice Submitted",
        "Cancel Purchase Invoice",
        "Purchase Invoice Cancelled",
    ): "Connect Purchase Invoice Cancel",
}


def _ensure_task(name: str, task_name: str) -> None:
    expected = [(task_name, 1, 0)]
    if frappe.db.exists("Workflow Transition Tasks", name):
        doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != expected:
            frappe.throw(_("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(name))
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Transition Tasks",
            "name": name,
            "tasks": [{"task": task_name, "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def _workflow_fingerprint(workflow: Mapping[str, Any]) -> str:
    states = cast(list[Mapping[str, Any]], workflow.get("states", []))
    transitions = cast(list[Mapping[str, Any]], workflow.get("transitions", []))
    payload = {
        "name": workflow.get("name"),
        "document_type": workflow.get("document_type"),
        "is_active": workflow.get("is_active"),
        "workflow_state_field": workflow.get("workflow_state_field"),
        "states": [
            {
                "state": state.get("state"),
                "doc_status": str(state.get("doc_status") or 0),
                "allow_edit": state.get("allow_edit"),
            }
            for state in states
        ],
        "transitions": [
            {
                "state": transition.get("state"),
                "action": transition.get("action"),
                "next_state": transition.get("next_state"),
                "allowed": transition.get("allowed"),
                "allow_self_approval": int(transition.get("allow_self_approval") or 0),
                "condition": transition.get("condition") or None,
                "transition_tasks": transition.get("transition_tasks") or None,
            }
            for transition in transitions
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def execute() -> None:
    """Fail closed unless the inventoried empty local.test baseline is present."""
    if frappe.local.site != "local.test":
        frappe.throw(_("Purchase Invoice trial migration is authorized only on local.test."))
    if frappe.db.count("Purchase Invoice"):
        frappe.throw(_("Purchase Invoice trial migration requires an empty Purchase Invoice table."))
    if frappe.db.count("Workflow Action", {"reference_doctype": "Purchase Invoice"}):
        frappe.throw(_("Purchase Invoice trial migration requires no open workflow actions."))
    if frappe.get_meta("Purchase Invoice").queue_in_background:
        frappe.throw(_("Purchase Invoice trial migration requires synchronous workflow execution."))
    required_roles = {"Accounts User", "Purchase Manager", "Accounts Manager"}
    existing_roles = set(frappe.get_all("Role", pluck="name"))
    if not required_roles.issubset(existing_roles):
        frappe.throw(_("Purchase Invoice trial migration requires the approved accounting roles."))
    workflow = frappe.get_doc("Workflow", "Connect Purchase Invoice Blueprint")
    if not workflow:
        frappe.throw(_("Purchase Invoice trial migration requires the inventoried Purchase Invoice workflow."))
    fingerprint = _workflow_fingerprint(json.loads(frappe.as_json(workflow.as_dict())))
    if fingerprint != EXPECTED_FINGERPRINT:
        frappe.throw(_("Purchase Invoice trial migration fingerprint contract is invalid."))
    for name, task_name in TASKS.items():
        _ensure_task(name, task_name)


def validate_installed_configuration() -> None:
    """Fail closed after fixture sync unless every guarded transition is wired synchronously."""
    if frappe.local.site != "local.test":
        frappe.throw(_("Purchase Invoice trial configuration is authorized only on local.test."))
    workflow = frappe.get_doc("Workflow", "Connect Purchase Invoice Blueprint")
    fingerprint = _workflow_fingerprint(json.loads(frappe.as_json(workflow.as_dict())))
    if fingerprint != TRIAL_FINGERPRINT:
        frappe.throw(
            _(
                "Purchase Invoice trial Workflow does not match the reviewed configuration; "
                "restore only through the fingerprint-guarded recovery procedure."
            )
        )
    actual_transitions = {
        (row.state, row.action, row.next_state): row.transition_tasks or None for row in workflow.transitions
    }
    if actual_transitions != EXPECTED_TRANSITION_TASKS:
        frappe.throw(_("Purchase Invoice trial Workflow transitions do not match the reviewed route."))
    for name, task_name in TASKS.items():
        task = frappe.get_doc("Workflow Transition Tasks", name)
        actual_tasks = [(row.task, int(row.enabled), int(row.asynchronous)) for row in task.tasks]
        if actual_tasks != [(task_name, 1, 0)]:
            frappe.throw(_("Workflow Transition Tasks {0} is not the reviewed synchronous task.").format(name))
