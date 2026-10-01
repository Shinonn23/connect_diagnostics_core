# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guard the PO-only procurement approval migration and preserve legacy history."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _

PURCHASE_ORDER_WORKFLOW = "Connect Purchase Order Blueprint"
MATERIAL_REQUEST_WORKFLOW = "Connect Material Request Blueprint"
BASELINE_PO_FINGERPRINT = "450f4257c28f13db87e52ce118841a9da224087f2430d407e006ec7c83606d9f"
BASELINE_MR_FINGERPRINT = "473dac18ef7fa622942e32f355c3a5040c519ad09f3a49569f06d03ed33ddd82"
TARGET_PO_FINGERPRINT = "55478e4137b7fc0e3fdb550c2a889aaf12a5d6ca6afe333f3b4c2de59fb666db"
INACTIVE_MR_FINGERPRINT = "c2df08978d418bc5de5efb6f904a070c7fdffde4a845919e8ccd5b34bc7910ef"
RECOVERY_FILE_NAME = "connect-purchase-order-approval-recovery.json"
RECOVERY_SCHEMA_VERSION = 1

TASKS = {
    "Connect Purchase Order Review": "Capture Print Action: Checked",
    "Connect Purchase Order Approval": "Capture Print Action: Authorized",
    "Connect Purchase Order Approval Reset": "Clear Purchase Order Approval Snapshots",
    "Connect Purchase Order Submit": "Authorize Purchase Order Submit",
    "Connect Purchase Order Cancel": "Authorize Purchase Order Cancel",
}

EXPECTED_TRANSITION_TASKS = {
    (
        "Purchase Order Draft",
        "Submit Purchase Order for Review",
        "Purchase Order Pending Review",
    ): None,
    (
        "Purchase Order Pending Review",
        "Review Purchase Order",
        "Purchase Order Pending Approval",
    ): "Connect Purchase Order Review",
    (
        "Purchase Order Pending Review",
        "Return Purchase Order",
        "Purchase Order Draft",
    ): "Connect Purchase Order Approval Reset",
    (
        "Purchase Order Pending Approval",
        "Approve Purchase Order",
        "Purchase Order Approved",
    ): "Connect Purchase Order Approval",
    (
        "Purchase Order Pending Approval",
        "Reject Purchase Order",
        "Purchase Order Rejected",
    ): None,
    (
        "Purchase Order Pending Approval",
        "Return Purchase Order",
        "Purchase Order Draft",
    ): "Connect Purchase Order Approval Reset",
    (
        "Purchase Order Rejected",
        "Resubmit Purchase Order",
        "Purchase Order Pending Review",
    ): "Connect Purchase Order Approval Reset",
    (
        "Purchase Order Approved",
        "Post Purchase Order",
        "Purchase Order Submitted",
    ): "Connect Purchase Order Submit",
    (
        "Purchase Order Submitted",
        "Cancel Purchase Order",
        "Purchase Order Cancelled",
    ): "Connect Purchase Order Cancel",
}


def _workflow_fingerprint(workflow: Mapping[str, Any]) -> str:
    states = cast(list[Mapping[str, Any]], workflow.get("states", []))
    transitions = cast(list[Mapping[str, Any]], workflow.get("transitions", []))
    payload = {
        "name": workflow.get("name"),
        "document_type": workflow.get("document_type"),
        "is_active": int(workflow.get("is_active") or 0),
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


def _get_workflow_fingerprint(name: str) -> str:
    workflow = frappe.get_doc("Workflow", name)
    return _workflow_fingerprint(json.loads(frappe.as_json(workflow.as_dict())))


def _workflow_exists(name: str) -> bool:
    return bool(frappe.db.exists("Workflow", name))


def _configuration_dict(doc: Any) -> dict[str, Any]:
    """Capture every persisted configuration field while excluding row identity metadata."""
    excluded = {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parenttype",
        "parentfield",
    }
    result: dict[str, Any] = {}
    for field in doc.meta.fields:
        if field.fieldname in excluded or field.fieldtype in {"Section Break", "Column Break", "Tab Break"}:
            continue
        value = doc.get(field.fieldname)
        if field.fieldtype in {"Table", "Table MultiSelect"}:
            result[field.fieldname] = [_configuration_dict(row) for row in value or []]
        else:
            result[field.fieldname] = value
    return json.loads(frappe.as_json(result))


def _recovery_snapshot() -> dict[str, Any]:
    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "site": frappe.local.site,
        "workflows": {
            name: _configuration_dict(frappe.get_doc("Workflow", name))
            for name in (PURCHASE_ORDER_WORKFLOW, MATERIAL_REQUEST_WORKFLOW)
        },
        "transition_tasks": {
            name: (
                _configuration_dict(frappe.get_doc("Workflow Transition Tasks", name))
                if frappe.db.exists("Workflow Transition Tasks", name)
                else None
            )
            for name in TASKS
        },
    }


