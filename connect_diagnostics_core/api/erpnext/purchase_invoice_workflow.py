# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fail-closed approval controls for the native Purchase Invoice route."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe import approval_controls
from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
)

APPROVED_STATE = "Purchase Invoice Approved"
SUBMITTED_STATE = "Purchase Invoice Submitted"
_LOCKED_STATES = frozenset({"Purchase Invoice Pending Accounting Approval", APPROVED_STATE, SUBMITTED_STATE})
_DIGEST_EXCLUDED = {
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
    "workflow_state",
    "approval_critical_digest",
    "approval_reviewer_user",
    "approval_authorized_user",
    "checked_by",
    "checked_at",
    "checked_signature",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
    "status",
    "outstanding",
    "outstanding_amount",
    "in_words",
    "base_in_words",
    "other_charges_calculation",
    "address_display",
    "shipping_address_display",
    "billing_address_display",
    "contact_display",
    "remarks",
    "terms",
    "letter_head",
}


def _payload(doc: Document) -> dict[str, Any]:
    def normalize(value: Any, key: str | None = None) -> Any:
        if key and (key in _DIGEST_EXCLUDED or key.startswith("_")):
            return None
        if isinstance(value, Mapping):
            return {
                child_key: normalized
                for child_key, child_value in value.items()
                if (normalized := normalize(child_value, str(child_key))) is not None
            }
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, (date, datetime, time)):
            return value.isoformat()
        return value

    payload = cast(dict[str, Any], normalize(doc.as_dict()))
    if not doc.get("set_posting_time"):
        payload.pop("posting_time", None)
    return payload


def get_approval_digest(doc: Document) -> str:
    return critical_digest(_payload(doc))


def _require_sources(doc: Document) -> None:
    if doc.get("is_paid"):
        frappe.throw(_("Purchase Invoice approval does not permit paid invoices. Use Payment Entry."))
    for row in doc.get("items") or []:
        if not row.get("purchase_order") or not row.get("purchase_receipt"):
            frappe.throw(
                _(
                    "Every Purchase Invoice item must reference a submitted Purchase Order and Purchase Receipt."
                )
            )
        if not frappe.db.exists("Purchase Order", {"name": row.purchase_order, "docstatus": 1}):
            frappe.throw(_("Purchase Order references must be submitted."))
        if not frappe.db.exists("Purchase Receipt", {"name": row.purchase_receipt, "docstatus": 1}):
            frappe.throw(_("Purchase Receipt references must be submitted."))


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    if str(doc.get("owner") or "") != frappe.session.user:
        frappe.throw(_("Only the Purchase Invoice owner can send it for review."))
    doc.set("approval_maker_user", frappe.session.user)


def capture_source_verification_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    _require_sources(doc)
    snapshot = approval_controls.capture_signed_approval_actor(doc, str(doc.get("approval_maker_user") or ""))
    doc.set("approval_critical_digest", get_approval_digest(doc))
    doc.set("approval_reviewer_user", snapshot.user)
    doc.set("checked_by", snapshot.employee)
    doc.set("checked_at", snapshot.acted_at)
    doc.set("checked_signature", snapshot.signature)


def capture_accounting_approval_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    _require_sources(doc)
    if doc.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("The Purchase Invoice changed after source verification and must be reviewed again."))
    snapshot = approval_controls.capture_signed_approval_actor(
        doc,
        str(doc.get("owner") or ""),
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    doc.set("approval_authorized_user", snapshot.user)
    doc.set("authorized_by", snapshot.employee)
    doc.set("authorized_at", snapshot.acted_at)
    doc.set("authorized_signature", snapshot.signature)


def clear_approval_snapshots(doc: Document, method: str | None = None) -> None:
    del method
    for field in (
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
        doc.set(field, None)


def _marker(doc: Document) -> bool:
    return getattr(frappe.flags, "purchase_invoice_execution", None) == {
        "doctype": doc.doctype,
        "name": doc.name,
    }


def authorize_submit_execution(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") != SUBMITTED_STATE or doc.get("is_paid"):
        frappe.throw(_("Purchase Invoice must be approved through its native Workflow action."))
    if doc.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("The Purchase Invoice approval is stale and must be renewed."))
    frappe.flags.purchase_invoice_execution = {"doctype": doc.doctype, "name": doc.name}


def authorize_cancel_execution(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") != "Purchase Invoice Cancelled":
        frappe.throw(_("Purchase Invoice cancellation must use its native Workflow action."))
    frappe.flags.purchase_invoice_cancel_execution = {"doctype": doc.doctype, "name": doc.name}


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") in _LOCKED_STATES and doc.get("approval_critical_digest"):
        previous = doc.get_doc_before_save()
        if (
            previous
            and previous.get("workflow_state") in _LOCKED_STATES
            and get_approval_digest(previous) != get_approval_digest(doc)
        ):
            previous_payload = _payload(previous)
            current_payload = _payload(doc)
            changed_fields = sorted(
                key
                for key in previous_payload.keys() | current_payload.keys()
                if previous_payload.get(key) != current_payload.get(key)
            )
            frappe.throw(
                _(
                    "Critical Purchase Invoice fields cannot change after review. "
                    "Return it for correction first. Changed fields: {0}."
                ).format(", ".join(changed_fields))
            )
    state = doc.get("workflow_state")
    if not state and doc.is_new():
        return
    if state not in {
        "Purchase Invoice Draft",
        "Purchase Invoice Returned",
        "Purchase Invoice Pending Source Verification",
        "Purchase Invoice Pending Accounting Approval",
        APPROVED_STATE,
        SUBMITTED_STATE,
        "Purchase Invoice Rejected",
        "Purchase Invoice Cancelled",
    }:
        frappe.throw(_("Purchase Invoice has an invalid approval state."))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    try:
        validate_workflow(doc)
        _require_sources(doc)
        if not _marker(doc):
            frappe.throw(_("Purchase Invoice submission must use the approved Workflow action."))
        require_permission(doc, "submit")
        persisted = cast(
            dict[str, Any] | None,
            frappe.db.get_value(
                "Purchase Invoice",
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
            frappe.throw(_("Purchase Invoice approval is missing or stale."))
            return
        if persisted.get("workflow_state") != APPROVED_STATE or persisted.get(
            "approval_critical_digest"
        ) != get_approval_digest(doc):
            frappe.throw(_("Purchase Invoice approval is missing or stale."))
        if not persisted.get("checked_signature") or not persisted.get("authorized_signature"):
            frappe.throw(_("Signed source verification and accounting approval are required."))
        require_distinct_actors(
            str(doc.get("owner") or ""),
            str(persisted.get("approval_authorized_user") or ""),
            (str(persisted.get("approval_reviewer_user") or ""),),
        )
    finally:
        frappe.flags.purchase_invoice_execution = None


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        marker = getattr(frappe.flags, "purchase_invoice_cancel_execution", None)
        if marker != {"doctype": doc.doctype, "name": doc.name}:
            frappe.throw(_("Purchase Invoice cancellation must use its native Workflow action."))
        require_permission(doc, "cancel")
        persisted = frappe.db.get_value("Purchase Invoice", doc.name, "workflow_state", for_update=True)
        if persisted != SUBMITTED_STATE or doc.get("workflow_state") != "Purchase Invoice Cancelled":
            frappe.throw(_("Purchase Invoice cancellation must use its native Workflow action."))
    finally:
        frappe.flags.purchase_invoice_cancel_execution = None
