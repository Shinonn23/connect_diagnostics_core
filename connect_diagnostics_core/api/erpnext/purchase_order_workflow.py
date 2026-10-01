# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side approval boundary for the native Purchase Order Workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
    resolve_user,
)

DIGEST_VERSION = "purchase-order-commitment-v1"
REVIEW_STATE = "Purchase Order Pending Review"
APPROVAL_STATE = "Purchase Order Pending Approval"
APPROVED_STATE = "Purchase Order Approved"
SUBMITTED_STATE = "Purchase Order Submitted"
CANCELLED_STATE = "Purchase Order Cancelled"
_EXECUTION_FLAG = "purchase_order_workflow_execution"

# This is deliberately explicit.  Changes to this map are a digest-schema revision.
COMMITMENT_FIELDS: Mapping[str, tuple[str, ...]] = {
    "Purchase Order": (
        "owner",
        "supplier",
        "company",
        "transaction_date",
        "transaction_time",
        "schedule_date",
        "order_confirmation_no",
        "order_confirmation_date",
        "currency",
        "conversion_rate",
        "buying_price_list",
        "price_list_currency",
        "plc_conversion_rate",
        "party_account_currency",
        "ignore_pricing_rule",
        "supplier_address",
        "contact_person",
        "shipping_address",
        "billing_address",
        "dispatch_address",
        "drop_ship",
        "customer",
        "customer_contact_person",
        "set_warehouse",
        "set_from_warehouse",
        "set_reserve_warehouse",
        "supplier_warehouse",
        "shipping_rule",
        "incoterm",
        "named_place",
        "is_subcontracted",
        "is_old_subcontracting_flow",
        "is_internal_supplier",
        "represents_company",
        "inter_company_order_reference",
        "ref_sq",
        "taxes_and_charges",
        "tax_category",
        "apply_discount_on",
        "base_discount_amount",
        "additional_discount_percentage",
        "discount_amount",
        "disable_rounded_total",
        "payment_terms_template",
        "tc_name",
        "terms",
        "cost_center",
        "project",
        "department",
        "territory",
        "p2p_exception_reason",
        "custom_delivery_by",
        "eta",
        "custom_eta",
        "total_qty",
        "base_total",
        "total",
        "base_net_total",
        "net_total",
        "base_taxes_and_charges_added",
        "base_taxes_and_charges_deducted",
        "base_total_taxes_and_charges",
        "taxes_and_charges_added",
        "taxes_and_charges_deducted",
        "total_taxes_and_charges",
        "base_grand_total",
        "grand_total",
        "base_rounding_adjustment",
        "rounding_adjustment",
        "base_rounded_total",
        "rounded_total",
    ),
    "items": (
        "item_code",
        "supplier_part_no",
        "item_name",
        "description",
        "item_group",
        "brand",
        "manufacturer",
        "manufacturer_part_no",
        "qty",
        "uom",
        "stock_uom",
        "conversion_factor",
        "stock_qty",
        "price_list_rate",
        "base_price_list_rate",
        "discount_percentage",
        "discount_amount",
        "margin_type",
        "margin_rate_or_amount",
        "rate_with_margin",
        "base_rate_with_margin",
        "rate",
        "amount",
        "base_rate",
        "base_amount",
        "net_rate",
        "net_amount",
        "base_net_rate",
        "base_net_amount",
        "distributed_discount_amount",
        "item_tax_rate",
        "item_tax_template",
        "schedule_date",
        "expected_delivery_date",
        "warehouse",
        "from_warehouse",
        "material_request",
        "material_request_item",
        "supplier_quotation",
        "supplier_quotation_item",
        "blanket_order",
        "blanket_order_rate",
        "against_blanket_order",
        "sales_order",
        "sales_order_item",
        "project",
        "cost_center",
        "department",
        "territory",
        "expense_account",
        "is_free_item",
        "delivered_by_supplier",
        "bom",
        "include_exploded_items",
        "is_fixed_asset",
        "fg_item",
        "fg_item_qty",
        "production_plan",
        "production_plan_item",
        "production_plan_sub_assembly_item",
        "product_bundle",
        "sales_order_packed_item",
        "wip_composite_asset",
        "job_card",
    ),
    "taxes": (
        "category",
        "add_deduct_tax",
        "charge_type",
        "row_id",
        "allocate_full_amount_to_stock_items",
        "included_in_print_rate",
        "account_head",
        "cost_center",
        "project",
        "department",
        "territory",
        "description",
        "rate",
        "tax_amount",
        "tax_amount_after_discount_amount",
        "base_tax_amount",
        "base_tax_amount_after_discount_amount",
        "total",
        "base_total",
        "included_in_paid_amount",
        "account_currency",
        "is_tax_withholding_account",
        "net_amount",
        "base_net_amount",
        "set_by_item_tax_template",
        "dont_recompute_tax",
    ),
    "payment_schedule": (
        "payment_term",
        "description",
        "due_date",
        "invoice_portion",
        "payment_amount",
        "base_payment_amount",
        "mode_of_payment",
        "discount_date",
        "discount_type",
        "discount",
        "due_date_based_on",
        "credit_days",
        "credit_months",
        "discount_validity_based_on",
        "discount_validity",
    ),
    "supplied_items": (
        "main_item_code",
        "rm_item_code",
        "required_qty",
        "rate",
        "amount",
        "bom_detail_no",
        "reference_name",
        "conversion_factor",
        "stock_uom",
        "reserve_warehouse",
    ),
}
SNAPSHOT_FIELDS = frozenset(
    {
        "approval_critical_digest",
        "approval_digest_version",
        "approval_reviewer_user",
        "approval_authorized_user",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)


def _row_payload(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {"name": row.get("name"), **{field: row.get(field) for field in fields}}


def build_commitment_payload(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable server-side input to the approved digest schema."""
    get = doc.get
    payload: dict[str, Any] = {field: get(field) for field in COMMITMENT_FIELDS["Purchase Order"]}
    for table in ("items", "taxes", "payment_schedule", "supplied_items"):
        payload[table] = [_row_payload(row, COMMITMENT_FIELDS[table]) for row in (get(table) or [])]
    return payload


def _normalize_native_numbers(value: Any) -> Any:
    """Treat ERPNext's integer-to-float normalization as the same amount."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize_native_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_native_numbers(item) for item in value]
    return value


def get_commitment_digest(doc: Document | Mapping[str, Any]) -> str:
    """Return the versioned digest of all commitment-critical values."""
    return critical_digest(_normalize_native_numbers(build_commitment_payload(doc)))


def _employee_snapshot() -> tuple[str, str]:
    employee = cast(
        Mapping[str, Any],
        frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user},
            ["name", "approval_signature"],
            as_dict=True,
        ),
    )
    if not employee:
        frappe.throw(_("An Employee record is required for Purchase Order approval."))
    signature = str(employee.get("approval_signature") or "")
    if not signature:
        frappe.throw(_("An approval signature is required for Purchase Order approval."))
    return str(employee.get("name") or ""), signature


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    require_permission(doc, "write")
    if resolve_user(str(doc.get("owner") or "")) != resolve_user(frappe.session.user):
        frappe.throw(_("Only the Purchase Order owner can send it for review."))
    doc.set("approval_maker_user", frappe.session.user)


def capture_review_snapshot(doc: Document) -> None:
    """Workflow task: sign the current PO revision as reviewed."""
    require_permission(doc, "write")
    employee, signature = _employee_snapshot()
    require_distinct_actors(str(doc.get("approval_maker_user") or ""), frappe.session.user, ())
    digest = get_commitment_digest(doc)
    doc.set("approval_critical_digest", digest)
    doc.set("approval_digest_version", DIGEST_VERSION)
    doc.set("approval_reviewer_user", frappe.session.user)
    doc.set("checked_by", employee)
    doc.set("checked_at", now_datetime())
    doc.set("checked_signature", signature)


def capture_authorization_snapshot(doc: Document) -> None:
    """Workflow task: sign final authorization for the current PO revision."""
    require_permission(doc, "write")
    employee, signature = _employee_snapshot()
    require_distinct_actors(
        str(doc.get("owner") or ""),
        frappe.session.user,
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    if not doc.get("approval_critical_digest"):
        frappe.throw(_("Purchase Order review approval is required before final authorization."))
    if get_commitment_digest(doc) != doc.get("approval_critical_digest"):
        frappe.throw(_("Purchase Order approval is stale; return it for review again."))
    doc.set("approval_authorized_user", frappe.session.user)
    doc.set("authorized_by", employee)
    doc.set("authorized_at", now_datetime())
    doc.set("authorized_signature", signature)


def clear_approval_snapshots(doc: Document) -> None:
    """Workflow task: remove revision-bound evidence on return or correction."""
    for field in SNAPSHOT_FIELDS:
        doc.set(field, None)


def _reject_critical_changes_after_review(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if (
        not previous
        or previous.get("workflow_state") not in {APPROVAL_STATE, APPROVED_STATE}
        or doc.get("workflow_state") not in {APPROVAL_STATE, APPROVED_STATE}
    ):
        return
    previous_payload = build_commitment_payload(previous)
    current_payload = build_commitment_payload(doc)
    changed_fields = [
        fieldname for fieldname, value in previous_payload.items() if value != current_payload[fieldname]
    ]
    if changed_fields:
        frappe.throw(
            _("Commitment-critical Purchase Order fields cannot change after approval review: {0}.").format(
                ", ".join(changed_fields)
            )
        )


def validate_workflow(doc: Document, method: str | None = None) -> None:
    """Reject commitment mutations after review and invalidate stale evidence."""
    del method
    _reject_critical_changes_after_review(doc)


def _persisted_approval(doc: Document) -> Mapping[str, Any]:
    if not doc.name:
        frappe.throw(_("Purchase Order approval must be saved before submission."))
    row = frappe.db.get_value(
        "Purchase Order",
        doc.name,
        ["workflow_state", "owner", *SNAPSHOT_FIELDS],
        as_dict=True,
        for_update=True,
    )
    if not row:
        frappe.throw(_("Purchase Order approval could not be verified."))
    return cast(Mapping[str, Any], row)


def _execution_marker(doc: Document, action: str) -> dict[str, str]:
    return {
        "doctype": doc.doctype,
        "name": str(doc.name or ""),
        "action": action,
        "user": frappe.session.user,
    }


def _clear_execution_marker() -> None:
    setattr(frappe.flags, _EXECUTION_FLAG, None)


def authorize_submit_execution(doc: Document) -> None:
    """Workflow task: authorize this request's native Approved -> Submitted transition."""
    if not doc.name or doc.get("workflow_state") != SUBMITTED_STATE:
        frappe.throw(_("Purchase Order submit authorization requires the native Workflow transition."))
    setattr(frappe.flags, _EXECUTION_FLAG, _execution_marker(doc, "submit"))


def authorize_cancel_execution(doc: Document) -> None:
    """Workflow task: authorize this request's native Submitted -> Cancelled transition."""
    if not doc.name or doc.get("workflow_state") != CANCELLED_STATE:
        frappe.throw(_("Purchase Order cancel authorization requires the native Workflow transition."))
    setattr(frappe.flags, _EXECUTION_FLAG, _execution_marker(doc, "cancel"))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    """Fail closed before ERPNext's native Purchase Order submit effects."""
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != _execution_marker(doc, "submit"):
            frappe.throw(_("Purchase Order must be submitted through its approved Workflow action."))
        require_permission(doc, "submit")
        persisted = _persisted_approval(doc)
        if persisted.get("workflow_state") != APPROVED_STATE or doc.get("workflow_state") != SUBMITTED_STATE:
            frappe.throw(_("Purchase Order must be approved through the native Workflow before submission."))
        if persisted.get("approval_digest_version") != DIGEST_VERSION:
            frappe.throw(_("Purchase Order approval version is invalid."))
        digest = get_commitment_digest(doc)
        if (
            persisted.get("approval_critical_digest") != digest
            or doc.get("approval_critical_digest") != digest
        ):
            frappe.throw(_("Purchase Order approval is stale; return it for review again."))
        owner = str(persisted.get("owner") or doc.get("owner") or "")
        reviewer = str(persisted.get("approval_reviewer_user") or "")
        approver = str(persisted.get("approval_authorized_user") or "")
        if (
            not reviewer
            or not approver
            or not persisted.get("checked_signature")
            or not persisted.get("authorized_signature")
        ):
            frappe.throw(
                _("Purchase Order requires signed review and final authorization before submission.")
            )
        require_distinct_actors(owner, reviewer, ())
        require_distinct_actors(owner, approver, (reviewer,))
    finally:
        _clear_execution_marker()


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    """Prevent direct cancellation; native Workflow owns Submitted -> Cancelled."""
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != _execution_marker(doc, "cancel"):
            frappe.throw(_("Purchase Order must be cancelled through its Workflow action."))
        persisted_state = frappe.db.get_value(
            "Purchase Order",
            doc.name,
            "workflow_state",
            for_update=True,
        )
        if not (persisted_state == SUBMITTED_STATE and doc.get("workflow_state") == CANCELLED_STATE):
            frappe.throw(_("Submitted Purchase Orders must be cancelled through the native Workflow."))
    finally:
        _clear_execution_marker()