def _save_recovery_snapshot() -> None:
    if frappe.db.exists("File", {"file_name": RECOVERY_FILE_NAME}):
        frappe.throw(
            _("Purchase Order approval migration found an existing recovery snapshot requiring owner review.")
        )
    frappe.get_doc(
        {
            "doctype": "File",
            "file_name": RECOVERY_FILE_NAME,
            "is_private": 1,
            "content": json.dumps(_recovery_snapshot(), sort_keys=True, default=str),
        }
    ).insert(ignore_permissions=True)


def _ensure_no_open_procurement_actions() -> None:
    affected = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": ["in", ["Purchase Order", "Material Request"]],
            "status": "Open",
        },
        fields=["name", "reference_doctype", "reference_name"],
        limit=1,
    )
    if affected:
        frappe.throw(
            _(
                "Purchase Order approval migration stopped because an affected open Workflow Action "
                "requires record-level owner disposition."
            )
        )


def _validate_task(name: str, task_name: str) -> bool:
    expected = [(task_name, 1, 0)]
    if frappe.db.exists("Workflow Transition Tasks", name):
        doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != expected:
            frappe.throw(
                _("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(name)
            )
        return True
    return False


def _validate_tasks() -> None:
    for name, task_name in TASKS.items():
        _validate_task(name, task_name)


def _ensure_task(name: str, task_name: str) -> None:
    if _validate_task(name, task_name):
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Transition Tasks",
            "name": name,
            "tasks": [{"task": task_name, "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def execute() -> None:
    """Prepare the approved migration without changing historical actions."""
    _ensure_no_open_procurement_actions()
    if frappe.get_meta("Purchase Order").queue_in_background:
        frappe.throw(_("Purchase Order approval requires synchronous workflow execution."))
    required_roles = {"Purchase User", "Purchase Manager", "C-Level Approver"}
    if not required_roles.issubset(set(frappe.get_all("Role", pluck="name"))):
        frappe.throw(_("Purchase Order approval migration requires the approved procurement roles."))
    _validate_tasks()
    po_exists = _workflow_exists(PURCHASE_ORDER_WORKFLOW)
    mr_exists = _workflow_exists(MATERIAL_REQUEST_WORKFLOW)
    if not po_exists and not mr_exists:
        for name, task_name in TASKS.items():
            _ensure_task(name, task_name)
        return
    po_fingerprint = _get_workflow_fingerprint(PURCHASE_ORDER_WORKFLOW) if po_exists else None
    mr_fingerprint = _get_workflow_fingerprint(MATERIAL_REQUEST_WORKFLOW) if mr_exists else None
    if po_fingerprint == TARGET_PO_FINGERPRINT and mr_fingerprint in {
        None,
        INACTIVE_MR_FINGERPRINT,
    }:
        for name, task_name in TASKS.items():
            _ensure_task(name, task_name)
        return
    if po_exists != mr_exists:
        frappe.throw(_("Procurement Workflow configuration is incomplete and requires owner review."))
    if po_fingerprint != BASELINE_PO_FINGERPRINT:
        frappe.throw(_("Purchase Order Workflow baseline fingerprint does not match the reviewed route."))
    if mr_fingerprint != BASELINE_MR_FINGERPRINT:
        frappe.throw(_("Material Request Workflow baseline fingerprint does not match the reviewed route."))

    _save_recovery_snapshot()

    for name, task_name in TASKS.items():
        _ensure_task(name, task_name)

    material_request_workflow = frappe.get_doc("Workflow", MATERIAL_REQUEST_WORKFLOW)
    material_request_workflow.is_active = 0
    material_request_workflow.save(ignore_permissions=True)


def validate_installed_configuration() -> None:
    """Validate the post-fixture PO-only target and synchronous task wiring."""
    _ensure_no_open_procurement_actions()
    if _get_workflow_fingerprint(PURCHASE_ORDER_WORKFLOW) != TARGET_PO_FINGERPRINT:
        frappe.throw(_("Purchase Order Workflow does not match the reviewed approval route."))
    if _workflow_exists(MATERIAL_REQUEST_WORKFLOW) and (
        _get_workflow_fingerprint(MATERIAL_REQUEST_WORKFLOW) != INACTIVE_MR_FINGERPRINT
    ):
        frappe.throw(_("Material Request Workflow was not preserved as the reviewed inactive route."))

    workflow = frappe.get_doc("Workflow", PURCHASE_ORDER_WORKFLOW)
    actual_transitions = {
        (row.state, row.action, row.next_state): row.transition_tasks or None for row in workflow.transitions
    }
    if actual_transitions != EXPECTED_TRANSITION_TASKS:
        frappe.throw(_("Purchase Order Workflow transitions do not match the reviewed route."))
    for name, task_name in TASKS.items():
        task = frappe.get_doc("Workflow Transition Tasks", name)
        actual_tasks = [(row.task, int(row.enabled), int(row.asynchronous)) for row in task.tasks]
        if actual_tasks != [(task_name, 1, 0)]:
            frappe.throw(
                _("Workflow Transition Tasks {0} is not the reviewed synchronous task.").format(name)
            )
