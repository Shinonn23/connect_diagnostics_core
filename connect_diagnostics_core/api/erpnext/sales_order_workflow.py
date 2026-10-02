# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native Sales Order approval adapter."""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from erpnext.accounts.party import get_party_account
from erpnext.selling.doctype.customer.customer import get_credit_limit
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.api.frappe.approval_controls import require_interactive_user
from connect_diagnostics_core.api.frappe.approval_routes import get_route

APPROVAL_REVISION = "sales-order-native-v1"
_CANCELLATION_FLAG = "connect_sales_order_cancellation"
APPROVAL_STATES = frozenset(
    {
        "Sales Order Pending Review",
        "Sales Order Reviewed",
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
        "billing_authority_revision",
        "billing_authority_digest",
        "billing_authorized_by",
        "billing_authorized_at",
        "billing_authorized_signature",
        "billing_authority_source_state",
        "billing_receivable_account",
    }
)

BILLING_AUTHORITY_REVISION = "sales-order-billing-v2"
_BILLING_AUTHORITY_FIELDS = frozenset(
    {
        "billing_authority_revision",
        "billing_authority_digest",
        "billing_authorized_by",
        "billing_authorized_at",
        "billing_authorized_signature",
        "billing_authority_source_state",
        "billing_receivable_account",
    }
)
_BILLING_WRITE: ContextVar[tuple[Document, str, str] | None] = ContextVar(
    "sales_order_billing_write", default=None
)
_BILLING_HEADER_FIELDS = (
    "customer",
    "company",
    "transaction_date",
    "delivery_date",
    "currency",
    "conversion_rate",
    "order_type",
    "selling_price_list",
    "price_list_currency",
    "taxes_and_charges",
    "payment_terms_template",
    "tc_name",
    "incoterm",
    "named_place",
    "customer_address",
    "shipping_address_name",
    "company_address",
    "contact_person",
    "project",
    "net_total",
    "grand_total",
    "base_grand_total",
    "total_taxes_and_charges",
    "discount_amount",
    "additional_discount_percentage",
    "apply_discount_on",
)
_BILLING_ITEM_FIELDS = (
    "name",
    "item_code",
    "item_group",
    "asset",
    "qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "rate",
    "price_list_rate",
    "discount_percentage",
    "discount_amount",
    "amount",
    "net_amount",
    "warehouse",
    "income_account",
    "cost_center",
    "project",
    "item_tax_template",
    "item_tax_rate",
    "delivery_date",
    "is_fixed_asset",
)
_BILLING_TAX_FIELDS = (
    "charge_type",
    "row_id",
    "account_head",
    "cost_center",
    "description",
    "rate",
    "tax_amount",
    "included_in_print_rate",
    "included_in_paid_amount",
)
_BILLING_SCHEDULE_FIELDS = (
    "payment_term",
    "due_date",
    "invoice_portion",
    "payment_amount",
    "mode_of_payment",
)


def billing_dimension_fields() -> tuple[str, ...]:
    """Current native accounting and inventory fields that can affect a mapped invoice."""
    fields = {str(field) for field in get_accounting_dimensions() or []}
    fields.update(
        str(row.get("fieldname")) for row in get_inventory_dimensions() or [] if row.get("fieldname")
    )
    fields.update({"storage_location", "to_storage_location", "from_storage_location"})
    return tuple(sorted(fields))


def billing_authority_payload(doc: Document) -> dict[str, Any]:
    """Finite commercial input approved by Finance, independent of native billing progress."""
    dimensions = billing_dimension_fields()
    item_codes = sorted(
        {_text(row.get("item_code")) for row in doc.get("items") or [] if row.get("item_code")}
    )
    item_identities = (
        {
            row.name: row
            for row in frappe.get_all(
                "Item",
                filters={"name": ["in", item_codes]},
                fields=["name", "is_stock_item", "is_fixed_asset", "item_group"],
            )
        }
        if item_codes
        else {}
    )
    if set(item_identities) != set(item_codes):
        frappe.throw(_("A Sales Order Item no longer exists."))
    items = []
    for row in doc.get("items") or []:
        item_code = _text(row.get("item_code"))
        item_identity = item_identities.get(item_code) or {}
        items.append(
            {
                **{field: _billing_value(row.get(field)) for field in (*_BILLING_ITEM_FIELDS, *dimensions)},
                "item_identity": {
                    field: _billing_value(item_identity.get(field))
                    for field in ("is_stock_item", "is_fixed_asset", "item_group")
                },
            }
        )
    return {
        "revision": BILLING_AUTHORITY_REVISION,
        "receivable_account": _text(doc.get("billing_receivable_account")),
        "header": {field: _billing_value(doc.get(field)) for field in (*_BILLING_HEADER_FIELDS, *dimensions)},
        "items": items,
        "taxes": [
            {field: _billing_value(row.get(field)) for field in _BILLING_TAX_FIELDS}
            for row in doc.get("taxes") or []
        ],
        "payment_schedule": [
            {field: _billing_value(row.get(field)) for field in _BILLING_SCHEDULE_FIELDS}
            for row in doc.get("payment_schedule") or []
        ],
        "finance_actor": _text(doc.get("approval_approver_user")),
        "finance_signature": _text(doc.get("authorized_signature")),
    }


