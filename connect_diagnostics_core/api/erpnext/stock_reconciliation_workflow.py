# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Signed approval and execution guards for native Stock Reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe.approval_controls import (
    authorize_approval_field_write,
    authorize_workflow_field_write,
    consume_approval_field_grant,
    critical_digest,
    require_distinct_actors,
    require_interactive_user,
)
from connect_diagnostics_core.api.frappe.approval_routes import get_route
from connect_diagnostics_core.setup.print_action_fields import PRINT_ACTIONS

ROUTE = get_route("stock_reconciliation")
DIGEST_VERSION = "stock-reconciliation-approval-v2"
APPROVED_STATE = ROUTE.approved_state
SUBMITTED_STATE = ROUTE.submitted_state
CANCELLED_STATE = "Stock Reconciliation Cancelled"
REJECTED_STATE = "Stock Reconciliation Rejected"
CANCEL_ACTION = "Cancel Stock Reconciliation"
_EXECUTION_FLAG = "stock_reconciliation_execution"
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
        "status",
        "__islocal",
        "__unsaved",
    }
)
_PRINT_FIELDS = frozenset(
    field
    for action in PRINT_ACTIONS["Stock Reconciliation"]
    for field in (action.employee_field, action.datetime_field, action.signature_field)
)
_EVIDENCE_FIELDS = (
    "approval_maker_user",
    "approval_reviewer_user",
    "approval_authorized_user",
    "approval_critical_digest",
    "checked_by",
    "checked_at",
    "checked_signature",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
)
_DECISION_FIELDS = tuple(field for field in _EVIDENCE_FIELDS if field != "approval_maker_user")
_PERSISTED_FIELDS = ("owner", "workflow_state", "docstatus", *_EVIDENCE_FIELDS)


def _business_value(value: Any, *, root: bool = False) -> Any:
    if isinstance(value, Document):
        value = value.as_dict()
    if isinstance(value, Mapping):
        return {
            str(key): _business_value(item)
            for key, item in value.items()
            if (key not in _STRUCTURAL_FIELDS or (key == "name" and not root))
            and (not root or key not in _PRINT_FIELDS)
            and (not root or key not in _EVIDENCE_FIELDS)
        }
    if isinstance(value, (list, tuple)):
        return [_business_value(item) for item in value]
    return value


def approval_payload(doc: Document) -> dict[str, Any]:
    """Retain all business inputs and row order, including current counted identities."""
    return cast(dict[str, Any], _business_value(doc.as_dict(), root=True))


def _approval_digest(doc: Document) -> str:
    return DIGEST_VERSION + ":" + critical_digest(approval_payload(doc))


def _persisted_approval(doc: Document) -> dict[str, Any]:
    if doc.doctype != ROUTE.doctype or not doc.name:
        frappe.throw(_("Stock Reconciliation approval requires a saved document."))
    row = frappe.db.get_value(ROUTE.doctype, doc.name, list(_PERSISTED_FIELDS), as_dict=True, for_update=True)
    if not row:
        frappe.throw(_("Stock Reconciliation approval record cannot be found."))
    return dict(cast(dict[str, Any], row))


def _transition(doc: Document, sources: tuple[str, ...], target: str, status: int) -> dict[str, Any]:
    persisted = _persisted_approval(doc)
    if (
        persisted.get("workflow_state") not in sources
        or int(persisted.get("docstatus") or 0) != status
        or doc.get("workflow_state") != target
    ):
        frappe.throw(_("Stock Reconciliation transition has an invalid source or target state."))
    return persisted


def _clear_decision(doc: Document) -> None:
    for field in _DECISION_FIELDS:
        doc.set(field, None)


def capture_maker(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.draft_state, ROUTE.returned_state), ROUTE.pending_review_state, 0)
    action = ROUTE.send_action if persisted["workflow_state"] == ROUTE.draft_state else ROUTE.resubmit_action
    if not persisted.get("owner") or frappe.session.user != persisted["owner"]:
        frappe.throw(_("Only the Stock Reconciliation owner may send it for review."))
    if action == ROUTE.send_action:
        if persisted.get("approval_maker_user"):
            frappe.throw(_("Stock Reconciliation already has maker evidence."))
    elif (
        persisted.get("approval_maker_user") != frappe.session.user
        or doc.get("approval_maker_user") != frappe.session.user
    ):
        frappe.throw(_("Only the original Stock Reconciliation maker may resubmit it."))
    if doc.get("owner") != persisted["owner"]:
        frappe.throw(_("Stock Reconciliation owner cannot change during approval."))
    user = authorize_workflow_field_write(doc, ROUTE.key, action, ROUTE.maker_roles)
    if action == ROUTE.send_action:
        doc.set("approval_maker_user", user)


