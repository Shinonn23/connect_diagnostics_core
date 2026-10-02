# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side guards for the native Payment Entry approval route."""

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

ROUTE = get_route("payment_entry")
DIGEST_VERSION = "payment-entry-approval-v2"
APPROVED_STATE = ROUTE.approved_state
SUBMITTED_STATE = ROUTE.submitted_state
CANCELLED_STATE = "Payment Entry Cancelled"
REJECTED_STATE = "Payment Entry Rejected"
CANCEL_ACTION = "Cancel Payment Entry"
_STRUCTURAL_FIELDS = frozenset(
    {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "status",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "workflow_state",
        "__islocal",
        "__unsaved",
    }
)
_PRINT_FIELDS = frozenset(
    field
    for action in PRINT_ACTIONS["Payment Entry"]
    for field in (action.employee_field, action.datetime_field, action.signature_field)
)
_EVIDENCE_FIELDS = (
    "approval_digest",
    "approval_maker_user",
    "approval_maker_at",
    "approval_checker_user",
    "approval_checker_at",
    "approval_approver_user",
    "approval_approver_at",
    "approval_submit_actor",
    "approval_cancel_actor",
    "checked_by",
    "checked_at",
    "checked_signature",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
)
_DECISION_FIELDS = tuple(
    field for field in _EVIDENCE_FIELDS if field not in {"approval_maker_user", "approval_maker_at"}
)
_PERSISTED_FIELDS = ("owner", "workflow_state", "docstatus", *_EVIDENCE_FIELDS)


def _business_value(value: Any) -> Any:
    if isinstance(value, Document):
        value = value.as_dict()
    if isinstance(value, Mapping):
        return {
            str(key): _business_value(item)
            for key, item in value.items()
            if key not in _STRUCTURAL_FIELDS
            and key not in _PRINT_FIELDS
            and not str(key).startswith("approval_")
        }
    if isinstance(value, (list, tuple)):
        return [_business_value(item) for item in value]
    return value


def approval_payload(doc: Document) -> dict[str, Any]:
    """Retain all business inputs and child order, excluding only evidence and metadata."""
    return cast(dict[str, Any], _business_value(doc.as_dict()))


def get_approval_digest(doc: Document) -> str:
    return DIGEST_VERSION + ":" + critical_digest(approval_payload(doc))


def _reference_identity(doc: Document) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        tuple(
            row.get(field)
            for field in ("name", "doctype", "parent", "parentfield", "parenttype", "docstatus")
        )
        for row in (doc.get("references") or [])
    )


def _persisted(doc: Document) -> dict[str, Any]:
    if doc.doctype != ROUTE.doctype or not doc.name:
        frappe.throw(_("Payment Entry approval requires a saved Payment Entry."))
    row = frappe.db.get_value(ROUTE.doctype, doc.name, list(_PERSISTED_FIELDS), as_dict=True, for_update=True)
    if not row:
        frappe.throw(_("Payment Entry approval record cannot be found."))
    return dict(cast(dict[str, Any], row))


def _transition(doc: Document, sources: tuple[str, ...], target: str, status: int) -> dict[str, Any]:
    persisted = _persisted(doc)
    if (
        persisted.get("workflow_state") not in sources
        or int(persisted.get("docstatus") or 0) != status
        or doc.get("workflow_state") != target
    ):
        frappe.throw(_("Payment Entry transition has an invalid source or target state."))
    return persisted


def _clear_decision(doc: Document) -> None:
    for field in _DECISION_FIELDS:
        doc.set(field, None)


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.draft_state, ROUTE.returned_state), ROUTE.pending_review_state, 0)
    action = ROUTE.send_action if persisted["workflow_state"] == ROUTE.draft_state else ROUTE.resubmit_action
    if not persisted.get("owner") or frappe.session.user != persisted["owner"]:
        frappe.throw(_("Only the Payment Entry owner may send it for review."))
    if action == ROUTE.send_action:
        if persisted.get("approval_maker_user") or persisted.get("approval_maker_at"):
            frappe.throw(_("Payment Entry already has maker evidence."))
    elif (
        persisted.get("approval_maker_user") != frappe.session.user
        or not persisted.get("approval_maker_at")
        or doc.get("approval_maker_user") != frappe.session.user
        or doc.get("approval_maker_at") != persisted.get("approval_maker_at")
    ):
        frappe.throw(_("Only the original Payment Entry maker may resubmit it."))
    if doc.get("owner") != persisted["owner"]:
        frappe.throw(_("Payment Entry owner cannot change during approval."))
    user = authorize_workflow_field_write(doc, ROUTE.key, action, ROUTE.maker_roles)
    if action == ROUTE.send_action:
        doc.set("approval_maker_user", user)
        doc.set("approval_maker_at", frappe.utils.now_datetime())


