# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side guards for the native Payment Entry approval route."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
)

APPROVED_STATE = "Payment Entry Approved"
SUBMITTED_STATE = "Payment Entry Submitted"
CANCELLED_STATE = "Payment Entry Cancelled"
_EXECUTION_FLAG = "connect_payment_entry_execution"
_STRUCTURAL_FIELDS = frozenset(
    {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "workflow_state",
    }
)


def approval_payload(doc: Document) -> dict[str, Any]:
    """Build deterministic evidence from business fields, excluding mutable approval metadata."""
    return {
        str(key): value
        for key, value in doc.as_dict().items()
        if key not in _STRUCTURAL_FIELDS and not str(key).startswith("approval_")
    }


def get_approval_digest(doc: Document) -> str:
    return "payment-entry-approval-v1:" + critical_digest(approval_payload(doc))


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    clear_approval_snapshots(doc)
    doc.set("approval_maker_user", frappe.session.user)
    doc.set("approval_maker_at", frappe.utils.now_datetime())


def capture_checker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    maker = str(doc.get("approval_maker_user") or "")
    if not maker:
        frappe.throw(_("Payment Entry maker evidence is required before review."))
    require_distinct_actors(maker, frappe.session.user, ())
    doc.set("approval_digest", get_approval_digest(doc))
    doc.set("approval_checker_user", frappe.session.user)
    doc.set("approval_checker_at", frappe.utils.now_datetime())


def capture_approver_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("approval_digest") != get_approval_digest(doc):
        frappe.throw(_("The Payment Entry changed after review and must be reviewed again."))
    maker = str(doc.get("approval_maker_user") or "")
    checker = str(doc.get("approval_checker_user") or "")
    if not maker or not checker:
        frappe.throw(_("Payment Entry review evidence is required before approval."))
    require_distinct_actors(maker, frappe.session.user, (checker,))
    doc.set("approval_approver_user", frappe.session.user)
    doc.set("approval_approver_at", frappe.utils.now_datetime())


def clear_approval_snapshots(doc: Document, method: str | None = None) -> None:
    del method
    for field in (
        "approval_digest",
        "approval_maker_user",
        "approval_maker_at",
        "approval_checker_user",
        "approval_checker_at",
        "approval_approver_user",
        "approval_approver_at",
        "approval_submit_actor",
        "approval_cancel_actor",
    ):
        doc.set(field, None)


def _persisted(doc: Document) -> dict[str, Any]:
    row = frappe.db.get_value(
        "Payment Entry",
        doc.name,
        [
            "workflow_state",
            "docstatus",
            "approval_digest",
            "approval_maker_user",
            "approval_checker_user",
            "approval_approver_user",
        ],
        as_dict=True,
        for_update=True,
    )
    if not row:
        frappe.throw(_("Payment Entry approval record cannot be found."))
    return dict(cast(dict[str, Any], row))


def _execution_marker(doc: Document, action: str) -> dict[str, str]:
    return {
        "doctype": doc.doctype,
        "name": str(doc.name or ""),
        "action": action,
        "user": str(frappe.session.user or ""),
    }


def _clear_execution_marker() -> None:
    setattr(frappe.flags, _EXECUTION_FLAG, None)


def _validate_approval(doc: Document, persisted: dict[str, Any]) -> None:
    digest = get_approval_digest(doc)
    if persisted.get("approval_digest") != digest or doc.get("approval_digest") != digest:
        frappe.throw(_("Payment Entry approval is missing or stale."))
    maker = str(persisted.get("approval_maker_user") or "")
    checker = str(persisted.get("approval_checker_user") or "")
    approver = str(persisted.get("approval_approver_user") or "")
    if not maker or not checker or not approver:
        frappe.throw(_("Current Payment Entry approval evidence is required."))
    require_distinct_actors(maker, checker, ())
    require_distinct_actors(maker, approver, (checker,))


def _authorize_execution(doc: Document, action: str) -> None:
    if doc.doctype != "Payment Entry" or not doc.name:
        frappe.throw(_("Payment Entry execution authorization requires a saved Payment Entry."))
    persisted = _persisted(doc)
    expected_source = APPROVED_STATE if action == "submit" else SUBMITTED_STATE
    expected_target = SUBMITTED_STATE if action == "submit" else CANCELLED_STATE
    expected_docstatus = 0 if action == "submit" else 1
    if (
        persisted.get("workflow_state") != expected_source
        or persisted.get("docstatus") != expected_docstatus
        or doc.get("workflow_state") != expected_target
    ):
        frappe.throw(_("Payment Entry transition has an invalid source or target state."))
    if action == "submit":
        _validate_approval(doc, persisted)
    require_permission(doc, action)
    actor_field = "approval_submit_actor" if action == "submit" else "approval_cancel_actor"
    doc.set(actor_field, frappe.session.user)
    setattr(frappe.flags, _EXECUTION_FLAG, _execution_marker(doc, action))


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    _authorize_execution(doc, "submit")


def authorize_cancel_transition(doc: Document, method: str | None = None) -> None:
    del method
    _authorize_execution(doc, "cancel")


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    try:
        if getattr(frappe.flags, _EXECUTION_FLAG, None) != _execution_marker(doc, "submit"):
            frappe.throw(_("Payment Entry must be submitted through its approved Workflow action."))
        persisted = _persisted(doc)
        if persisted.get("workflow_state") != APPROVED_STATE or doc.get("workflow_state") != SUBMITTED_STATE:
            frappe.throw(_("Payment Entry must have current approval before submission."))
        require_permission(doc, "submit")
        _validate_approval(doc, persisted)
    finally:
        _clear_execution_marker()


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        if getattr(frappe.flags, _EXECUTION_FLAG, None) != _execution_marker(doc, "cancel"):
            frappe.throw(_("Payment Entry must be cancelled through its Workflow action."))
        persisted = _persisted(doc)
        if persisted.get("workflow_state") != SUBMITTED_STATE or doc.get("workflow_state") != CANCELLED_STATE:
            frappe.throw(_("Submitted Payment Entries must be cancelled through the native Workflow."))
        require_permission(doc, "cancel")
    finally:
        _clear_execution_marker()


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") in {APPROVED_STATE, SUBMITTED_STATE}:
        digest = get_approval_digest(doc)
        if doc.get("approval_digest") != digest:
            frappe.throw(_("Payment Entry approval is missing or stale."))