def capture_review(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.pending_review_state,), ROUTE.reviewed_state, 0)
    maker = str(persisted.get("approval_maker_user") or "")
    if not maker or doc.get("approval_maker_user") != maker:
        frappe.throw(_("Stock Reconciliation maker evidence is required before review."))
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.review_action, ROUTE.reviewer_roles, maker
    )
    doc.set("approval_critical_digest", _approval_digest(doc))
    doc.set("approval_reviewer_user", snapshot.user)
    doc.set("checked_by", snapshot.employee)
    doc.set("checked_at", snapshot.acted_at)
    doc.set("checked_signature", snapshot.signature)


def capture_approval(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.reviewed_state,), APPROVED_STATE, 0)
    if persisted.get("approval_critical_digest") != _approval_digest(doc):
        frappe.throw(_("Stock Reconciliation changed after review and must be reviewed again."))
    maker = str(persisted.get("approval_maker_user") or "")
    reviewer = str(persisted.get("approval_reviewer_user") or "")
    if not maker or not reviewer or not persisted.get("checked_signature"):
        frappe.throw(_("Stock Reconciliation signed review evidence is required before approval."))
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.approve_action, ROUTE.final_approver_roles, maker, (reviewer,)
    )
    doc.set("approval_authorized_user", snapshot.user)
    doc.set("authorized_by", snapshot.employee)
    doc.set("authorized_at", snapshot.acted_at)
    doc.set("authorized_signature", snapshot.signature)


def clear_approval(doc: Document, method: str | None = None) -> None:
    """Clear decisions on Return/Reject while retaining the original maker."""
    del method
    target = str(doc.get("workflow_state") or "")
    if target == ROUTE.returned_state:
        persisted = _transition(
            doc, (ROUTE.pending_review_state, ROUTE.reviewed_state, APPROVED_STATE), ROUTE.returned_state, 0
        )
        roles = (
            ROUTE.reviewer_roles
            if persisted["workflow_state"] == ROUTE.pending_review_state
            else ROUTE.final_approver_roles
        )
        action = ROUTE.return_action
    elif target == REJECTED_STATE:
        persisted = _transition(doc, (ROUTE.reviewed_state,), REJECTED_STATE, 0)
        roles, action = ROUTE.final_approver_roles, ROUTE.reject_action
    else:
        frappe.throw(_("Stock Reconciliation has an invalid Return or Reject target."))
    if doc.get("approval_maker_user") != persisted.get("approval_maker_user"):
        frappe.throw(_("Stock Reconciliation maker evidence cannot change."))
    authorize_workflow_field_write(doc, ROUTE.key, action, roles)
    _clear_decision(doc)


def _validate_approval(doc: Document, persisted: dict[str, Any]) -> None:
    digest = _approval_digest(doc)
    if persisted.get("approval_critical_digest") != digest or doc.get("approval_critical_digest") != digest:
        frappe.throw(_("Stock Reconciliation approval is missing or stale."))
    if any(persisted.get(field) != doc.get(field) for field in _EVIDENCE_FIELDS):
        frappe.throw(_("Stock Reconciliation approval evidence was changed."))
    maker = str(persisted.get("approval_maker_user") or "")
    reviewer = str(persisted.get("approval_reviewer_user") or "")
    approver = str(persisted.get("approval_authorized_user") or "")
    if not all((maker, reviewer, approver)) or not all(
        persisted.get(field)
        for field in (
            "checked_by",
            "checked_at",
            "checked_signature",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        )
    ):
        frappe.throw(_("Current signed Stock Reconciliation approval evidence is required."))
    require_distinct_actors(maker, reviewer, ())
    require_distinct_actors(maker, approver, (reviewer,))


def authorize_submit_execution(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (APPROVED_STATE,), SUBMITTED_STATE, 0)
    _validate_approval(doc, persisted)
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.execute_action, ROUTE.execution_roles, "submit")
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "submit"})


