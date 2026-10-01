# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guards for the native Stock Entry Material Transfer workflow."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe import approval_controls

DIRECT_TRANSFER_PURPOSE = "Material Transfer"
APPROVED_STATE = "Stock Transfer Submitted"
_EXECUTION_FLAG = "stock_transfer_execution"


def _digest(doc: Document) -> str:
    return approval_controls.critical_digest(
        {"purpose": doc.get("purpose"), "items": [dict(row) for row in doc.get("items", [])]}
    )


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    doc.set("approval_maker_user", approval_controls.resolve_user(frappe.session.user))


def capture_review_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    maker = str(doc.get("approval_maker_user") or "")
    reviewer = approval_controls.resolve_user(frappe.session.user)
    approval_controls.require_distinct_actors(maker, reviewer, ())
    doc.set("approval_critical_digest", _digest(doc))
    doc.set("approval_reviewer_user", reviewer)


def capture_approval_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("approval_critical_digest") != _digest(doc):
        frappe.throw(_("Stock Transfer review is stale; return it for review again."))
    approver = approval_controls.resolve_user(frappe.session.user)
    approval_controls.require_distinct_actors(
        str(doc.get("approval_maker_user") or ""),
        approver,
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    doc.set("approval_authorized_user", approver)


def reset_approval(doc: Document, method: str | None = None) -> None:
    del method
    for fieldname in (
        "approval_maker_user",
        "approval_critical_digest",
        "approval_reviewer_user",
        "approval_authorized_user",
    ):
        doc.set(fieldname, None)


def authorize_submit_execution(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") != APPROVED_STATE:
        frappe.throw(_("Stock Transfer must be approved before submission."))
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "submit"})


def authorize_cancel_execution(doc: Document, method: str | None = None) -> None:
    del method
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "cancel"})


def is_direct_transfer(doc: Document) -> bool:
    """Return whether a Stock Entry is a direct Material Transfer."""
    return bool(
        doc.get("purpose") == DIRECT_TRANSFER_PURPOSE
        and not doc.get("add_to_transit")
        and not doc.get("outgoing_stock_entry")
    )


def validate_workflow(doc: Document, method: str | None = None) -> None:
    """Reject non-transfer entries from the Material Transfer route."""
    del method
    if (
        doc.get("workflow_state")
        and not is_direct_transfer(doc)
        and str(doc.get("workflow_state")).startswith("Stock Transfer")
    ):
        frappe.throw(_("Stock Transfer workflow is limited to direct Material Transfer entries."))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    """Prevent direct Material Transfer submission without native approval."""
    del method
    marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
    if is_direct_transfer(doc) and (
        marker != {"doctype": doc.doctype, "name": doc.name, "action": "submit"}
        or doc.get("workflow_state") != "Stock Transfer Submitted"
    ):
        frappe.throw(_("Direct stock transfers must be approved through the Stock Entry Workflow."))
    setattr(frappe.flags, _EXECUTION_FLAG, None)


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
    if marker != {"doctype": doc.doctype, "name": doc.name, "action": "cancel"}:
        frappe.throw(_("Stock Entry must be cancelled through its Workflow action."))
    setattr(frappe.flags, _EXECUTION_FLAG, None)
