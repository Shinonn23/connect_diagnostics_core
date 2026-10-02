# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Sales invoice generation from signed Sales Order authority and submitted delivery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from secrets import compare_digest, token_urlsafe
from typing import Any, cast

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice as from_sales_order
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice as from_delivery_note
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.api.erpnext.sales_order_workflow import (
    BILLING_AUTHORITY_REVISION,
    billing_dimension_fields,
    require_billing_authority,
)
from connect_diagnostics_core.connect_diagnostics_core.doctype.sales_invoice_generation.sales_invoice_generation import (
    SalesInvoiceGeneration,
    _system_write,
)

RUN_DOCTYPE = "Sales Invoice Generation"


class _AllocationRequiredError(frappe.ValidationError):
    """A partial source contains a fixed value needing an accounting allocation."""


class _CrossRouteFixedPoolError(frappe.ValidationError):
    """An ordinary invoice cannot allocate a charge covering excluded Asset rows."""


class _SourceAuthorityMismatchError(frappe.ValidationError):
    """The source cannot be composed from the signed SO billing authority."""


class _LegacyAuthorityError(frappe.ValidationError):
    """A pre-v2 SO/run cannot gain new billing authority by migration."""


ALLOCATION_REQUIRED_STATUS = "Approved accounting allocation required for a partial source group."
PROVENANCE_FIELDS = (
    "connect_invoice_generation_run",
    "connect_invoice_source_doctype",
    "connect_invoice_source_name",
    "connect_billing_authority_digest",
    "connect_source_group_digest",
    "connect_generated_by_actor",
    "connect_generated_at",
    "connect_generation_payload_digest",
)
INVOICE_HEADER_FIELDS = (
    "company",
    "customer",
    "currency",
    "conversion_rate",
    "posting_date",
    "due_date",
    "debit_to",
    "selling_price_list",
    "price_list_currency",
    "taxes_and_charges",
    "payment_terms_template",
    "apply_discount_on",
    "discount_amount",
    "additional_discount_percentage",
    "total",
    "net_total",
    "total_taxes_and_charges",
    "grand_total",
    "rounded_total",
    "base_grand_total",
    "base_rounded_total",
    "write_off_amount",
    "is_pos",
    "update_stock",
    "company_address",
    "customer_address",
    "shipping_address_name",
    "contact_person",
    "project",
    "base_total",
    "base_net_total",
    "base_total_taxes_and_charges",
    "paid_amount",
    "change_amount",
    "taxes_and_charges_added",
    "taxes_and_charges_deducted",
    "base_discount_amount",
)
INVOICE_ITEM_FIELDS = (
    "item_code",
    "sales_order",
    "so_detail",
    "delivery_note",
    "dn_detail",
    "qty",
    "stock_qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "rate",
    "price_list_rate",
    "discount_percentage",
    "discount_amount",
    "amount",
    "net_amount",
    "base_amount",
    "income_account",
    "cost_center",
    "warehouse",
    "project",
    "item_tax_template",
    "item_tax_rate",
    "asset",
    "base_rate",
    "base_net_rate",
    "base_net_amount",
    "net_rate",
    "stock_uom_rate",
)
INVOICE_TAX_FIELDS = (
    "charge_type",
    "row_id",
    "account_head",
    "cost_center",
    "description",
    "rate",
    "tax_amount",
    "total",
    "included_in_print_rate",
    "included_in_paid_amount",
    "base_tax_amount",
    "tax_amount_after_discount_amount",
    "base_tax_amount_after_discount_amount",
    "base_total",
)
INVOICE_SCHEDULE_FIELDS = ("payment_term", "due_date", "invoice_portion", "payment_amount", "mode_of_payment")
SO_APPROVED_INVOICE_HEADER_FIELDS = (
    "company",
    "customer",
    "currency",
    "conversion_rate",
    "selling_price_list",
    "price_list_currency",
    "taxes_and_charges",
    "payment_terms_template",
    "apply_discount_on",
    "discount_amount",
    "additional_discount_percentage",
    "company_address",
    "customer_address",
    "shipping_address_name",
    "contact_person",
    "project",
)
SO_APPROVED_INVOICE_ITEM_FIELDS = (
    "item_code",
    "uom",
    "stock_uom",
    "conversion_factor",
    "rate",
    "price_list_rate",
    "discount_percentage",
    "discount_amount",
    "income_account",
    "cost_center",
    "project",
    "item_tax_template",
    "item_tax_rate",
    "asset",
)
_STAGE: ContextVar[tuple[int, str, str, str, bool, SalesInvoiceGeneration, str] | None] = ContextVar(
    "sales_invoice_target_stage", default=None
)


def _scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
        if not number.is_finite():
            frappe.throw(_("Invoice financial input must be finite."))
        return str(number.normalize())
    if isinstance(value, (date, datetime, time, timedelta)):
        return str(value)
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_scalar).encode()
    ).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_rows(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), default=_scalar)


_SOURCE_HEADER_FIELDS = (
    "company",
    "customer",
    "currency",
    "conversion_rate",
    "transaction_date",
    "posting_date",
    "posting_time",
    "set_posting_time",
    "selling_price_list",
    "taxes_and_charges",
    "payment_terms_template",
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
)
_SOURCE_ROW_FIELDS = (
    "item_code",
    "item_group",
    "asset",
    "is_fixed_asset",
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
    "so_detail",
    "against_sales_order",
    "delivery_date",
)


