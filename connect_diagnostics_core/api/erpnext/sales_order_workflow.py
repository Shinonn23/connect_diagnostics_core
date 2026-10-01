# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Local.test-only native Sales Order approval adapter."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from erpnext.selling.doctype.customer.customer import get_credit_limit
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

DEMO_REVISION = "D-SALES-DEMO-2026-09-23.1"
DEMO_SITE = "local.test"
APPROVAL_STATES = frozenset(
    {
        "Sales Order Pending Commercial/Credit Review",
        "Sales Order Pending Final Approval",
        "Sales Order Approved",
    }
)
CRITICAL_FIELDS = (
    "customer",
    "company",
    "transaction_date",
    "delivery_date",
    "order_type",
    "currency",
    "conversion_rate",
    "selling_price_list",
    "price_list_currency",
    "taxes_and_charges",
    "shipping_rule",
    "payment_terms_template",
    "tc_name",
    "incoterm",
    "named_place",
    "items",
    "taxes",
    "payment_schedule",
    "grand_total",
    "net_total",
    "base_grand_total",
)
DERIVED_FIELDS = frozenset(
    {
        "status",
        "per_billed",
        "per_delivered",
        "billing_status",
        "delivery_status",
        "billed_amt",
        "delivered_amount",
        "advance_paid",
        "total_commission",
        "rounded_total",
        "base_rounded_total",
        "rounded_total_difference",
        "base_rounded_total_difference",
        "company_tax_id",
        "base_net_total",
        "total_qty",
        "total_net_weight",
        "total",
        "net_total",
        "grand_total",
        "base_total_taxes_and_charges",
        "total_taxes_and_charges",
        "base_discount_amount",
        "discount_amount",
        "in_words",
        "base_in_words",
        "customer_name",
        "address_display",
        "contact_display",
        "shipping_address_display",
        "terms",
        "letter_head",
    }
)
ITEM_FIELDS = (
    "item_code",
    "qty",
    "uom",
    "conversion_factor",
    "rate",
    "price_list_rate",
    "margin_rate_or_amount",
    "discount_percentage",
    "discount_amount",
    "delivery_date",
    "warehouse",
)
CHILD_STRUCTURAL_FIELDS = frozenset(
    {
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
        "doctype",
    }
)
ITEM_NATIVE_DERIVED_FIELDS = frozenset(
    {
        "actual_qty",
        "amount",
        "base_amount",
        "base_net_amount",
        "base_net_rate",
        "base_rate",
        "net_amount",
        "net_rate",
        "stock_qty",
        "total_weight",
    }
)
SNAPSHOT_FIELDS = frozenset(
    {
        "workflow_state",
        "approval_revision",
        "approval_digest",
        "approval_maker_user",
        "approval_maker_at",
        "approval_reviewer_user",
        "approval_reviewer_at",
        "approval_approver_user",
        "approval_approver_at",
        "modified",
        "modified_by",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)


def _enabled() -> bool:
    config = frappe.get_site_config()
    return (
        cint(config.get("sales_order_approval_demo_enabled")) == 1
        and str(config.get("sales_order_approval_demo_site") or "") == DEMO_SITE
        and str(getattr(frappe.local, "site", "")) == DEMO_SITE
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain(value: Any) -> Any:
    if isinstance(value, Document):
        return {
            str(key): _plain(item)
            for key, item in value.as_dict(no_nulls=True).items()
            if key not in {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    return value


def _credit_inputs(doc: Document) -> dict[str, Any]:
    limit = (
        get_credit_limit(_text(doc.get("customer")), _text(doc.get("company"))) if doc.get("customer") else 0
    )
    direct = (
        frappe.db.get_value(
            "Customer Credit Limit",
            {"parent": doc.get("customer"), "parenttype": "Customer", "company": doc.get("company")},
            ["credit_limit", "bypass_credit_limit_check"],
            as_dict=True,
        )
        or {}
    )
    group = frappe.db.get_value("Customer", doc.get("customer"), "customer_group")
    group_limit = (
        frappe.db.get_value(
            "Customer Credit Limit",
            {"parent": group, "parenttype": "Customer Group", "company": doc.get("company")},
            ["credit_limit", "bypass_credit_limit_check"],
            as_dict=True,
        )
        or {}
    )
    company_limit = frappe.db.get_value("Company", doc.get("company"), "credit_limit")
    return {
        "effective_credit_limit": limit,
        "customer_credit_limit": direct.get("credit_limit"),
        "customer_credit_limit_bypass": bool(direct.get("bypass_credit_limit_check")),
        "customer_group": group,
        "customer_group_credit_limit": group_limit.get("credit_limit"),
        "customer_group_credit_limit_bypass": bool(group_limit.get("bypass_credit_limit_check")),
        "company_credit_limit": company_limit,
        "credit_controller": frappe.db.get_single_value("Accounts Settings", "credit_controller"),
    }


def approval_payload(doc: Document) -> dict[str, Any]:
    payload: dict[str, Any] = {"revision": DEMO_REVISION, "credit": _credit_inputs(doc)}
    for fieldname, value in doc.as_dict(no_nulls=True).items():
        if (
            fieldname in SNAPSHOT_FIELDS
            or fieldname in DERIVED_FIELDS
            or fieldname
            in {
                "name",
                "owner",
                "creation",
                "modified",
                "modified_by",
                "docstatus",
                "idx",
            }
        ):
            continue
        if fieldname == "payment_schedule":
            payload[fieldname] = [
                {key: _plain(item) for key, item in row.items() if key not in CHILD_STRUCTURAL_FIELDS}
                for row in (value or [])
            ]
        elif fieldname == "items":
            payload[fieldname] = [
                {
                    key: _plain(item)
                    for key, item in row.items()
                    if key not in CHILD_STRUCTURAL_FIELDS | ITEM_NATIVE_DERIVED_FIELDS
                }
                for row in (value or [])
            ]
        else:
            payload[fieldname] = _plain(value)
    return payload


def approval_digest(doc: Document) -> str:
    encoded = json.dumps(approval_payload(doc), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_enabled() -> None:
    if not _enabled():
        frappe.throw(_("Sales Order approval demo is not enabled on this site."))


def _employee_signature(user: str) -> tuple[str, str]:
    row = frappe.db.get_value("Employee", {"user_id": user}, ["name", "approval_signature"], as_dict=True)
    if not row or not _text(row.get("name")) or not _text(row.get("approval_signature")):
        frappe.throw(_("The workflow actor must have a linked Employee with a signature."))
    return _text(row.get("name")), _text(row.get("approval_signature"))


def _distinct_actors(doc: Document) -> bool:
    actors = [
        doc.get("approval_maker_user"),
        doc.get("approval_reviewer_user"),
        doc.get("approval_approver_user"),
    ]
    return all(_text(actor) for actor in actors) and len(set(actors)) == 3


def capture_sales_order_demo_maker(doc: Document) -> None:
    _require_enabled()
    if doc.doctype != "Sales Order":
        frappe.throw(_("This transition task only supports Sales Order."))
    if doc.get("workflow_state") != "Sales Order Pending Commercial/Credit Review":
        frappe.throw(_("Sales Order maker capture requires the commercial/credit review state."))
    if any(
        doc.get(fieldname)
        for fieldname in (
            "approval_maker_user",
            "approval_digest",
            "approval_reviewer_user",
            "approval_approver_user",
        )
    ):
        frappe.throw(_("Sales Order approval maker is already recorded."))
    doc.set("approval_maker_user", frappe.session.user)
    doc.set("approval_maker_at", now_datetime())
    doc.set("approval_revision", DEMO_REVISION)
    doc.set("approval_digest", approval_digest(doc))


def capture_sales_order_demo_review(doc: Document) -> None:
    _require_enabled()
    if doc.get("workflow_state") != "Sales Order Pending Final Approval" or doc.get(
        "approval_digest"
    ) != approval_digest(doc):
        frappe.throw(_("Sales Order changed before commercial/credit review."))
    employee, signature = _employee_signature(frappe.session.user)
    if frappe.session.user == doc.get("approval_maker_user") or not _text(doc.get("approval_maker_user")):
        frappe.throw(_("The Sales Order maker cannot perform commercial/credit review."))
    doc.set("approval_reviewer_user", frappe.session.user)
    doc.set("approval_reviewer_at", now_datetime())
    if (
        doc.get("checked_by") != employee
        or doc.get("checked_signature") != signature
        or not _text(doc.get("checked_at"))
    ):
        frappe.throw(_("Sales Order checked signature is required before review."))


def capture_sales_order_demo_final_approval(doc: Document) -> None:
    _require_enabled()
    if doc.get("workflow_state") != "Sales Order Approved" or not _text(doc.get("checked_signature")):
        frappe.throw(_("Sales Order review evidence is incomplete or stale."))
    if doc.get("approval_digest") != approval_digest(doc):
        frappe.throw(_("Sales Order changed after commercial/credit review; return it for correction."))
    employee, signature = _employee_signature(frappe.session.user)
    if frappe.session.user in {doc.get("approval_maker_user"), doc.get("approval_reviewer_user")}:
        frappe.throw(_("The Sales Order maker or reviewer cannot perform final approval."))
    doc.set("approval_approver_user", frappe.session.user)
    doc.set("approval_approver_at", now_datetime())
    if (
        doc.get("authorized_by") != employee
        or doc.get("authorized_signature") != signature
        or not _text(doc.get("authorized_at"))
    ):
        frappe.throw(_("Sales Order authorized signature is required before final approval."))


def clear_sales_order_demo_approval(doc: Document) -> None:
    _require_enabled()
    for fieldname in (
        "approval_revision",
        "approval_digest",
        "approval_maker_user",
        "approval_maker_at",
        "approval_reviewer_user",
        "approval_reviewer_at",
        "checked_by",
        "checked_at",
        "checked_signature",
        "approval_approver_user",
        "approval_approver_at",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        doc.set(fieldname, None)


def authorize_sales_order_demo_submission(doc: Document) -> None:
    _require_enabled()
    if doc.doctype != "Sales Order" or doc.get("workflow_state") != "Sales Order Submitted":
        frappe.throw(_("Sales Order must be approved before posting."))
    if frappe.session.user != doc.get("approval_approver_user") or not _distinct_actors(doc):
        frappe.throw(_("Current Sales Order approval evidence is missing or stale."))
    frappe.flags.sales_order_demo_submission = {
        "doctype": doc.doctype,
        "name": doc.name,
        "approval_revision": doc.get("approval_revision"),
        "approval_digest": doc.get("approval_digest"),
        "action": "Post Sales Order",
        "actor": frappe.session.user,
    }


def clear_sales_order_demo_submission() -> None:
    frappe.flags.sales_order_demo_submission = None


def _critical_changed(doc: Document, previous: Document) -> bool:
    return approval_digest(doc) != approval_digest(previous)


def _disallowed_changed(doc: Document, previous: Document) -> bool:
    """Fail closed for every field not explicitly part of the transition allowlist."""
    for fieldname in doc.meta.get_valid_columns():
        if (
            fieldname in SNAPSHOT_FIELDS
            or fieldname in DERIVED_FIELDS
            or fieldname in {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
        ):
            continue
        if doc.get(fieldname) != previous.get(fieldname):
            return True
    for fieldname in ("items", "taxes", "payment_schedule"):
        current_rows = [_plain(row) for row in (doc.get(fieldname) or [])]
        previous_rows = [_plain(row) for row in (previous.get(fieldname) or [])]
        if current_rows != previous_rows:
            return True
    return False


def validate_sales_order_demo(doc: Document, method: str | None = None) -> None:
    del method
    if not _enabled():
        return
    previous = doc.get_doc_before_save()
    if (
        previous
        and previous.get("workflow_state") == "Sales Order Draft"
        and doc.get("workflow_state") == "Sales Order Pending Commercial/Credit Review"
        and doc.get("approval_maker_user")
    ):
        doc.set("approval_digest", approval_digest(doc))
    if (
        previous
        and previous.get("workflow_state") == "Sales Order Pending Commercial/Credit Review"
        and doc.get("workflow_state") == "Sales Order Pending Final Approval"
    ):
        doc.set("approval_digest", approval_digest(doc))
    if (
        previous
        and previous.get("workflow_state") in APPROVAL_STATES
        and previous.get("workflow_state") == doc.get("workflow_state")
    ):
        if _critical_changed(doc, previous) or _disallowed_changed(doc, previous):
            frappe.throw(
                _(
                    "Critical Sales Order fields cannot change after approval review; return it for correction."
                )
            )
    if doc.get("amended_from") and doc.get("docstatus") == 0:
        clear_sales_order_demo_approval(doc)


def validate_sales_order_demo_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    if not _enabled():
        return
    marker = getattr(frappe.flags, "sales_order_demo_submission", None)
    try:
        persisted = frappe.db.get_value(
            "Sales Order",
            doc.name,
            [
                "docstatus",
                "workflow_state",
                "approval_revision",
                "approval_digest",
                "approval_maker_user",
                "approval_maker_at",
                "approval_reviewer_user",
                "approval_reviewer_at",
                "approval_approver_user",
                "approval_approver_at",
                "checked_by",
                "checked_at",
                "checked_signature",
                "authorized_by",
                "authorized_at",
                "authorized_signature",
            ],
            for_update=True,
            as_dict=True,
        )
        if not persisted or persisted.get("workflow_state") != "Sales Order Approved":
            frappe.throw(_("Sales Order must have current native approval before submission."))
        expected = {
            "doctype": "Sales Order",
            "name": doc.name,
            "approval_revision": DEMO_REVISION,
            "approval_digest": doc.get("approval_digest"),
            "action": "Post Sales Order",
            "actor": frappe.session.user,
        }
        if marker != expected or persisted.get("approval_digest") != doc.get("approval_digest"):
            frappe.throw(_("Sales Order submission requires the current native Post approval action."))
        if doc.get("approval_digest") != approval_digest(doc):
            frappe.throw(_("Sales Order changed after final approval; return it for correction."))
        if not frappe.has_permission("Sales Order", "submit", doc=doc):
            frappe.throw(_("You do not have permission to submit this Sales Order."))
        for fieldname, value in persisted.items():
            if fieldname not in {"docstatus", "workflow_state"} and value != doc.get(fieldname):
                frappe.throw(_("Sales Order approval evidence changed before submission."))
        if (
            not _distinct_actors(doc)
            or not _text(doc.get("checked_signature"))
            or not _text(doc.get("authorized_signature"))
        ):
            frappe.throw(_("Sales Order approval evidence is incomplete."))
    finally:
        clear_sales_order_demo_submission()


def validate_sales_order_demo_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    if _enabled():
        persisted = frappe.db.get_value("Sales Order", doc.name, "workflow_state", for_update=True)
        if persisted != "Sales Order Submitted" or doc.get("workflow_state") != "Sales Order Cancelled":
            frappe.throw(_("Sales Order cancellation must use the native Post-to-Cancel transition."))
