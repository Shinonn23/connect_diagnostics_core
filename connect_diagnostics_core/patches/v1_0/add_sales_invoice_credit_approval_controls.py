# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Preflight the reviewed Sales Invoice credit-note Workflow before fixture sync."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

WORKFLOW = "Connect Sales Invoice Credit Blueprint"
DOCTYPE = "Sales Invoice"
SNAPSHOT_FILE = "TSK-526 Sales Invoice Credit Workflow Legacy Snapshot"
CREDIT_CONDITION = "doc.is_return and doc.return_against"
ORDINARY_CONDITION = "not doc.is_return"

LEGACY_STATES = (
    ("Sales Invoice Credit Draft", "0", "Sales User"),
    ("Sales Invoice Credit Pending Review", "0", "Sales User"),
    ("Sales Invoice Credit Approved", "0", "Sales Manager"),
    ("Sales Invoice Credit Rejected", "0", "Sales User"),
    ("Sales Invoice Credit Submitted", "1", "Sales Manager"),
    ("Sales Invoice Credit Cancelled", "2", "Sales Manager"),
)
LEGACY_TRANSITIONS = (
    (
        "Sales Invoice Credit Draft",
        "Submit Sales Invoice Credit for Review",
        "Sales Invoice Credit Pending Review",
        "Sales User",
        0,
        "",
        "",
    ),
    (
        "Sales Invoice Credit Pending Review",
        "Approve Sales Invoice Credit",
        "Sales Invoice Credit Approved",
        "Sales Manager",
        0,
        "",
        "",
    ),
    (
        "Sales Invoice Credit Pending Review",
        "Reject Sales Invoice Credit",
        "Sales Invoice Credit Rejected",
        "Sales Manager",
        0,
        "",
        "",
    ),
    (
        "Sales Invoice Credit Approved",
        "Post Sales Invoice Credit",
        "Sales Invoice Credit Submitted",
        "Sales Manager",
        0,
        "",
        "",
    ),
    (
        "Sales Invoice Credit Submitted",
        "Cancel Sales Invoice Credit",
        "Sales Invoice Credit Cancelled",
        "Sales Manager",
        0,
        "",
        "",
    ),
)
DESIRED_STATES = (
    ("Sales Invoice Draft", "0", "All"),
    ("Sales Invoice Credit Pending Review", "0", "All"),
    ("Sales Invoice Credit Reviewed", "0", "Sales Manager"),
    ("Sales Invoice Credit Returned", "0", "All"),
    ("Sales Invoice Credit Approved", "0", "Sales Manager"),
    ("Sales Invoice Submitted", "1", "All"),
    ("Sales Invoice Cancelled", "2", "All"),
)
DESIRED_TRANSITIONS = (
    (
        "Sales Invoice Draft",
        "Submit Sales Invoice",
        "Sales Invoice Submitted",
        "Accounts User",
        1,
        ORDINARY_CONDITION,
        "",
    ),
    (
        "Sales Invoice Draft",
        "Submit Sales Invoice",
        "Sales Invoice Submitted",
        "Accounts Manager",
        1,
        ORDINARY_CONDITION,
        "",
    ),
    (
        "Sales Invoice Submitted",
        "Cancel Sales Invoice",
        "Sales Invoice Cancelled",
        "Accounts Manager",
        1,
        ORDINARY_CONDITION,
        "",
    ),
    (
        "Sales Invoice Draft",
        "Send Sales Invoice Credit for Review",
        "Sales Invoice Credit Pending Review",
        "Sales User",
        1,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Send",
    ),
    (
        "Sales Invoice Credit Returned",
        "Resubmit Sales Invoice Credit for Review",
        "Sales Invoice Credit Pending Review",
        "Sales User",
        1,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Resubmit",
    ),
    (
        "Sales Invoice Credit Pending Review",
        "Review Sales Invoice Credit",
        "Sales Invoice Credit Reviewed",
        "Sales Manager",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Review",
    ),
    (
        "Sales Invoice Credit Pending Review",
        "Return Sales Invoice Credit",
        "Sales Invoice Credit Returned",
        "Sales Manager",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Return",
    ),
    (
        "Sales Invoice Credit Reviewed",
        "Approve Sales Invoice Credit",
        "Sales Invoice Credit Approved",
        "C-Level Approver",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Approve",
    ),
    (
        "Sales Invoice Credit Reviewed",
        "Reject Sales Invoice Credit",
        "Sales Invoice Credit Returned",
        "C-Level Approver",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Reject",
    ),
    (
        "Sales Invoice Credit Approved",
        "Post Sales Invoice Credit",
        "Sales Invoice Submitted",
        "Sales Manager",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Post",
    ),
    (
        "Sales Invoice Submitted",
        "Cancel Sales Invoice Credit",
        "Sales Invoice Cancelled",
        "Sales Manager",
        0,
        CREDIT_CONDITION,
        "Connect Sales Invoice Credit Cancel",
    ),
)
TASKS = {
    "Connect Sales Invoice Credit Send": "Capture Sales Invoice Credit Maker",
    "Connect Sales Invoice Credit Resubmit": "Capture Sales Invoice Credit Maker",
    "Connect Sales Invoice Credit Review": "Capture Sales Invoice Credit Review",
    "Connect Sales Invoice Credit Return": "Clear Sales Invoice Credit Return",
    "Connect Sales Invoice Credit Approve": "Capture Sales Invoice Credit Approval",
    "Connect Sales Invoice Credit Reject": "Clear Sales Invoice Credit Reject",
    "Connect Sales Invoice Credit Post": "Authorize Sales Invoice Credit Post",
    "Connect Sales Invoice Credit Cancel": "Authorize Sales Invoice Credit Cancel",
}