def capture_checker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.pending_review_state,), ROUTE.reviewed_state, 0)
    maker = str(persisted.get("approval_maker_user") or "")
    if not maker or doc.get("approval_maker_user") != maker:
        frappe.throw(_("Payment Entry maker evidence is required before review."))
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.review_action, ROUTE.reviewer_roles, maker
    )
    doc.set("approval_digest", get_approval_digest(doc))
    doc.set("approval_checker_user", snapshot.user)
    doc.set("approval_checker_at", snapshot.acted_at)
    doc.set("checked_by", snapshot.employee)
    doc.set("checked_at", snapshot.acted_at)
    doc.set("checked_signature", snapshot.signature)


def capture_approver_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (ROUTE.reviewed_state,), ROUTE.approved_state, 0)
    if persisted.get("approval_digest") != get_approval_digest(doc):
        frappe.throw(_("The Payment Entry changed after review and must be reviewed again."))
    maker = str(persisted.get("approval_maker_user") or "")
    checker = str(persisted.get("approval_checker_user") or "")
    if not maker or not checker or not persisted.get("checked_signature"):
        frappe.throw(_("Payment Entry review evidence is required before approval."))
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.approve_action, ROUTE.final_approver_roles, maker, (checker,)
    )
    doc.set("approval_approver_user", snapshot.user)
    doc.set("approval_approver_at", snapshot.acted_at)
    doc.set("authorized_by", snapshot.employee)
    doc.set("authorized_at", snapshot.acted_at)
    doc.set("authorized_signature", snapshot.signature)


def clear_approval_snapshots(doc: Document, method: str | None = None) -> None:
    """Retain the original maker during an exact Return or Reject transition."""
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
        roles = ROUTE.final_approver_roles
        action = ROUTE.reject_action
    else:
        frappe.throw(_("Payment Entry has an invalid Return or Reject target."))
    if doc.get("approval_maker_user") != persisted.get("approval_maker_user") or doc.get(
        "approval_maker_at"
    ) != persisted.get("approval_maker_at"):
        frappe.throw(_("Payment Entry maker evidence cannot change on Return or Reject."))
    authorize_workflow_field_write(doc, ROUTE.key, action, roles)
    _clear_decision(doc)


def _validate_approval(doc: Document, persisted: dict[str, Any]) -> None:
    digest = get_approval_digest(doc)
    if persisted.get("approval_digest") != digest or doc.get("approval_digest") != digest:
        frappe.throw(_("Payment Entry approval is missing or stale."))
    for field in _EVIDENCE_FIELDS:
        if field in {"approval_submit_actor", "approval_cancel_actor"}:
            continue
        if persisted.get(field) != doc.get(field):
            frappe.throw(_("Payment Entry approval evidence was changed."))
    maker = str(persisted.get("approval_maker_user") or "")
    checker = str(persisted.get("approval_checker_user") or "")
    approver = str(persisted.get("approval_approver_user") or "")
    if not all((maker, checker, approver)):
        frappe.throw(_("Current Payment Entry approval evidence is required."))
    if not all(
        persisted.get(field)
        for field in (
            "approval_maker_at",
            "approval_checker_at",
            "checked_by",
            "checked_at",
            "checked_signature",
            "approval_approver_at",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        )
    ):
        frappe.throw(_("Current signed Payment Entry approval evidence is required."))
    if (
        persisted["approval_checker_at"] != persisted["checked_at"]
        or persisted["approval_approver_at"] != persisted["authorized_at"]
    ):
        frappe.throw(_("Payment Entry approval timestamps are inconsistent."))
    require_distinct_actors(maker, checker, ())
    require_distinct_actors(maker, approver, (checker,))


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _transition(doc, (APPROVED_STATE,), SUBMITTED_STATE, 0)
    _validate_approval(doc, persisted)
    user = authorize_workflow_field_write(
        doc, ROUTE.key, ROUTE.execute_action, ROUTE.execution_roles, "submit"
    )
    doc.set("approval_submit_actor", user)


