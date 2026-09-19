# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side guards for the shared native Stock Entry Workflow."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

DIRECT_TRANSFER_PURPOSE = "Material Transfer"
APPROVED_STATES = frozenset(
    {
        "Stock Transfer Submitted",
        "Emergency Stock Movement Submitted",
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
EXCEPTION_FLAG = "custom_freeze_exception"
EXCEPTION_REASON = "custom_freeze_exception_reason"
EXCEPTION_SCOPE = "custom_freeze_exception_reconciliation_scope"
_CRITICAL_FIELDS = ("purpose", "add_to_transit", "outgoing_stock_entry", "items")
_CRITICAL_ITEM_FIELDS = (
    "item_code",
    "s_warehouse",
    "t_warehouse",
    "qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "basic_rate",
    "allow_zero_valuation_rate",
)


def is_direct_transfer(doc: Document) -> bool:
    """Return whether a Stock Entry is the direct transfer route, not either transit leg."""
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


def _reject_critical_changes_after_review(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.get("workflow_state") not in {
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
    }:
        return
    for fieldname in _CRITICAL_FIELDS:
        previous_value = previous.get(fieldname)
        current_value = doc.get(fieldname)
        if fieldname == "items":
            previous_value = [
                tuple(row.get(key) for key in _CRITICAL_ITEM_FIELDS) for row in previous_value or []
            ]
            current_value = [
                tuple(row.get(key) for key in _CRITICAL_ITEM_FIELDS) for row in current_value or []
            ]
        if previous_value != current_value:
            frappe.throw(_("Critical Stock Entry fields cannot change after Emergency review starts."))


def validate_workflow(doc: Document, method: str | None = None) -> None:
    """Validate the exception request before native Workflow or posting can proceed."""
    del method
    _reject_critical_changes_after_review(doc)
    state = doc.get("workflow_state")
    requested = has_freeze_exception(doc)
    if not requested:
        if state in EMERGENCY_STATES:
            frappe.throw(_("Emergency Stock Movement requires a Freeze Exception request."))
        return
    if not is_direct_transfer(doc):
        frappe.throw(_("Freeze Exception is limited to direct Material Transfer stock entries."))
    if not str(doc.get(EXCEPTION_REASON) or "").strip():
        frappe.throw(_("Freeze Exception reason is required."))
    if state not in {"Stock Transfer Draft", *EMERGENCY_STATES}:
        frappe.throw(_("Freeze Exception must use the native Emergency Stock Movement Workflow."))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    """Prevent native/API submit from bypassing approval on direct transfers."""
    del method
    try:
        validate_workflow(doc)
        if is_direct_transfer(doc) and doc.get("workflow_state") not in APPROVED_STATES:
            frappe.throw(_("Direct stock transfers must be approved through the Stock Entry Workflow."))
    except Exception:
        clear_freeze_exception_execution()
        raise
