# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fail-closed approval controls for the temporary local.test PI route."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
    resolve_user,
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
    "trial_policy_warning",
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
    rows = doc.get("items") or []
    item_codes = sorted({str(row.get("item_code")) for row in rows if row.get("item_code")})
    if len(item_codes) != len({str(row.get("item_code") or "") for row in rows}):
        frappe.throw(_("Every Purchase Invoice row requires an Item."))
    try:
        items = (
            frappe.db.get_values(
                "Item",
                filters={"name": ("in", item_codes)},
                fieldname=["name", "is_stock_item", "is_fixed_asset"],
                as_dict=True,
                for_update=True,
                wait=False,
                order_by="name",
            )
            if item_codes
            else []
        )
        classified = {str(item.name): bool(item.is_stock_item or item.is_fixed_asset) for item in items}
        if len(classified) != len(item_codes):
            frappe.throw(_("Purchase Invoice references an Item that no longer exists."))

        sources: set[tuple[str, str]] = set()
        for row in rows:
            po = str(row.get("purchase_order") or "")
            po_detail = str(row.get("po_detail") or "")
            pr = str(row.get("purchase_receipt") or "")
            pr_detail = str(row.get("pr_detail") or "")
            if not po or not po_detail:
                frappe.throw(_("Every Purchase Invoice row requires a Purchase Order and its exact item."))
            if classified[str(row.get("item_code"))] and (not pr or not pr_detail):
                frappe.throw(
                    _("Stock and fixed-asset Purchase Invoice rows require a Purchase Receipt item.")
                )
            if bool(pr) != bool(pr_detail):
                frappe.throw(_("Purchase Receipt references must include both header and item."))
            sources.add(("Purchase Order", po))
            if pr:
                sources.add(("Purchase Receipt", pr))

        children: dict[tuple[str, str], dict[str, Any]] = {}
        for doctype, name in sorted(sources):
            header = frappe.db.get_value(
                doctype, name, ["name", "docstatus"], as_dict=True, for_update=True, wait=False
            )
            if not header or header.docstatus != 1:
                frappe.throw(_("Purchase Order and Purchase Receipt sources must remain submitted."))
        for doctype, name in sorted(sources):
            childtype = f"{doctype} Item"
            fields = ["name", "parent", "item_code"]
            if doctype == "Purchase Receipt":
                fields.extend(("purchase_order", "purchase_order_item"))
            current = frappe.db.get_values(
                childtype,
                filters={"parent": name, "parenttype": doctype, "parentfield": "items"},
                fieldname=fields,
                as_dict=True,
                for_update=True,
                wait=False,
                order_by="name",
            )
            loaded = cast(Document, frappe.get_doc(doctype, name))
            locked_rows = {str(row.name): {field: row.get(field) for field in fields} for row in current}
            loaded_rows = {
                str(row.name): {field: row.get(field) for field in fields} for row in loaded.get("items", [])
            }
            if locked_rows != loaded_rows:
                frappe.throw(_("A Purchase Order or Receipt item changed while being checked. Please retry."))
            children[(doctype, name)] = locked_rows
        for row in rows:
            item_code = str(row.get("item_code"))
            po = str(row.get("purchase_order"))
            po_detail = str(row.get("po_detail"))
            po_row = children[("Purchase Order", po)].get(po_detail)
            if not po_row or po_row["parent"] != po or po_row["item_code"] != item_code:
                frappe.throw(_("Purchase Order item must belong to the selected order and Item."))
            if pr := str(row.get("purchase_receipt") or ""):
                pr_detail = str(row.get("pr_detail"))
                pr_row = children[("Purchase Receipt", pr)].get(pr_detail)
                if (
                    not pr_row
                    or pr_row["parent"] != pr
                    or pr_row["item_code"] != item_code
                    or pr_row["purchase_order"] != po
                    or pr_row["purchase_order_item"] != po_detail
                ):
                    frappe.throw(
                        _("Purchase Receipt item must match the selected Item and Purchase Order item.")
                    )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw(_("Purchase Invoice source is being updated. Please retry."))


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    """Record the active owner as the unsigned maker of the native review route."""
    del method
    require_permission(doc, "write")
    owner = resolve_user(str(doc.get("owner") or ""))
    actor = resolve_user(str(frappe.session.user or ""))
    if owner != actor:
        frappe.throw(_("Only the Purchase Invoice owner can send it for review."))
    doc.set("approval_maker_user", actor)


def capture_source_verification_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    _require_sources(doc)
    require_distinct_actors(str(doc.get("owner") or ""), frappe.session.user, ())
    doc.set("approval_critical_digest", get_approval_digest(doc))
    doc.set("approval_reviewer_user", frappe.session.user)
    from connect_diagnostics_core.api.erpnext.print_actions import capture_checked_action

    capture_checked_action(doc)
    if not doc.get("checked_by") or not doc.get("checked_signature"):
        frappe.throw(_("An Employee and approval signature are required for source verification."))


def capture_accounting_approval_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    _require_sources(doc)
    if doc.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("The Purchase Invoice changed after source verification and must be reviewed again."))
    require_distinct_actors(
        str(doc.get("owner") or ""), frappe.session.user, (str(doc.get("approval_reviewer_user") or ""),)
    )
    doc.set("approval_authorized_user", frappe.session.user)
    from connect_diagnostics_core.api.erpnext.print_actions import capture_authorized_action

    capture_authorized_action(doc)
    if not doc.get("authorized_by") or not doc.get("authorized_signature"):
        frappe.throw(_("An Employee and approval signature are required for accounting approval."))


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
