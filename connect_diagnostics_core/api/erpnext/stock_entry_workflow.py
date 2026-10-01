# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guards for the native Stock Entry Material Transfer workflow."""

from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
)

DIRECT_TRANSFER_PURPOSE = "Material Transfer"
APPROVED_STATES = frozenset(
    {
        "Stock Transfer Submitted",
    }
)
EMERGENCY_STATES = frozenset(
    {
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
        "Emergency Stock Movement Submitted",
        "Emergency Stock Movement Rejected",
        "Emergency Stock Movement Cancelled",
    }
)
EXCEPTION_FLAG = "freeze_exception"
EXCEPTION_REASON = "freeze_exception_reason"
EXCEPTION_SCOPE = "freeze_exception_reconciliation_scope"
_REVIEW_LOCKED_STATES = frozenset(
    {
        "Stock Transfer Pending Review",
        "Stock Transfer Reviewed",
        "Stock Transfer Approved",
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
    }
)
_CRITICAL_FIELDS = (
    "purpose",
    "stock_entry_type",
    "company",
    "posting_date",
    "posting_time",
    "set_posting_time",
    "from_warehouse",
    "to_warehouse",
    "add_to_transit",
    "outgoing_stock_entry",
    "inspection_required",
    "apply_putaway_rule",
    "items",
)
_CRITICAL_ITEM_FIELDS = (
    "item_code",
    "s_warehouse",
    "t_warehouse",
    "qty",
    "transfer_qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "serial_and_batch_bundle",
    "serial_no",
    "batch_no",
    "basic_rate",
    "basic_amount",
    "valuation_rate",
    "allow_zero_valuation_rate",
    "use_serial_batch_fields",
    "expense_account",
    "cost_center",
    "project",
    "material_request",
    "material_request_item",
    "against_stock_entry",
    "putaway_rule",
    "reference_purchase_receipt",
    "job_card_item",
    "bom_no",
    "sample_quantity",
)


def is_direct_transfer(doc: Document) -> bool:
    """Return whether a Stock Entry is a direct Material Transfer."""
    return bool(
        doc.get("purpose") == DIRECT_TRANSFER_PURPOSE
        and not doc.get("add_to_transit")
        and not doc.get("outgoing_stock_entry")
    )


def has_freeze_exception(doc: Document) -> bool:
    """Return whether the document requests the narrowly scoped exception route."""
    return bool(doc.get(EXCEPTION_FLAG))


def _has_native_exception_approval(doc: Document) -> bool:
    """Use a completed native action as supporting approval evidence only.

    A rejected action is also Completed in Frappe, so this predicate is never
    sufficient to authorize posting by itself.  The native Post transition task
    supplies the request-scoped execution provenance checked below.
    """
    return bool(
        frappe.db.exists(
            {
                "doctype": "Workflow Action",
                "reference_doctype": "Stock Entry",
                "reference_name": doc.name,
                "workflow_state": "Emergency Stock Movement Pending Review",
                "status": "Completed",
            }
        )
    )


def _has_native_execution_provenance(doc: Document) -> bool:
    marker = getattr(frappe.flags, "freeze_exception_execution", None)
    return marker == {"doctype": doc.doctype, "name": doc.name}


def clear_freeze_exception_execution() -> None:
    """Clear the one-transition execution marker after validation or failure."""
    frappe.flags.freeze_exception_execution = None


def _has_current_freeze_scope(doc: Document) -> bool:
    try:
        approved_scope = {
            tuple(sorted(entry.items())) for entry in json.loads(doc.get(EXCEPTION_SCOPE) or "[]")
        }
    except (TypeError, ValueError):
        return False

    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import get_active_freeze_scope

    current_scope = {tuple(sorted(entry.items())) for entry in get_active_freeze_scope(doc)}
    return current_scope.issubset(approved_scope)


def is_authorized_freeze_exception(doc: Document) -> bool:
    """Return whether native posting may use the scoped reconciliation exception."""
    return bool(
        is_direct_transfer(doc)
        and has_freeze_exception(doc)
        and doc.get("workflow_state") == "Emergency Stock Movement Submitted"
        and str(doc.get(EXCEPTION_REASON) or "").strip()
        and _has_native_exception_approval(doc)
        and _has_current_freeze_scope(doc)
        and _has_native_execution_provenance(doc)
    )


def authorize_freeze_exception_execution(doc: Document) -> None:
    """Mark a native Post transition as the only execution entry point."""
    if not (
        is_direct_transfer(doc)
        and has_freeze_exception(doc)
        and doc.get("workflow_state") == "Emergency Stock Movement Submitted"
        and str(doc.get(EXCEPTION_REASON) or "").strip()
        and _has_native_exception_approval(doc)
        and _has_current_freeze_scope(doc)
    ):
        frappe.throw(_("Emergency Stock Movement must have a completed native approval before posting."))
    frappe.flags.freeze_exception_execution = {"doctype": doc.doctype, "name": doc.name}