def billing_authority_digest(doc: Document) -> str:
    encoded = json.dumps(billing_authority_payload(doc), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def require_billing_authority(doc: Document) -> None:
    if (
        doc.get("billing_authority_revision") != BILLING_AUTHORITY_REVISION
        or doc.get("billing_authority_source_state") != "Sales Order Approved"
        or doc.get("billing_authorized_by") != doc.get("approval_approver_user")
        or doc.get("billing_authorized_signature") != doc.get("authorized_signature")
        or not _text(doc.get("billing_receivable_account"))
        or not _text(doc.get("billing_authorized_at"))
        or doc.get("billing_authority_digest") != billing_authority_digest(doc)
    ):
        frappe.throw(_("Sales Order billing authority is missing or its approved inputs changed."))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _billing_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
        if not number.is_finite():
            frappe.throw(_("Sales Order billing input must be finite."))
        return str(number.normalize())
    if isinstance(value, (date, datetime, time, timedelta)):
        return str(value)
    return value


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
    payload: dict[str, Any] = {"revision": APPROVAL_REVISION, "credit": _credit_inputs(doc)}
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


def capture_sales_order_maker(doc: Document) -> None:
    if doc.doctype != "Sales Order":
        frappe.throw(_("This transition task only supports Sales Order."))
    if doc.get("workflow_state") != "Sales Order Pending Review":
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
    doc.set("approval_revision", APPROVAL_REVISION)
    doc.set("approval_digest", approval_digest(doc))


def capture_sales_order_review(doc: Document) -> None:
    if doc.get("workflow_state") != "Sales Order Reviewed" or doc.get("approval_digest") != approval_digest(
        doc
    ):
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


def capture_sales_order_final_approval(doc: Document) -> None:
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
    for row in doc.get("items") or []:
        if not _text(row.get("income_account")) or not _text(row.get("cost_center")):
            frappe.throw(
                _("Each Sales Order item needs an income account and cost center before Finance approval.")
            )
    receivable = get_party_account("Customer", _text(doc.get("customer")), _text(doc.get("company")))
    if not _text(receivable):
        frappe.throw(_("A customer receivable account is required before Finance approval."))
    doc.set("billing_receivable_account", receivable)
    doc.set("billing_authority_revision", BILLING_AUTHORITY_REVISION)
    doc.set("billing_authorized_by", frappe.session.user)
    doc.set("billing_authorized_at", now_datetime())
    doc.set("billing_authorized_signature", signature)
    doc.set("billing_authority_source_state", "Sales Order Approved")
    doc.set("billing_authority_digest", billing_authority_digest(doc))
    _BILLING_WRITE.set((doc, "capture", frappe.session.user))


def clear_sales_order_approval(doc: Document) -> None:
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
        "billing_authority_revision",
        "billing_authority_digest",
        "billing_authorized_by",
        "billing_authorized_at",
        "billing_authorized_signature",
        "billing_authority_source_state",
        "billing_receivable_account",
    ):
        doc.set(fieldname, None)
    _BILLING_WRITE.set((doc, "clear", frappe.session.user))


def authorize_sales_order_submission(doc: Document) -> None:
    clear_sales_order_submission()
    if doc.doctype != "Sales Order" or doc.get("workflow_state") != "Sales Order Submitted":
        frappe.throw(_("Sales Order must be approved before posting."))
    if not _distinct_actors(doc):
        frappe.throw(_("Current Sales Order approval evidence is missing or stale."))
    persisted = frappe.db.get_value(
        "Sales Order", doc.name, ["workflow_state", "docstatus"], as_dict=True, for_update=True
    )
    if (
        not persisted
        or persisted.get("workflow_state") != "Sales Order Approved"
        or persisted.get("docstatus") != 0
    ):
        frappe.throw(_("Sales Order must have current native approval before posting."))
    actor = require_interactive_user(doc, get_route("sales_order_credit").execution_roles, "submit")
    frappe.flags.sales_order_submission = {
        "doctype": doc.doctype,
        "name": doc.name,
        "approval_revision": doc.get("approval_revision"),
        "approval_digest": doc.get("approval_digest"),
        "action": "Post Sales Order",
        "actor": actor,
    }


def clear_sales_order_submission() -> None:
    frappe.flags.sales_order_submission = None