def _source_financial_payload(source: Document, selected: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = billing_dimension_fields()
    by_name = {row.name: row for row in source.get("items") or []}
    return {
        "source": source.doctype,
        "name": source.name,
        "docstatus": source.docstatus,
        "header": {field: _scalar(source.get(field)) for field in (*_SOURCE_HEADER_FIELDS, *dimensions)},
        "taxes": [
            {field: _scalar(row.get(field)) for field in INVOICE_TAX_FIELDS}
            for row in source.get("taxes") or []
        ],
        "payment_schedule": [
            {field: _scalar(row.get(field)) for field in INVOICE_SCHEDULE_FIELDS}
            for row in source.get("payment_schedule") or []
        ],
        "rows": [
            {
                **item,
                "source_values": {
                    field: _scalar(by_name[item["source_row"]].get(field))
                    for field in (*_SOURCE_ROW_FIELDS, *dimensions)
                },
            }
            for item in selected
        ],
    }


def _invoice_payload(doc: Document) -> dict[str, Any]:
    """Finite native financial result sealed just before insert and compared on submit."""
    dimensions = billing_dimension_fields()
    return {
        "header": {field: _scalar(doc.get(field)) for field in (*INVOICE_HEADER_FIELDS, *dimensions)},
        "items": [
            {field: _scalar(row.get(field)) for field in (*INVOICE_ITEM_FIELDS, *dimensions)}
            for row in doc.get("items") or []
        ],
        "taxes": [
            {field: _scalar(row.get(field)) for field in (*INVOICE_TAX_FIELDS, *dimensions)}
            for row in doc.get("taxes") or []
        ],
        "payment_schedule": [
            {field: _scalar(row.get(field)) for field in INVOICE_SCHEDULE_FIELDS}
            for row in doc.get("payment_schedule") or []
        ],
    }


def _source_row(doc: Document, row: Document, sales_order: str) -> dict[str, Any]:
    return {
        "source_doctype": doc.doctype,
        "source_name": doc.name,
        "source_row": row.name,
        "sales_order_item": row.name if doc.doctype == "Sales Order" else _text(row.get("so_detail")),
        "sales_order": sales_order,
        "item_code": row.get("item_code"),
        "authorized_qty": _scalar(row.get("qty")),
    }


def _item_identities(rows: list[Document]) -> dict[str, dict[str, Any]]:
    codes = sorted({_text(row.get("item_code")) for row in rows if row.get("item_code")})
    if not codes:
        return {}
    found = frappe.get_all(
        "Item",
        filters={"name": ["in", codes]},
        fields=["name", "is_stock_item", "is_fixed_asset", "item_group"],
    )
    identities = {row.name: dict(row) for row in found}
    if set(identities) != set(codes):
        frappe.throw(_("A source Item no longer exists."))
    return identities


def _ordinary(row: Document, identity: dict[str, Any], *, stock: bool) -> bool:
    if _text(row.get("asset")) or row.get("is_fixed_asset") or identity.get("is_fixed_asset"):
        return False
    return bool(identity.get("is_stock_item")) is stock


def _load_submitted(doctype: str, name: str) -> Document:
    source = frappe.get_doc(doctype, name)
    if not frappe.has_permission(doctype, ptype="read", doc=source, user=frappe.session.user):
        raise frappe.PermissionError(_("You cannot read the Sales Invoice source."))
    if source.docstatus != 1:
        frappe.throw(_("Invoice source must remain submitted."))
    return source


def _authority(sales_order: str) -> Document:
    so = _load_submitted("Sales Order", sales_order)
    require_billing_authority(so)
    return so


def _group(source: Document, so: Document, kind: str, rows: list[Document]) -> dict[str, Any] | None:
    if not rows:
        return None
    if source.get("company") != so.get("company") or source.get("customer") != so.get("customer"):
        frappe.throw(_("Invoice source and Sales Order customer/company differ."))
    selected = [_source_row(source, row, _text(so.name)) for row in rows]
    selected.sort(key=lambda row: row["source_row"])
    selected_json = _source_rows(selected)
    source_digest = _digest(_source_financial_payload(source, selected))
    key = _digest((source.doctype, source.name, so.name, BILLING_AUTHORITY_REVISION, kind, source_digest))
    return {
        "source_doctype": source.doctype,
        "source_name": source.name,
        "sales_order": so.name,
        "billing_authority_revision": BILLING_AUTHORITY_REVISION,
        "group_kind": kind,
        "group_key": key,
        "source_rows_json": selected_json,
        "source_digest": source_digest,
        "billing_authority_digest": so.get("billing_authority_digest"),
        "generation_status": "Queued",
        "attempt_count": 0,
        "initiated_by": frappe.session.user,
    }


def _reserve(group: dict[str, Any]) -> str:
    """Unique key is the final concurrent replay arbiter; never generate a second run."""
    existing = frappe.db.get_value(RUN_DOCTYPE, {"group_key": group["group_key"]}, "name")
    if existing:
        return str(existing)
    run = frappe.get_doc({"doctype": RUN_DOCTYPE, **group})
    try:
        with _system_write(run, "insert"):
            run.insert()
    except frappe.DuplicateEntryError:
        # Current locking read sees the winner even under REPEATABLE READ's older snapshot.
        winner = frappe.db.sql(
            "SELECT name FROM `tabSales Invoice Generation` WHERE group_key=%s FOR UPDATE NOWAIT",
            (group["group_key"],),
            as_dict=True,
        )
        if winner:
            return str(winner[0]["name"])
        raise
    return str(run.name)


def _queue(run_name: str) -> None:
    frappe.enqueue(
        "connect_diagnostics_core.api.erpnext.auto_invoice_generation.process_sales_invoice_generation",
        queue="short",
        timeout=300,
        enqueue_after_commit=True,
        job_id=f"sales-invoice-generation:{run_name}",
        deduplicate=True,
        run_name=run_name,
    )


def enqueue_sales_order_service_group(doc: Document, method: str | None = None) -> None:
    del method
    if doc.doctype != "Sales Order" or doc.docstatus != 1:
        frappe.throw(_("Only a submitted Sales Order can initiate service invoicing."))
    if frappe.session.user in {"Administrator", "Guest"}:
        frappe.throw(_("A real Sales Manager must submit the Sales Order."))
    if not frappe.has_permission(doc.doctype, ptype="read", doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You cannot read the Sales Order."))
    require_billing_authority(doc)
    identities = _item_identities(list(doc.get("items") or []))
    rows = [
        row for row in doc.get("items") or [] if _ordinary(row, identities[_text(row.item_code)], stock=False)
    ]
    group = _group(doc, doc, "SO Service", rows)
    if group:
        _queue(_reserve(group))


def enqueue_delivery_note_stock_groups(doc: Document, method: str | None = None) -> None:
    del method
    if doc.doctype != "Delivery Note" or doc.docstatus != 1 or doc.get("is_return"):
        return
    if not frappe.has_permission(doc.doctype, ptype="read", doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You cannot read the Delivery Note."))
    identities = _item_identities(list(doc.get("items") or []))
    grouped: dict[str, list[Document]] = {}
    for row in doc.get("items") or []:
        if not _ordinary(row, identities[_text(row.item_code)], stock=True):
            continue
        so = _text(row.get("against_sales_order"))
        so_item = _text(row.get("so_detail"))
        if not so or not so_item:
            frappe.throw(_("A delivery stock row requires its approved Sales Order row."))
        grouped.setdefault(so, []).append(row)
    for so_name, rows in sorted(grouped.items()):
        so = _authority(so_name)
        by_id = {row.name: row for row in so.get("items") or []}
        for row in rows:
            approved = by_id.get(_text(row.get("so_detail")))
            if not approved or approved.get("item_code") != row.get("item_code"):
                frappe.throw(_("Delivery row does not match its approved Sales Order item."))
        group = _group(doc, so, "DN Stock", rows)
        if group:
            _queue(_reserve(group))


def _lock_run(name: str) -> SalesInvoiceGeneration:
    rows = frappe.db.sql(
        "SELECT name FROM `tabSales Invoice Generation` WHERE name=%s FOR UPDATE NOWAIT",
        (name,),
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Sales Invoice Generation no longer exists."))
    return cast(SalesInvoiceGeneration, frappe.get_doc(RUN_DOCTYPE, name))


def _lock_authority_then_run(name: str) -> SalesInvoiceGeneration:
    """Serialize every SO billing candidate before locking its individual run."""
    so_name = frappe.db.get_value(RUN_DOCTYPE, name, "sales_order")
    if not so_name:
        frappe.throw(_("Sales Invoice Generation no longer exists."))
    locked = frappe.db.sql(
        "SELECT name FROM `tabSales Order` WHERE name=%s FOR UPDATE NOWAIT", (so_name,), as_dict=True
    )
    if not locked:
        frappe.throw(_("Sales Order billing authority no longer exists."))
    run = _lock_run(name)
    if run.sales_order != so_name:
        frappe.throw(_("Sales Invoice Generation authority changed while locking."))
    return run


def _visible_run(run_name: str) -> SalesInvoiceGeneration:
    if not isinstance(run_name, str) or not run_name or len(run_name) > 140:
        frappe.throw(_("Select an existing Sales Invoice Generation run."))
    if not frappe.db.exists(RUN_DOCTYPE, run_name):
        frappe.throw(_("Select an existing Sales Invoice Generation run."))
    run = cast(SalesInvoiceGeneration, frappe.get_doc(RUN_DOCTYPE, run_name))
    user = frappe.session.user
    if user in {"Guest", "Administrator"}:
        raise frappe.PermissionError
    if run.source_doctype not in {"Sales Order", "Delivery Note"}:
        frappe.throw(_("Sales Invoice Generation has an invalid source."))
    source = frappe.get_doc(run.source_doctype, run.source_name)
    company = frappe.get_doc("Company", source.company)
    if (
        not frappe.has_permission(source.doctype, ptype="read", doc=source, user=user)
        or not frappe.has_permission(
            "Sales Order", ptype="read", doc=frappe.get_doc("Sales Order", run.sales_order), user=user
        )
        or not frappe.has_permission("Company", ptype="read", doc=company, user=user)
    ):
        raise frappe.PermissionError
    return run


@frappe.whitelist()
def get_sales_invoice_generation_status(run_name: str) -> dict[str, Any]:
    """Read exact run progress only when the actor can read its source and Company."""
    run = _visible_run(run_name)
    return {
        "data": {
            "name": run.name,
            "generation_status": run.generation_status,
            "failure_code": run.failure_code,
            "attempt_count": run.attempt_count,
            "last_error": run.last_error,
            "target_sales_invoice": run.target_sales_invoice,
            "generated_at": run.generated_at,
        },
        "message": "Sales Invoice Generation status loaded.",
    }


@frappe.whitelist()
def list_sales_invoice_generations(source_doctype: str, source_name: str, start: int = 0) -> dict[str, Any]:
    """List bounded source runs using native source, Sales Order and Company read scope."""
    if (
        source_doctype not in {"Sales Order", "Delivery Note"}
        or not isinstance(source_name, str)
        or not source_name
        or len(source_name) > 140
    ):
        frappe.throw(_("Select a Sales Order or Delivery Note."))
    try:
        page = int(start)
    except (TypeError, ValueError):
        frappe.throw(_("Invalid Sales Invoice Generation page."))
    if isinstance(start, bool) or page < 0 or page > 10000:
        frappe.throw(_("Invalid Sales Invoice Generation page."))
    user = frappe.session.user
    if user in {"Guest", "Administrator"}:
        raise frappe.PermissionError
    source = frappe.get_doc(source_doctype, source_name)
    if not frappe.has_permission(source_doctype, ptype="read", doc=source, user=user):
        raise frappe.PermissionError
    company = frappe.get_doc("Company", source.company)
    if not frappe.has_permission("Company", ptype="read", doc=company, user=user):
        raise frappe.PermissionError
    rows = frappe.get_all(
        RUN_DOCTYPE,
        filters={"source_doctype": source_doctype, "source_name": source_name},
        fields=[
            "name",
            "sales_order",
            "generation_status",
            "failure_code",
            "attempt_count",
            "last_error",
            "target_sales_invoice",
        ],
        order_by="name asc",
        start=page,
        page_length=50,
    )
    allowed_orders = (
        set(
            frappe.get_list(
                "Sales Order",
                filters={"name": ["in", sorted({_text(row.sales_order) for row in rows})]},
                pluck="name",
                user=user,
            )
        )
        if rows
        else set()
    )
    return {
        "data": [
            {
                field: row.get(field)
                for field in (
                    "name",
                    "generation_status",
                    "failure_code",
                    "attempt_count",
                    "last_error",
                    "target_sales_invoice",
                )
            }
            for row in rows
            if row.sales_order in allowed_orders
        ],
        "message": "Sales Invoice Generation runs loaded.",
    }


@frappe.whitelist(methods=["POST"])
def retry_sales_invoice_generation(run_name: str) -> dict[str, Any]:
    """Queue an existing failed run under the current authorized actor's identity."""
    run = _visible_run(run_name)
    if (
        run.generation_status not in {"Failed", "Pending Permission", "Queued"}
        or run.target_sales_invoice
        or run.failure_code
        in {"Allocation Required", "Cross-route Fixed Pool Unsupported", "Legacy Authority Hold"}
    ):
        frappe.throw(_("This Sales Invoice Generation run cannot be retried."))
    _queue(_text(run.name))
    return {
        "data": {"name": run.name, "generation_status": run.generation_status},
        "message": "Retry queued.",
    }


def _verify_group(run: SalesInvoiceGeneration) -> tuple[Document, Document, list[dict[str, Any]]]:
    if run.billing_authority_revision != BILLING_AUTHORITY_REVISION:
        frappe.throw(
            _("Legacy Sales Order billing requires a new Finance approval."), exc=_LegacyAuthorityError
        )
    if (
        run.source_doctype not in {"Sales Order", "Delivery Note"}
        or (run.source_doctype == "Sales Order" and run.group_kind != "SO Service")
        or (run.source_doctype == "Delivery Note" and run.group_kind != "DN Stock")
    ):
        frappe.throw(_("Sales Invoice Generation has an invalid source group."))
    source = _load_submitted(_text(run.source_doctype), _text(run.source_name))
    so = source if source.doctype == "Sales Order" else _authority(_text(run.sales_order))
    require_billing_authority(so)
    if (
        so.name != run.sales_order
        or run.billing_authority_revision != BILLING_AUTHORITY_REVISION
        or run.billing_authority_digest != so.get("billing_authority_digest")
    ):
        frappe.throw(_("Sales Order billing authority changed."))
    selected = json.loads(run.source_rows_json)
    if not isinstance(selected, list) or not selected:
        frappe.throw(_("Invoice group has no approved source rows."))
    identities = _item_identities(list(source.get("items") or []))
    by_id = {row.name: row for row in source.get("items") or []}
    current = []
    for item in selected:
        if not isinstance(item, dict) or set(item) != {
            "source_doctype",
            "source_name",
            "source_row",
            "sales_order_item",
            "sales_order",
            "item_code",
            "authorized_qty",
        }:
            frappe.throw(_("Invoice group source row is invalid."))
        row = by_id.get(item["source_row"])
        if (
            not row
            or item["source_doctype"] != source.doctype
            or item["source_name"] != source.name
            or item["sales_order"] != so.name
            or item["item_code"] != row.get("item_code")
            or item["sales_order_item"]
            != (row.name if source.doctype == "Sales Order" else _text(row.get("so_detail")))
            or str(item["authorized_qty"]) != str(_scalar(row.get("qty")))
            or not _ordinary(row, identities[_text(row.item_code)], stock=source.doctype == "Delivery Note")
        ):
            frappe.throw(_("Invoice group source row changed or is no longer eligible."))
        current.append(_source_row(source, cast(Document, row), _text(so.name)))
    if _source_rows(sorted(current, key=lambda row: row["source_row"])) != run.source_rows_json:
        frappe.throw(_("Invoice group source rows changed."))
    current_group = _group(
        source, so, _text(run.group_kind), [by_id[item["source_row"]] for item in selected]
    )
    if not current_group or current_group["source_digest"] != run.source_digest:
        frappe.throw(_("Invoice group source digest changed."))
    return source, so, selected


def _check_remaining(rows: list[dict[str, Any]], *, source_doctype: str) -> None:
    field = "so_detail" if source_doctype == "Sales Order" else "dn_detail"
    names = [row["source_row"] for row in rows]
    billed = frappe.get_all(
        "Sales Invoice Item",
        filters={field: ["in", names], "docstatus": 1},
        fields=[field, "qty"],
    )
    billed_rows = {_text(row.get(field)) for row in billed}
    for row in rows:
        if row["source_row"] in billed_rows:
            frappe.throw(_("Source row was already invoiced; review the generation run."))


def _nonzero_fixed_amount(value: Any) -> bool:
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        frappe.throw(_("Source fixed amount must be numeric."))
    if not amount.is_finite():
        frappe.throw(_("Source fixed amount must be finite."))
    return bool(amount)


def _reject_unallocated_fixed_amounts(source: Document, so: Document, rows: list[dict[str, Any]]) -> bool:
    """Only one invoice for the entire signed SO may inherit a fixed charge."""
    source_names = {str(row.name) for row in source.get("items") or []}
    selected_names = {str(row["source_row"]) for row in rows}
    source_partial = selected_names != source_names
    if source_partial and any(
        _nonzero_fixed_amount(source.get(field)) for field in ("loyalty_amount", "loyalty_points")
    ):
        frappe.throw(
            _("A loyalty amount on a partial source group needs an approved allocation."),
            exc=frappe.ValidationError,
        )
    if source_partial:
        for schedule in source.get("payment_schedule") or []:
            if not _nonzero_fixed_amount(schedule.get("invoice_portion")) and _nonzero_fixed_amount(
                schedule.get("payment_amount")
            ):
                frappe.throw(
                    _("A fixed payment schedule on a partial source group needs an approved allocation."),
                    exc=frappe.ValidationError,
                )
    actual_tax = any(
        tax.get("charge_type") == "Actual"
        and any(_nonzero_fixed_amount(tax.get(field)) for field in ("tax_amount", "base_tax_amount"))
        for tax in so.get("taxes") or []
    )
    fixed_discount = not _nonzero_fixed_amount(so.get("additional_discount_percentage")) and (
        _nonzero_fixed_amount(so.get("discount_amount"))
    )
    has_fixed = actual_tax or fixed_discount
    if not has_fixed:
        return False
    identities = _item_identities(list(so.get("items") or []))
    if any(
        _text(row.get("asset"))
        or row.get("is_fixed_asset")
        or identities[_text(row.get("item_code"))].get("is_fixed_asset")
        for row in so.get("items") or []
    ):
        frappe.throw(
            _("A fixed charge spanning Asset rows needs separate cross-route authority."),
            exc=_CrossRouteFixedPoolError,
        )
    approved = {str(row.name): Decimal(str(row.get("qty") or 0)) for row in so.get("items") or []}
    selected: dict[str, Decimal] = {}
    for row in rows:
        key = str(row["sales_order_item"])
        selected[key] = selected.get(key, Decimal(0)) + Decimal(str(row["authorized_qty"]))
    if selected != approved:
        frappe.throw(
            _("A fixed charge on a partial Sales Order needs an approved allocation before invoicing."),
            exc=_AllocationRequiredError,
        )
    return True


def _reject_unsupported_invoice_features(invoice: Document) -> None:
    """Only the finite ordinary billing shape may enter the automatic route."""
    for table in ("advances", "payments", "tax_withholding_entries", "timesheets"):
        if invoice.get(table):
            frappe.throw(_("This Sales Invoice accounting feature needs separate billing authority."))
    for field in (
        "is_pos",
        "update_stock",
        "paid_amount",
        "change_amount",
        "write_off_amount",
        "allocate_advances_automatically",
        "redeem_loyalty_points",
        "loyalty_amount",
        "loyalty_points",
        "is_cash_or_non_trade_discount",
    ):
        if _nonzero_fixed_amount(invoice.get(field)):
            frappe.throw(_("This Sales Invoice posting mode needs separate billing authority."))
    if invoice.get("additional_discount_account"):
        frappe.throw(_("This Sales Invoice discount account needs separate billing authority."))


def _trusted_delivery_invoice(target: Document, so: Document, selected: list[dict[str, Any]]) -> None:
    """Keep DN delivery references but derive every billing term from the signed SO."""
    so_rows = [row["sales_order_item"] for row in selected]
    if len(set(so_rows)) != len(so_rows):
        frappe.throw(_("One invoice cannot contain two delivery rows for the same Sales Order item."))
    trusted = from_sales_order(
        so.name,
        ignore_permissions=True,
        args={"filtered_children": so_rows},
    )
    approved = {row.name: row for row in so.get("items") or []}
    mapped = {_text(row.get("so_detail")): row for row in trusted.get("items") or []}
    actual = {_text(row.get("so_detail")): row for row in target.get("items") or []}
    if set(mapped) != set(so_rows) or set(actual) != set(so_rows):
        frappe.throw(_("Native invoice mapping did not preserve the approved Sales Order rows."))
    _reject_unsupported_invoice_features(trusted)
    _reject_unsupported_invoice_features(target)
    for field in INVOICE_HEADER_FIELDS:
        target.set(field, trusted.get(field))
    for field in SO_APPROVED_INVOICE_HEADER_FIELDS:
        target.set(field, so.get(field))
        trusted.set(field, so.get(field))
    target.set("debit_to", so.get("billing_receivable_account"))
    dimensions = billing_dimension_fields()
    for field in dimensions:
        target.set(field, so.get(field))
        trusted.set(field, so.get(field))
    for so_row_name, invoice_row in actual.items():
        baseline = mapped[so_row_name]
        approved_row = approved[so_row_name]
        delivered_qty = invoice_row.get("qty")
        dn_reference = {
            field: invoice_row.get(field) for field in ("delivery_note", "dn_detail", "warehouse")
        }
        for field in INVOICE_ITEM_FIELDS:
            if field not in {"delivery_note", "dn_detail", "qty", "stock_qty", "warehouse"}:
                invoice_row.set(field, baseline.get(field))
        for field in (*SO_APPROVED_INVOICE_ITEM_FIELDS, *dimensions):
            invoice_row.set(field, approved_row.get(field))
            baseline.set(field, approved_row.get(field))
        invoice_row.set("qty", delivered_qty)
        baseline.set("qty", delivered_qty)
        for field, value in dn_reference.items():
            invoice_row.set(field, value)
        stock_qty = Decimal(str(delivered_qty)) * Decimal(str(approved_row.get("conversion_factor") or 1))
        invoice_row.set("stock_qty", float(stock_qty))
        baseline.set("stock_qty", float(stock_qty))
    for table in ("taxes", "payment_schedule"):
        source_rows = so.get("taxes") or [] if table == "taxes" else trusted.get(table) or []
        values = [
            {
                field: value
                for field, value in row.as_dict().items()
                if field not in {"name", "parent", "parenttype", "parentfield", "idx", "doctype"}
            }
            for row in source_rows
        ]
        target.set(table, values)
        if table == "taxes":
            trusted.set(table, values)
    for doc in (trusted, target):
        doc.set("debit_to", so.get("billing_receivable_account"))
        doc.run_method("calculate_taxes_and_totals")
    ignored = {"delivery_note", "dn_detail", "warehouse"}
    expected = _invoice_payload(trusted)
    observed = _invoice_payload(target)
    expected["items"].sort(key=lambda row: _text(row.get("so_detail")))
    observed["items"].sort(key=lambda row: _text(row.get("so_detail")))
    for item in expected["items"]:
        for field in ignored:
            item.pop(field, None)
    for item in observed["items"]:
        for field in ignored:
            item.pop(field, None)
    if expected != observed:
        frappe.throw(
            _("Delivery Note billing values differ from the signed Sales Order projection."),
            exc=_SourceAuthorityMismatchError,
        )


def _restore_signed_service_accounts(target: Document, so: Document) -> None:
    """Native SO mapper can replace row cost centers with current Item defaults."""
    approved = {row.name: row for row in so.get("items") or []}
    dimensions = billing_dimension_fields()
    target.set("debit_to", so.get("billing_receivable_account"))
    for field in SO_APPROVED_INVOICE_HEADER_FIELDS:
        target.set(field, so.get(field))
    for row in target.get("items") or []:
        source = approved.get(_text(row.get("so_detail")))
        if not source:
            frappe.throw(_("Sales Invoice item no longer matches an approved Sales Order row."))
        source = cast(Document, source)
        for field in (*SO_APPROVED_INVOICE_ITEM_FIELDS, *dimensions):
            row.set(field, source.get(field))
    target.run_method("calculate_taxes_and_totals")


def _stamp(target: Document, run: SalesInvoiceGeneration, actor: str) -> str:
    digest = _digest(_invoice_payload(target))
    values = {
        "connect_invoice_generation_run": run.name,
        "connect_invoice_source_doctype": run.source_doctype,
        "connect_invoice_source_name": run.source_name,
        "connect_billing_authority_digest": run.billing_authority_digest,
        "connect_source_group_digest": run.source_digest,
        "connect_generated_by_actor": actor,
        "connect_generated_at": now_datetime(),
        "connect_generation_payload_digest": digest,
    }
    for name, value in values.items():
        target.set(name, value)
    return digest


@contextmanager
def _target_stage(target: Document, run: SalesInvoiceGeneration, stage: str, digest: str) -> Iterator[None]:
    if stage not in {"map", "insert", "submit"}:
        frappe.throw(_("Invalid invoice generation stage."))
    nonce = token_urlsafe(24)
    token = _STAGE.set((id(target), _text(run.name), stage, digest, False, run, nonce))
    prior = target.flags.get("ignore_permissions")
    prior_nonce = target.flags.get("_connect_generation_nonce")
    try:
        target.flags.ignore_permissions = True
        target.flags._connect_generation_nonce = nonce
        yield
    finally:
        target.flags.ignore_permissions = prior
        target.flags._connect_generation_nonce = prior_nonce
        _STAGE.reset(token)


def _require_stage(doc: Document, stage: str, *, consume: bool = False, allow_consumed: bool = False) -> None:
    proof = _STAGE.get()
    if (
        proof is None
        or proof[0] != id(doc)
        or proof[2] != stage
        or (proof[4] and not allow_consumed)
        or proof[1] != _text(doc.get("connect_invoice_generation_run"))
        or proof[3] != _digest(_invoice_payload(doc))
        or proof[3] != doc.get("connect_generation_payload_digest")
        or not compare_digest(proof[6], _text(doc.flags.get("_connect_generation_nonce")))
        or doc.get("connect_invoice_source_doctype") != proof[5].source_doctype
        or doc.get("connect_invoice_source_name") != proof[5].source_name
        or doc.get("connect_billing_authority_digest") != proof[5].billing_authority_digest
        or doc.get("connect_source_group_digest") != proof[5].source_digest
        or doc.get("connect_generated_by_actor") != frappe.session.user
        or not doc.get("connect_generated_at")
    ):
        raise frappe.PermissionError(_("Sales Invoice generation proof is missing or changed."))
    if consume:
        _STAGE.set((proof[0], proof[1], proof[2], proof[3], True, proof[5], proof[6]))


def _linked(doc: Document) -> bool:
    return any(
        row.get(field)
        for row in doc.get("items") or []
        for field in ("sales_order", "so_detail", "delivery_note", "dn_detail")
    )


def validate_sales_invoice_generation(doc: Document, method: str | None = None) -> None:
    del method
    if doc.doctype != "Sales Invoice":
        return
    prior = doc.get_doc_before_save() if not doc.is_new() else None
    if doc.get("is_return"):
        if doc.get("connect_invoice_generation_run") or (
            prior and prior.get("connect_invoice_generation_run")
        ):
            frappe.throw(_("A generated Sales Invoice cannot become a return."))
        return
    if prior and any(doc.get(field) != prior.get(field) for field in PROVENANCE_FIELDS):
        frappe.throw(_("Generated Sales Invoice provenance cannot change."))
    if doc.get("connect_invoice_generation_run"):
        proof = _STAGE.get()
        if proof is None or proof[0] != id(doc) or proof[1] != doc.get("connect_invoice_generation_run"):
            raise frappe.PermissionError(_("Generated Sales Invoice requires its active generation run."))
        if proof[4] and doc.flags.get("in_insert"):
            _require_stage(doc, "insert", allow_consumed=True)
            return
        _require_stage(doc, proof[2])
    elif _linked(doc):
        frappe.throw(_("Source-linked Sales Invoices require an approved generation run."))


def before_insert_sales_invoice_generation(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("is_return"):
        if doc.get("connect_invoice_generation_run"):
            frappe.throw(_("A generated Sales Invoice cannot be a return."))
        return
    if doc.get("connect_invoice_generation_run"):
        _require_stage(doc, "insert", consume=True)
    elif not doc.get("is_return") and _linked(doc):
        frappe.throw(_("Source-linked Sales Invoices require an approved generation run."))


def before_submit_sales_invoice_generation(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("is_return"):
        if doc.get("connect_invoice_generation_run"):
            frappe.throw(_("A generated Sales Invoice cannot be a return."))
        return
    if not doc.get("connect_invoice_generation_run"):
        if _linked(doc):
            frappe.throw(_("Source-linked Sales Invoices require an approved generation run."))
        return
    if doc.docstatus != 1 or doc._action != "submit":
        frappe.throw(_("Generated Sales Invoice requires native submit."))
    persisted = frappe.db.get_value("Sales Invoice", doc.name, "docstatus", for_update=True)
    if persisted != 0:
        frappe.throw(_("Generated Sales Invoice must be a persisted Draft before submit."))
    _require_stage(doc, "submit", consume=True)


def on_submit_sales_invoice_generation(doc: Document, method: str | None = None) -> None:
    del method
    if not doc.get("connect_invoice_generation_run") or doc.get("is_return"):
        return
    proof = _STAGE.get()
    if proof is None or proof[0] != id(doc) or proof[2] != "submit" or not proof[4]:
        frappe.throw(_("Generated Sales Invoice submit proof was not consumed."))
    _require_stage(doc, "submit", allow_consumed=True)
    if frappe.db.get_value("Sales Invoice", doc.name, "docstatus") != 1:
        frappe.throw(_("Generated Sales Invoice was not submitted."))


def on_cancel_sales_invoice_generation(doc: Document, method: str | None = None) -> None:
    del method
    run_name = _text(doc.get("connect_invoice_generation_run"))
    if not run_name or doc.get("is_return"):
        return
    run = _lock_run(run_name)
    if run.target_sales_invoice != doc.name or run.generation_status != "Generated":
        frappe.throw(_("Generated Sales Invoice cancellation does not match its run."))
    run.set("generation_status", "Generated SI Cancelled")
    with _system_write(run, "update"):
        run.save()


def _mark(
    run: SalesInvoiceGeneration,
    status: str,
    *,
    target: str | None = None,
    digest: str | None = None,
    error: str | None = None,
    failure_code: str | None = None,
) -> None:
    run.set("generation_status", status)
    run.set("attempt_count", int(run.get("attempt_count") or 0) + 1)
    run.set("last_error", error)
    run.set("failure_code", failure_code)
    if target:
        run.set("target_sales_invoice", target)
        run.set("generated_at", now_datetime())
    if digest:
        run.set("expected_invoice_payload_digest", digest)
    with _system_write(run, "update"):
        run.save()


def _generate(run: SalesInvoiceGeneration) -> str:
    source, _so, selected = _verify_group(run)
    actor = frappe.session.user
    if actor in {"Administrator", "Guest"}:
        frappe.throw(_("Invoice generation requires a real authorized actor."), frappe.PermissionError)
    if not frappe.has_permission(source.doctype, ptype="read", doc=source, user=actor):
        raise frappe.PermissionError(_("You cannot read the Sales Invoice source."))
    full_fixed = _reject_unallocated_fixed_amounts(source, _so, selected)
    if full_fixed:
        competing = frappe.db.sql(
            "SELECT name FROM `tabSales Invoice Generation` WHERE sales_order=%s AND name!=%s "
            "AND generation_status NOT IN ('Generated SI Cancelled') FOR UPDATE NOWAIT",
            (_so.name, run.name),
            as_dict=True,
        )
        if competing:
            frappe.throw(_("A fixed charge already has another Sales Order invoice claim."))
        billed = frappe.db.sql(
            "SELECT name FROM `tabSales Invoice Item` WHERE sales_order=%s AND docstatus=1 FOR UPDATE NOWAIT",
            (_so.name,),
            as_dict=True,
        )
        if billed:
            frappe.throw(_("A fixed charge already has a submitted Sales Order invoice."))
    _check_remaining(selected, source_doctype=source.doctype)
    target = frappe.new_doc("Sales Invoice")
    # The object alone receives this capability. Native mapper still checks the source read ACL.
    with _target_stage(target, run, "map", ""):
        args = {"filtered_children": [row["source_row"] for row in selected]}
        if source.doctype == "Sales Order":
            mapped = from_sales_order(source.name, target_doc=target, ignore_permissions=False, args=args)
        else:
            mapped = from_delivery_note(source.name, target_doc=target, args=args)
        if mapped is not target:
            frappe.throw(_("Native Sales Invoice mapper replaced the authorized target."))
    mapped_ids = [
        _text(row.get("so_detail") if source.doctype == "Sales Order" else row.get("dn_detail"))
        for row in target.get("items") or []
    ]
    if sorted(mapped_ids) != sorted(row["source_row"] for row in selected):
        frappe.throw(_("Native Sales Invoice mapper changed the approved source group."))
    if any(
        Decimal(str(row.get("qty") or 0))
        != Decimal(str(next(item["authorized_qty"] for item in selected if item["source_row"] == mapped_id)))
        for row, mapped_id in zip(target.get("items") or [], mapped_ids, strict=True)
    ):
        frappe.throw(_("Native Sales Invoice mapper changed approved quantities."))
    if source.doctype == "Delivery Note":
        _trusted_delivery_invoice(target, _so, selected)
    else:
        _restore_signed_service_accounts(target, _so)
    payload = _stamp(target, run, actor)
    with _target_stage(target, run, "insert", payload):
        target.insert()
    # Re-run native credit/accounting checks at posting; a mapper result is never approval.
    with _target_stage(target, run, "submit", payload):
        target.submit()
    _mark(run, "Generated", target=target.name, digest=payload)
    return _text(target.name)


def process_sales_invoice_generation(run_name: str) -> str | None:
    """Queue target; a failed native posting rolls back fully before visible retry state."""
    if not _text(run_name):
        frappe.throw(_("Sales Invoice Generation name is required."))
    run = _lock_authority_then_run(run_name)
    if run.generation_status in {"Generated", "Generated SI Cancelled"}:
        return run.target_sales_invoice
    if run.target_sales_invoice:
        frappe.throw(_("An existing generated Sales Invoice cannot be replaced."))
    try:
        return _generate(run)
    except Exception as exc:
        # Native insert, submit and all ledger writes are discarded together.
        frappe.db.rollback()
        run = _lock_authority_then_run(run_name)
        if run.generation_status in {"Generated", "Generated SI Cancelled"}:
            return run.target_sales_invoice
        status = "Pending Permission" if isinstance(exc, frappe.PermissionError) else "Failed"
        failure_code = None
        if isinstance(exc, _AllocationRequiredError):
            failure_code = "Allocation Required"
            error = ALLOCATION_REQUIRED_STATUS
        elif isinstance(exc, _CrossRouteFixedPoolError):
            failure_code = "Cross-route Fixed Pool Unsupported"
            error = "A fixed charge spans ordinary and Asset invoice rows."
        elif isinstance(exc, _SourceAuthorityMismatchError):
            failure_code = "Source Authority Mismatch"
            error = "The delivery billing values cannot be proved from approved Sales Order terms."
        elif isinstance(exc, _LegacyAuthorityError):
            status = "Legacy Authority Hold"
            failure_code = "Legacy Authority Hold"
            error = "A new Finance approval is required before billing this Sales Order."
        else:
            error = type(exc).__name__
        _mark(run, status, error=error, failure_code=failure_code)
        return None