def authorize_cancel_execution(doc: Document, method: str | None = None) -> None:
    del method
    _transition(doc, (SUBMITTED_STATE,), CANCELLED_STATE, 1)
    authorize_workflow_field_write(doc, ROUTE.key, CANCEL_ACTION, ROUTE.execution_roles, "cancel")
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "cancel"})


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    try:
        consume_approval_field_grant(doc, ROUTE.key, ROUTE.execute_action)
        persisted = _transition(doc, (APPROVED_STATE,), SUBMITTED_STATE, 0)
        require_interactive_user(doc, ROUTE.execution_roles, "submit")
        _validate_approval(doc, persisted)
    finally:
        setattr(frappe.flags, _EXECUTION_FLAG, None)


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        consume_approval_field_grant(doc, ROUTE.key, CANCEL_ACTION)
        _transition(doc, (SUBMITTED_STATE,), CANCELLED_STATE, 1)
        require_interactive_user(doc, ROUTE.execution_roles, "cancel")
    finally:
        setattr(frappe.flags, _EXECUTION_FLAG, None)


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    state = str(doc.get("workflow_state") or "")
    if previous is None:
        if state not in {"", ROUTE.draft_state} or any(doc.get(field) for field in _EVIDENCE_FIELDS):
            frappe.throw(_("New Stock Reconciliation must start without approval evidence in Draft."))
        return
    before = str(previous.get("workflow_state") or "")
    if previous.get("owner") != doc.get("owner"):
        frappe.throw(_("Stock Reconciliation owner cannot change during approval."))
    transitions = {
        (ROUTE.draft_state, ROUTE.pending_review_state): ROUTE.send_action,
        (ROUTE.returned_state, ROUTE.pending_review_state): ROUTE.resubmit_action,
        (ROUTE.pending_review_state, ROUTE.reviewed_state): ROUTE.review_action,
        (ROUTE.pending_review_state, ROUTE.returned_state): ROUTE.return_action,
        (ROUTE.reviewed_state, ROUTE.returned_state): ROUTE.return_action,
        (APPROVED_STATE, ROUTE.returned_state): ROUTE.return_action,
        (ROUTE.reviewed_state, REJECTED_STATE): ROUTE.reject_action,
        (ROUTE.reviewed_state, APPROVED_STATE): ROUTE.approve_action,
        (APPROVED_STATE, SUBMITTED_STATE): ROUTE.execute_action,
    }
    action = transitions.get((before, state))
    if before != state and not action:
        frappe.throw(_("Stock Reconciliation Workflow transition is not authorized."))
    if action == ROUTE.execute_action and int(doc.get("docstatus") or 0) != 1:
        frappe.throw(_("Stock Reconciliation Submitted state requires native submission."))
    if action and action != ROUTE.execute_action:
        _transition(doc, (before,), state, 0)
        consume_approval_field_grant(doc, ROUTE.key, action)
    changed = {field for field in _EVIDENCE_FIELDS if previous.get(field) != doc.get(field)}
    allowed = {
        ROUTE.send_action: {"approval_maker_user"},
        ROUTE.resubmit_action: set(),
        ROUTE.review_action: {
            "approval_critical_digest",
            "approval_reviewer_user",
            "checked_by",
            "checked_at",
            "checked_signature",
        },
        ROUTE.approve_action: {
            "approval_authorized_user",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        },
        ROUTE.return_action: set(_DECISION_FIELDS),
        ROUTE.reject_action: set(_DECISION_FIELDS),
    }.get(action or "", set())
    if changed - allowed:
        frappe.throw(_("Stock Reconciliation approval evidence cannot be changed by this transition."))
    if before in {ROUTE.reviewed_state, APPROVED_STATE} or state in {
        ROUTE.reviewed_state,
        APPROVED_STATE,
        SUBMITTED_STATE,
    }:
        if _approval_digest(previous) != _approval_digest(doc):
            frappe.throw(_("Stock Reconciliation counting fields cannot change after review."))
    if state in {ROUTE.reviewed_state, APPROVED_STATE} and doc.get(
        "approval_critical_digest"
    ) != _approval_digest(doc):
        frappe.throw(_("Stock Reconciliation approval is missing or stale."))


def validate_after_submit_update(doc: Document, method: str | None = None) -> None:
    """Submitted state, business data, actor evidence and child identities are immutable."""
    del method
    previous = doc.get_doc_before_save()
    if not previous:
        frappe.throw(_("Submitted Stock Reconciliation history cannot be verified."))
    persisted = _persisted_approval(doc)
    if any(
        state != SUBMITTED_STATE or int(status or 0) != 1
        for state, status in (
            (persisted.get("workflow_state"), persisted.get("docstatus")),
            (previous.get("workflow_state"), previous.get("docstatus")),
            (doc.get("workflow_state"), doc.get("docstatus")),
        )
    ):
        frappe.throw(_("Submitted Stock Reconciliation state cannot change through an update."))
    if previous.get("owner") != doc.get("owner") or any(
        previous.get(field) != doc.get(field) for field in _EVIDENCE_FIELDS
    ):
        frappe.throw(_("Submitted Stock Reconciliation approval evidence cannot change."))
    if _approval_digest(previous) != _approval_digest(doc):
        frappe.throw(_("Submitted Stock Reconciliation counting fields cannot change."))