def execute() -> None:
    active = frappe.get_all("Workflow", filters={"document_type": DOCTYPE, "is_active": 1}, pluck="name")
    foreign = [name for name in active if name != WORKFLOW]
    if foreign:
        frappe.throw(_("Sales Invoice has another active Workflow; migration stopped for owner review."))

    if frappe.get_meta(DOCTYPE).queue_in_background:
        frappe.throw(_("Sales Invoice credit approval requires synchronous Workflow submission."))
    required_roles = {
        "Sales User",
        "Sales Manager",
        "C-Level Approver",
        "Accounts User",
        "Accounts Manager",
    }
    if not required_roles.issubset(set(frappe.get_all("Role", pluck="name"))):
        frappe.throw(_("Sales Invoice credit approval requires the reviewed business roles."))
    _validate_tasks()

    existing = frappe.db.exists("Workflow", WORKFLOW)
    if existing:
        workflow = frappe.get_doc("Workflow", WORKFLOW)
        fingerprint = _fingerprint(workflow)
        if fingerprint not in {
            (LEGACY_STATES, LEGACY_TRANSITIONS),
            (DESIRED_STATES, DESIRED_TRANSITIONS),
        }:
            frappe.throw(
                _("Sales Invoice credit Workflow differs from the reviewed route; migration stopped.")
            )
        if fingerprint == (DESIRED_STATES, DESIRED_TRANSITIONS):
            _ensure_tasks()
            return
        if fingerprint == (LEGACY_STATES, LEGACY_TRANSITIONS):
            _ensure_no_live_route_usage()
            _save_snapshot(workflow)
    else:
        _ensure_no_live_route_usage()

    _ensure_tasks()


def _ensure_no_live_route_usage() -> None:
    if frappe.db.exists("Workflow Action", {"reference_doctype": DOCTYPE, "status": "Open"}):
        frappe.throw(_("Sales Invoice has open Workflow Actions; migration stopped for owner review."))
    if frappe.db.exists(
        "Sales Invoice",
        {"docstatus": 0, "is_return": 1, "return_against": ["is", "set"]},
    ):
        frappe.throw(_("Pending Sales Invoice credit notes require owner disposition before migration."))


def _save_snapshot(workflow: Any) -> None:
    snapshot = _load_snapshot()
    if snapshot:
        prior = snapshot.get("workflow") if isinstance(snapshot, dict) else None
        if (
            isinstance(snapshot, dict)
            and snapshot.get("schema") == 1
            and snapshot.get("site") == frappe.local.site
            and isinstance(prior, dict)
            and prior.get("doctype") == "Workflow"
            and prior.get("name") == WORKFLOW
        ):
            prior_workflow = frappe.get_doc(prior)
            if _fingerprint(prior_workflow) == (LEGACY_STATES, LEGACY_TRANSITIONS):
                return
        frappe.throw(
            _(
                "Sales Invoice credit Workflow recovery snapshot already exists but is not the reviewed legacy route."
            )
        )
    frappe.get_doc(
        {
            "doctype": "File",
            "file_name": SNAPSHOT_FILE,
            "is_private": 1,
            "content": frappe.as_json(
                {"schema": 1, "site": frappe.local.site, "workflow": workflow.as_dict()}
            ),
        }
    ).insert(ignore_permissions=True)


def _load_snapshot() -> dict[str, Any] | None:
    files = frappe.get_all(
        "File",
        filters={"file_name": SNAPSHOT_FILE},
        pluck="name",
        limit=2,
    )
    if not files:
        return None
    if len(files) != 1:
        frappe.throw(_("Sales Invoice credit Workflow recovery snapshot is ambiguous."))
    content = frappe.get_doc("File", files[0]).get_content()
    if isinstance(content, bytes):
        content = content.decode()
    parsed = frappe.parse_json(content)
    return parsed if isinstance(parsed, dict) else None


def _ensure_task(name: str, task: str) -> None:
    expected = [(task, 1, 0)]
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
            "tasks": [{"task": task, "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def _validate_tasks() -> None:
    for name, task in TASKS.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            continue
        doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != [(task, 1, 0)]:
            frappe.throw(
                _("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(name)
            )


def _ensure_tasks() -> None:
    for name, task in TASKS.items():
        _ensure_task(name, task)


def _fingerprint(workflow: Any) -> tuple[tuple[tuple[str, str, str], ...], tuple[tuple[Any, ...], ...]]:
    states = tuple(
        (str(row.state), str(row.doc_status), str(row.allow_edit or "")) for row in workflow.states
    )
    transitions = tuple(
        (
            str(row.state),
            str(row.action),
            str(row.next_state),
            str(row.allowed),
            int(row.allow_self_approval or 0),
            str(row.condition or ""),
            str(row.transition_tasks or ""),
        )
        for row in workflow.transitions
    )
    return states, transitions