def capture_freeze_exception_approval_scope(doc: Document) -> None:
    """Persist the Freeze scope present when native Emergency approval completes."""
    if not (is_direct_transfer(doc) and has_freeze_exception(doc)):
        frappe.throw(_("Freeze Exception approval requires a direct Material Transfer."))
    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import get_active_freeze_scope

    doc.set(EXCEPTION_SCOPE, json.dumps(get_active_freeze_scope(doc), sort_keys=True))


def _approval_payload(doc: Document) -> dict[str, Any]:
    payload: dict[str, Any] = {
        fieldname: doc.get(fieldname) for fieldname in _CRITICAL_FIELDS if fieldname != "items"
    }
    if not doc.get("set_posting_time"):
        payload["posting_date"] = None
        payload["posting_time"] = None
    payload["items"] = [
        {fieldname: row.get(fieldname) for fieldname in _CRITICAL_ITEM_FIELDS}
        for row in doc.get("items") or []
    ]
    return payload


def get_approval_digest(doc: Document) -> str:
    """Bind approval to the direct transfer values that control native posting."""
    return critical_digest(_approval_payload(doc))


def capture_review_snapshot(doc: Document) -> None:
    """Bind a successful protected Review action to the current transfer payload."""
    if not is_direct_transfer(doc):
        frappe.throw(_("Review is limited to direct Material Transfer stock entries."))
    doc.set("approval_critical_digest", get_approval_digest(doc))
    doc.set("approval_reviewer_user", frappe.session.user)
    doc.set("approval_authorized_user", None)


def capture_authorization_snapshot(doc: Document) -> None:
    """Validate the review binding and record the distinct Final Approver."""
    if not is_direct_transfer(doc):
        frappe.throw(_("Approval is limited to direct Material Transfer stock entries."))
    if str(doc.get("approval_critical_digest") or "") != get_approval_digest(doc):
        frappe.throw(_("The Stock Entry changed after review and must be reviewed again."))
    require_distinct_actors(
        str(doc.get("owner") or ""),
        frappe.session.user,
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    doc.set("approval_authorized_user", frappe.session.user)


def clear_approval_snapshots(doc: Document) -> None:
    """Clear current denormalized approval evidence when a transfer is returned."""
    for fieldname in (
        "approval_critical_digest",
        "approval_reviewer_user",
        "approval_authorized_user",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        doc.set(fieldname, None)


def _reject_critical_changes_after_review(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.get("workflow_state") not in _REVIEW_LOCKED_STATES:
        return
    previous_payload = _approval_payload(previous)
    current_payload = _approval_payload(doc)
    changed = [
        key
        for key in previous_payload
        if critical_digest({key: previous_payload[key]}) != critical_digest({key: current_payload[key]})
    ]
    if changed:
        frappe.throw(
            _(
                "Critical Stock Entry fields cannot change after review. Return it for correction first: {0}."
            ).format(", ".join(changed))
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
    try:
        validate_workflow(doc)
        if is_direct_transfer(doc) and doc.get("workflow_state") not in APPROVED_STATES:
            frappe.throw(_("Direct stock transfers must be approved through the Stock Entry Workflow."))
        if is_direct_transfer(doc) and doc.get("workflow_state") in APPROVED_STATES:
            require_permission(doc, "submit")
            persisted = cast(
                dict[str, Any] | None,
                frappe.db.get_value(
                    "Stock Entry",
                    doc.name,
                    [
                        "workflow_state",
                        "approval_critical_digest",
                        "approval_reviewer_user",
                        "approval_authorized_user",
                        "checked_signature",
                        "authorized_signature",
                    ],
                    as_dict=True,
                    for_update=True,
                ),
            )
            if persisted is None:
                frappe.throw(_("Stock Transfer must be submitted through its approved Workflow action."))
                return
            if persisted.get("workflow_state") != "Stock Transfer Approved":
                frappe.throw(_("Stock Transfer must be submitted through its approved Workflow action."))
            if persisted.get("approval_critical_digest") != get_approval_digest(doc):
                frappe.throw(_("The Stock Entry approval is stale and must be renewed."))
            if not persisted.get("checked_signature") or not persisted.get("authorized_signature"):
                frappe.throw(_("Signed Review and Approval snapshots are required before submission."))
            require_distinct_actors(
                str(doc.get("owner") or ""),
                str(persisted.get("approval_authorized_user") or ""),
                (str(persisted.get("approval_reviewer_user") or ""),),
            )
    except Exception:
        clear_freeze_exception_execution()
        raise


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    """Keep direct transfers on the native Workflow cancel transition."""
    del method
    if not is_direct_transfer(doc):
        return
    persisted_state = frappe.db.get_value(
        "Stock Entry",
        doc.name,
        "workflow_state",
        for_update=True,
    )
    if not (
        persisted_state == "Stock Transfer Submitted"
        and doc.get("workflow_state") == "Stock Transfer Cancelled"
    ):
        frappe.throw(_("Direct stock transfers must be cancelled through their Workflow action."))