def authorize_cancel_transition(doc: Document, method: str | None = None) -> None:
    del method
    _transition(doc, (SUBMITTED_STATE,), CANCELLED_STATE, 1)
    user = authorize_workflow_field_write(doc, ROUTE.key, CANCEL_ACTION, ROUTE.execution_roles, "cancel")
    doc.set("approval_cancel_actor", user)


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    consume_approval_field_grant(doc, ROUTE.key, ROUTE.execute_action)
    persisted = _transition(doc, (APPROVED_STATE,), SUBMITTED_STATE, 0)
    user = require_interactive_user(doc, ROUTE.execution_roles, "submit")
    if doc.get("approval_submit_actor") != user:
        frappe.throw(_("Payment Entry submit actor does not match the Workflow action."))
    _validate_approval(doc, persisted)


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    consume_approval_field_grant(doc, ROUTE.key, CANCEL_ACTION)
    _transition(doc, (SUBMITTED_STATE,), CANCELLED_STATE, 1)
    user = require_interactive_user(doc, ROUTE.execution_roles, "cancel")
    if doc.get("approval_cancel_actor") != user:
        frappe.throw(_("Payment Entry cancel actor does not match the Workflow action."))


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    state = str(doc.get("workflow_state") or "")
    if previous is None:
        if state not in {"", ROUTE.draft_state} or any(doc.get(field) for field in _EVIDENCE_FIELDS):
            frappe.throw(_("New Payment Entry must start without approval evidence in Draft."))
        return
    before = str(previous.get("workflow_state") or "")
    if previous.get("owner") != doc.get("owner"):
        frappe.throw(_("Payment Entry owner cannot change during approval."))
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
        frappe.throw(_("Payment Entry Workflow state transition is not authorized."))
    if action == ROUTE.execute_action and int(doc.get("docstatus") or 0) != 1:
        frappe.throw(_("Payment Entry Submitted state requires native submission."))
    if action and action != ROUTE.execute_action:
        _transition(doc, (before,), state, 0)
        consume_approval_field_grant(doc, ROUTE.key, action)
    changed = {field for field in _EVIDENCE_FIELDS if previous.get(field) != doc.get(field)}
    allowed = {
        ROUTE.send_action: {"approval_maker_user", "approval_maker_at"},
        ROUTE.resubmit_action: set(),
        ROUTE.review_action: {
            "approval_digest",
            "approval_checker_user",
            "approval_checker_at",
            "checked_by",
            "checked_at",
            "checked_signature",
        },
        ROUTE.approve_action: {
            "approval_approver_user",
            "approval_approver_at",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        },
        ROUTE.return_action: set(_DECISION_FIELDS),
        ROUTE.reject_action: set(_DECISION_FIELDS),
        ROUTE.execute_action: {"approval_submit_actor"},
    }.get(action or "", set())
    if changed - allowed:
        frappe.throw(_("Payment Entry approval evidence cannot be changed by this transition."))
    if before in {ROUTE.reviewed_state, APPROVED_STATE, SUBMITTED_STATE} or state in {
        ROUTE.reviewed_state,
        APPROVED_STATE,
        SUBMITTED_STATE,
    }:
        if get_approval_digest(previous) != get_approval_digest(doc):
            frappe.throw(_("Payment Entry posting fields cannot change after review."))
    if state in {ROUTE.reviewed_state, APPROVED_STATE}:
        if doc.get("approval_digest") != get_approval_digest(doc):
            frappe.throw(_("Payment Entry approval is missing or stale."))


def validate_after_submit_update(doc: Document, method: str | None = None) -> None:
    """Reject changes to submitted business data or immutable approval evidence."""
    del method
    previous = doc.get_doc_before_save()
    if not previous:
        frappe.throw(_("Submitted Payment Entry history cannot be verified."))
    persisted = _persisted(doc)
    if any(
        state != SUBMITTED_STATE or int(status or 0) != 1
        for state, status in (
            (persisted.get("workflow_state"), persisted.get("docstatus")),
            (previous.get("workflow_state"), previous.get("docstatus")),
            (doc.get("workflow_state"), doc.get("docstatus")),
        )
    ):
        frappe.throw(_("Submitted Payment Entry state cannot change through an update."))
    if previous.get("owner") != doc.get("owner"):
        frappe.throw(_("Submitted Payment Entry owner cannot change."))
    if any(previous.get(field) != doc.get(field) for field in _EVIDENCE_FIELDS):
        frappe.throw(_("Submitted Payment Entry approval evidence cannot change."))
    if get_approval_digest(previous) != get_approval_digest(doc) or _reference_identity(
        previous
    ) != _reference_identity(doc):
        from connect_diagnostics_core.api.erpnext.payment_reconciliation import (
            consume_matching_capability,
        )

        consume_matching_capability(doc, previous)