def _cancellation_marker(doc: Document) -> dict[str, str]:
    return {
        "doctype": doc.doctype,
        "name": str(doc.name or ""),
        "action": "cancel",
        "user": str(frappe.session.user or ""),
    }


def authorize_sales_order_cancellation(doc: Document) -> None:
    if doc.doctype != "Sales Order" or not doc.name or doc.get("workflow_state") != "Sales Order Cancelled":
        frappe.throw(_("Sales Order cancel authorization requires the native Workflow transition."))
    persisted = frappe.db.get_value(
        "Sales Order",
        doc.name,
        ["workflow_state", "docstatus"],
        as_dict=True,
        for_update=True,
    )
    if (
        not persisted
        or persisted.get("workflow_state") != "Sales Order Submitted"
        or persisted.get("docstatus") != 1
    ):
        frappe.throw(_("Only a submitted Sales Order can be cancelled through this transition."))
    if not frappe.has_permission("Sales Order", "cancel", doc=doc):
        frappe.throw(_("You do not have permission to cancel this Sales Order."))
    setattr(frappe.flags, _CANCELLATION_FLAG, _cancellation_marker(doc))


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


def validate_sales_order(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    if previous and any(doc.get(field) != previous.get(field) for field in _BILLING_AUTHORITY_FIELDS):
        proof = _BILLING_WRITE.get()
        capture = (
            previous.get("workflow_state") == "Sales Order Reviewed"
            and doc.get("workflow_state") == "Sales Order Approved"
            and proof is not None
            and proof[0] is doc
            and proof[1:] == ("capture", frappe.session.user)
        )
        cleared = (
            previous.get("workflow_state")
            in {"Sales Order Pending Review", "Sales Order Reviewed", "Sales Order Approved"}
            and doc.get("workflow_state") in {"Sales Order Returned", "Sales Order Rejected"}
            and proof is not None
            and proof[0] is doc
            and proof[1:] == ("clear", frappe.session.user)
            and all(not doc.get(field) for field in _BILLING_AUTHORITY_FIELDS)
        )
        if not (capture or cleared):
            frappe.throw(
                _("Sales Order billing authority can only change through its native approval transition.")
            )
        if capture:
            require_billing_authority(doc)
        _BILLING_WRITE.set(None)
    if (
        previous
        and previous.get("workflow_state") == "Sales Order Draft"
        and doc.get("workflow_state") == "Sales Order Pending Review"
        and doc.get("approval_maker_user")
    ):
        doc.set("approval_digest", approval_digest(doc))
    if (
        previous
        and previous.get("workflow_state") == "Sales Order Pending Review"
        and doc.get("workflow_state") == "Sales Order Reviewed"
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
        clear_sales_order_approval(doc)


def validate_sales_order_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    marker = getattr(frappe.flags, "sales_order_submission", None)
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
                "billing_authority_revision",
                "billing_authority_digest",
                "billing_authorized_by",
                "billing_authorized_at",
                "billing_authorized_signature",
                "billing_authority_source_state",
                "billing_receivable_account",
            ],
            for_update=True,
            as_dict=True,
        )
        if (
            not persisted
            or persisted.get("workflow_state") != "Sales Order Approved"
            or persisted.get("docstatus") != 0
        ):
            frappe.throw(_("Sales Order must have current native approval before submission."))
        actor = require_interactive_user(doc, get_route("sales_order_credit").execution_roles, "submit")
        expected = {
            "doctype": "Sales Order",
            "name": doc.name,
            "approval_revision": APPROVAL_REVISION,
            "approval_digest": doc.get("approval_digest"),
            "action": "Post Sales Order",
            "actor": actor,
        }
        if marker != expected or persisted.get("approval_digest") != doc.get("approval_digest"):
            frappe.throw(_("Sales Order submission requires the current native Post approval action."))
        if doc.get("approval_digest") != approval_digest(doc):
            frappe.throw(_("Sales Order changed after final approval; return it for correction."))
        require_billing_authority(doc)
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
        clear_sales_order_submission()


def validate_sales_order_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        marker = getattr(frappe.flags, _CANCELLATION_FLAG, None)
        persisted = frappe.db.get_value(
            "Sales Order",
            doc.name,
            ["workflow_state", "docstatus"],
            as_dict=True,
            for_update=True,
        )
        if (
            marker != _cancellation_marker(doc)
            or not persisted
            or persisted.get("workflow_state") != "Sales Order Submitted"
            or persisted.get("docstatus") != 1
            or doc.get("workflow_state") != "Sales Order Cancelled"
        ):
            frappe.throw(_("Sales Order cancellation must use the native Post-to-Cancel transition."))
        if not frappe.has_permission("Sales Order", "cancel", doc=doc):
            frappe.throw(_("You do not have permission to cancel this Sales Order."))
    finally:
        setattr(frappe.flags, _CANCELLATION_FLAG, None)
