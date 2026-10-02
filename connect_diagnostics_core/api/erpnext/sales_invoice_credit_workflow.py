# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guards and evidence capture for Sales Invoice credit-note approval."""

from __future__ import annotations

from typing import Any, cast

import erpnext
import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from frappe import _
from frappe.model.document import Document
from frappe.model.meta import get_field_precision
from frappe.utils import flt

from connect_diagnostics_core.api.frappe.approval_controls import (
    authorize_approval_field_write,
    authorize_workflow_field_write,
    consume_approval_field_grant,
    critical_digest,
    require_distinct_actors,
    require_locked_submitted_update,
    require_native_terminal_state,
    require_permission,
    resolve_user,
)
from connect_diagnostics_core.api.frappe.approval_routes import get_route

ROUTE = "sales_invoice_credit_note"
DIGEST_VERSION = "sales-invoice-credit-note-v2"
APPROVED_STATE = get_route(ROUTE).approved_state
SUBMITTED_STATE = get_route(ROUTE).submitted_state
APPROVAL_FIELDS = frozenset(
    {
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)
_DIGEST_EXCLUDED_FIELDS = frozenset(
    {
        "name",
        "doctype",
        "docstatus",
        "workflow_state",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "idx",
        *APPROVAL_FIELDS,
    }
)


def is_credit_note(doc: Document) -> bool:
    """Identify the protected route without trusting source validity as a bypass."""
    if doc.get("doctype") != "Sales Invoice":
        return False
    identity = doc
    if not doc.is_new():
        identity = (
            frappe.db.get_value(
                "Sales Invoice",
                doc.name,
                ["is_return", "return_against"],
                as_dict=True,
            )
            or {}
        )
    return bool(identity.get("is_return") and str(identity.get("return_against") or "").strip())


def _payload(
    doc: Document,
    source: frappe._dict | None = None,
    source_items: list[frappe._dict] | None = None,
    masters: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fields = (
        "is_return",
        "return_against",
        "company",
        "customer",
        "currency",
        "posting_date",
        "set_posting_time",
        "posting_time",
        "due_date",
        "credit_note_reason",
        "conversion_rate",
        "selling_price_list",
        "update_stock",
        "is_pos",
        "debit_to",
        "party_account_currency",
        "against_income_account",
        "is_opening",
        "cost_center",
        "project",
        "update_outstanding_for_self",
        "is_internal_customer",
        "is_internal_transfer",
        "allocate_advances_automatically",
        "payment_terms_template",
        "cash_bank_account",
        "change_amount",
        "account_for_change_amount",
        "write_off_amount",
        "write_off_outstanding_amount_automatically",
        "write_off_account",
        "write_off_cost_center",
        "redeem_loyalty_points",
        "loyalty_points",
        "loyalty_amount",
        "coupon_code",
        "apply_discount_on",
        "discount_amount",
        "additional_discount_percentage",
        "grand_total",
        "total_taxes_and_charges",
        "net_total",
        "rounded_total",
        "base_grand_total",
        "base_net_total",
        "base_total_taxes_and_charges",
        "rounding_adjustment",
        "base_rounding_adjustment",
        "disable_rounded_total",
        "additional_discount_account",
        "cash_discount",
        "apply_discount_on_rate",
        "write_off_cost_center",
        "loyalty_redemption_account",
        "loyalty_redemption_cost_center",
        "unrealized_profit_loss_account",
        "change_amount",
        "account_for_change_amount",
        "cash_bank_account",
        "allocate_advances_automatically",
        "is_pos",
        "pos_profile",
        "paid_amount",
        "base_paid_amount",
        "base_change_amount",
        "write_off_amount",
        "write_off_account",
        "write_off_outstanding_amount_automatically",
    )
    payload: dict[str, Any] = {
        "digest_version": DIGEST_VERSION,
        **{field: doc.get(field) for field in fields},
    }
    payload["native_document"] = _native_document_projection(doc)
    for field in ("posting_date", "due_date"):
        if payload[field] is not None:
            payload[field] = str(payload[field])
    if not payload["set_posting_time"]:
        payload["posting_time"] = None
    elif payload["posting_time"] is not None:
        payload["posting_time"] = str(payload["posting_time"])
    dimensions = sorted(str(value) for value in get_accounting_dimensions() or [])
    payload["dimensions"] = {field: doc.get(field) for field in dimensions}
    item_fields = (
        "item_code",
        "sales_invoice_item",
        "qty",
        "stock_qty",
        "uom",
        "stock_uom",
        "conversion_factor",
        "rate",
        "base_rate",
        "amount",
        "net_amount",
        "base_amount",
        "base_net_amount",
        "discount_percentage",
        "discount_amount",
        "discount_account",
        "expense_account",
        "warehouse",
        "rejected_warehouse",
        "income_account",
        "cost_center",
        "project",
        "serial_no",
        "batch_no",
        "use_serial_batch_fields",
        "serial_and_batch_bundle",
        "rejected_serial_and_batch_bundle",
        "is_fixed_asset",
        "asset",
        "finance_book",
        "item_tax_template",
        "item_tax_rate",
        "posting_date",
        "service_start_date",
        "service_end_date",
        "dn_detail",
        "so_detail",
    )
    payload["items"] = [
        {**{key: row.get(key) for key in item_fields}, **{field: row.get(field) for field in dimensions}}
        for row in doc.get("items", [])
    ]
    tax_fields = (
        "charge_type",
        "row_id",
        "account_head",
        "cost_center",
        "description",
        "idx",
        "included_in_print_rate",
        "included_in_paid_amount",
        "rate",
        "tax_amount",
        "total",
    )
    payload["taxes"] = [
        {**{key: row.get(key) for key in tax_fields}, **{field: row.get(field) for field in dimensions}}
        for row in doc.get("taxes", [])
    ]
    child_fields = {
        "advances": (
            "reference_type",
            "reference_name",
            "reference_row",
            "advance_amount",
            "allocated_amount",
            "exchange_gain_loss",
            "ref_exchange_rate",
            "difference_posting_date",
        ),
        "payment_schedule": (
            "payment_term",
            "due_date",
            "invoice_portion",
            "payment_amount",
            "mode_of_payment",
            "discount_date",
            "discount_type",
            "discount",
        ),
        "payments": (
            "mode_of_payment",
            "amount",
            "account",
            "type",
            "reference_no",
        ),
        "withholding_tax": (
            "account_head",
            "taxable_value",
            "rate",
            "amount",
            "base_amount",
            "cost_center",
        ),
    }
    for table, table_fields in child_fields.items():
        payload[table] = [{field: row.get(field) for field in table_fields} for row in (doc.get(table) or [])]
    original = str(doc.get("return_against") or "")
    payload["original"] = (
        dict(source)
        if source is not None
        else dict(
            frappe.db.get_value(
                "Sales Invoice",
                original,
                [
                    "name",
                    "docstatus",
                    "company",
                    "customer",
                    "currency",
                    "conversion_rate",
                    "debit_to",
                    "party_account_currency",
                    "posting_date",
                    "posting_time",
                    "set_posting_time",
                    "is_opening",
                    "cost_center",
                    "project",
                    "update_stock",
                    "is_pos",
                    "grand_total",
                    "base_grand_total",
                    "net_total",
                    "total_taxes_and_charges",
                    "rounded_total",
                    "additional_discount_account",
                    "loyalty_redemption_account",
                    "unrealized_profit_loss_account",
                    "write_off_account",
                    "write_off_cost_center",
                ],
                as_dict=True,
            )
            or {}
        )
        if original
        else {}
    )
    if source_items is not None:
        payload["original_items"] = [dict(row) for row in source_items]
    if masters is not None:
        payload["posting_masters"] = masters
    return payload


def _native_document_projection(
    doc: Document | frappe._dict, persisted_children: dict[str, list[frappe._dict]] | None = None
) -> dict[str, Any]:
    """Bind native Sales Invoice values except lifecycle/evidence metadata."""
    meta = doc.meta if isinstance(doc, Document) else frappe.get_meta("Sales Invoice")

    def value_for(fieldname: str, values: Any, fields: list[Any]) -> Any:
        value = values.get(fieldname)
        if value == "":
            return None
        field = next((candidate for candidate in fields if candidate.fieldname == fieldname), None)
        if field and field.fieldtype in {"Date", "Datetime"} and value is not None:
            return str(value)
        return value

    parent_fields = [
        field.fieldname
        for field in meta.fields
        if field.fieldname
        and field.fieldtype not in {"Table", "Table MultiSelect"}
        and field.fieldname not in _DIGEST_EXCLUDED_FIELDS
    ]
    projection: dict[str, Any] = {field: value_for(field, doc, meta.fields) for field in parent_fields}
    if not doc.get("set_posting_time"):
        projection["posting_time"] = None
    children: dict[str, list[dict[str, Any]]] = {}
    for field in meta.get_table_fields():
        rows = (
            persisted_children.get(field.fieldname, [])
            if persisted_children is not None
            else doc.get(field.fieldname) or []
        )
        if not rows:
            continue
        child_meta = frappe.get_meta(field.options)
        row_fields = [
            child_field.fieldname
            for child_field in child_meta.fields
            if child_field.fieldname
            and child_field.fieldname not in _DIGEST_EXCLUDED_FIELDS - {"name", "idx"}
            and child_field.fieldname not in {"parent", "parenttype", "parentfield"}
        ]
        children[field.fieldname] = [
            {name: value_for(name, row, child_meta.fields) for name in row_fields} for row in rows
        ]
    projection["children"] = children
    return projection


def critical_payload(
    doc: Document,
    source: frappe._dict | None = None,
    source_items: list[frappe._dict] | None = None,
    masters: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _payload(doc, source, source_items, masters)


def critical_payload_digest(
    doc: Document,
    source: frappe._dict | None = None,
    source_items: list[frappe._dict] | None = None,
    masters: dict[str, dict[str, Any]] | None = None,
) -> str:
    return critical_digest(_payload(doc, source, source_items, masters))


def _lock_and_read_return_rows(
    doc: Document,
) -> tuple[
    frappe._dict,
    list[frappe._dict],
    list[frappe._dict],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    """Lock source, target, source children, then physical submitted return rows NOWAIT."""
    source_name = str(doc.get("return_against") or "").strip()
    if not source_name:
        frappe.throw(_("Credit Note must reference a submitted Sales Invoice."))
    try:
        source_rows = frappe.db.sql(
            "SELECT * FROM `tabSales Invoice` WHERE name=%s FOR UPDATE NOWAIT",
            (source_name,),
            as_dict=True,
        )
        target_rows = []
        target_children: dict[str, list[frappe._dict]] = {}
        if doc.name and not doc.is_new():
            target_rows = frappe.db.sql(
                "SELECT * FROM `tabSales Invoice` WHERE name=%s FOR UPDATE NOWAIT",
                (doc.name,),
                as_dict=True,
            )
            for table_field in doc.meta.get_table_fields():
                target_children[table_field.fieldname] = frappe.db.sql(
                    f"SELECT * FROM `tab{table_field.options}` WHERE parent=%s "
                    "AND parenttype=%s AND parentfield=%s ORDER BY idx, name FOR UPDATE NOWAIT",
                    (doc.name, "Sales Invoice", table_field.fieldname),
                    as_dict=True,
                )
        source_items = frappe.db.sql(
            "SELECT * FROM `tabSales Invoice Item` WHERE parent=%s ORDER BY name FOR UPDATE NOWAIT",
            (source_name,),
            as_dict=True,
        )
        # A locking read, rather than an aggregate snapshot, is essential here. MariaDB
        # locking reads are current reads under REPEATABLE READ, including after waiting
        # for the source invoice mutex held by an earlier return transaction.
        returns = frappe.db.sql(
            "SELECT parent.name AS parent, child.* "
            "FROM `tabSales Invoice` parent JOIN `tabSales Invoice Item` child "
            "ON child.parent=parent.name WHERE parent.return_against=%s AND parent.is_return=1 "
            "AND parent.docstatus=1 ORDER BY parent.name, child.name FOR UPDATE NOWAIT",
            (source_name,),
            as_dict=True,
        )
        bundle_ids = sorted(
            {
                str(row.get(field))
                for row in [*source_items, *returns, *(doc.get("items") or [])]
                for field in ("serial_and_batch_bundle",)
                if row.get(field)
            }
        )
        bundle_rows: list[frappe._dict] = []
        bundle_entries: list[frappe._dict] = []
        for bundle_id in bundle_ids:
            bundle_rows.extend(
                frappe.db.sql(
                    "SELECT * FROM `tabSerial and Batch Bundle` WHERE name=%s FOR UPDATE NOWAIT",
                    (bundle_id,),
                    as_dict=True,
                )
            )
            bundle_entries.extend(
                frappe.db.sql(
                    "SELECT * FROM `tabSerial and Batch Entry` WHERE parent=%s ORDER BY name FOR UPDATE NOWAIT",
                    (bundle_id,),
                    as_dict=True,
                )
            )
        source_ledger_facts: dict[str, dict[str, Any]] = {}
        for doctype in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
            ledger_rows = frappe.db.get_values(
                doctype,
                {"voucher_type": "Sales Invoice", "voucher_no": source_name},
                "*",
                as_dict=True,
                for_update=True,
                wait=False,
                order_by="name",
            )
            source_ledger_facts.update({f"{doctype}:{row.name}": dict(row) for row in ledger_rows})
        master_fields = {
            "Account": (
                "debit_to",
                "against_income_account",
                "write_off_account",
                "cash_bank_account",
                "account_for_change_amount",
                "additional_discount_account",
                "loyalty_redemption_account",
                "unrealized_profit_loss_account",
                "income_account",
                "expense_account",
                "discount_account",
                "account_head",
            ),
            "Company": ("company",),
            "Customer": ("customer",),
            "Item": ("item_code",),
            "Warehouse": ("warehouse", "rejected_warehouse"),
            "Cost Center": ("cost_center",),
            "Project": ("project",),
            "Asset": ("asset",),
            "Finance Book": ("finance_book",),
            "Item Tax Template": ("item_tax_template",),
            "Sales Taxes and Charges Template": ("taxes_and_charges",),
            "Price List": ("selling_price_list",),
            "Batch": ("batch_no",),
        }
        target_item_rows = [
            row
            for table_field in doc.meta.get_table_fields()
            for row in (doc.get(table_field.fieldname) or [])
        ]
        docs: list[Document | frappe._dict] = [
            doc,
            source_rows[0],
            *target_item_rows,
            *source_items,
            *returns,
            *bundle_rows,
            *bundle_entries,
        ]
        link_values: dict[str, set[str]] = {}
        for doctype, fields in master_fields.items():
            for value in {str(record.get(field) or "").strip() for record in docs for field in fields}:
                if value:
                    link_values.setdefault(doctype, set()).add(value)
        masters: dict[str, dict[str, Any]] = {}
        masters.update(source_ledger_facts)
        masters.update({f"Serial and Batch Bundle:{row.name}": dict(row) for row in bundle_rows})
        masters.update({f"Serial and Batch Entry:{row.name}": dict(row) for row in bundle_entries})
        dimension_rows = frappe.db.sql(
            "SELECT * FROM `tabAccounting Dimension` ORDER BY name FOR UPDATE NOWAIT",
            as_dict=True,
        )
        masters.update({f"Accounting Dimension:{row.name}": dict(row) for row in dimension_rows})
        serial_names = {
            serial for record in docs for serial in get_serial_nos(str(record.get("serial_no") or ""))
        }
        link_values.setdefault("Serial No", set()).update(serial_names)
        for doctype, names in sorted(link_values.items()):
            for name in sorted(names):
                master = frappe.db.get_value(doctype, name, "*", as_dict=True, for_update=True, wait=False)
                if master:
                    masters[f"{doctype}:{name}"] = dict(master)
        target_projection = (
            _native_document_projection(frappe._dict(target_rows[0]), target_children) if target_rows else {}
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw(_("Credit Note source is being updated by another transaction. Please retry."))
    if not source_rows or int(source_rows[0].docstatus or 0) != 1:
        frappe.throw(_("Credit Note reference must be a submitted Sales Invoice."))
    return source_rows[0], source_items, returns, masters, target_projection


def _require_target_projection_matches(doc: Document, persisted: dict[str, Any]) -> None:
    if not persisted or _native_document_projection(doc) != persisted:
        frappe.throw(_("Credit Note changed after it was loaded; reload it and resubmit for review."))


def _validate_cumulative_return_quantity(
    doc: Document, source_items: list[frappe._dict], returns: list[frappe._dict]
) -> None:
    """Supplement native return validation with a source-serialized current quantity read."""
    measure = "stock_qty" if doc.get("update_stock") else "qty"
    precision = get_field_precision(
        frappe.get_meta("Sales Invoice Item").get_field(measure),
        currency=erpnext.get_company_currency(str(doc.get("company") or "")),
    )
    source_by_name: dict[str, frappe._dict] = {str(row.name): row for row in source_items}
    returned_raw: dict[str, float] = {}
    for row in returns:
        source_row = str(row.sales_invoice_item or "")
        if source_row not in source_by_name or str(source_by_name[source_row].get("item_code") or "") != str(
            row.get("item_code") or ""
        ):
            frappe.throw(_("A prior Credit Note has invalid source item links; contact an administrator."))
        returned_raw[source_row] = returned_raw.get(source_row, 0.0) + abs(float(row.get(measure) or 0))
    for row in doc.get("items", []):
        source_row_name = str(row.get("sales_invoice_item") or "")
        source_row = cast(frappe._dict, source_by_name.get(source_row_name))
        if source_row is None or str(source_row.get("item_code") or "") != str(row.get("item_code") or ""):
            frappe.throw(_("Credit Note item must link to the exact original Sales Invoice item."))
        reference = flt(source_row.get(measure) or 0, precision)
        candidate = flt(row.get(measure) or 0, precision)
        if measure == "qty":
            reference = flt(
                flt(reference * flt(source_row.get("conversion_factor") or 1, precision), precision),
                precision,
            )
            candidate = flt(candidate * flt(row.get("conversion_factor") or 1, precision), precision)
        already_returned = flt(returned_raw.get(source_row_name, 0.0), precision)
        max_returnable = flt(reference - already_returned, precision)
        if candidate >= 0 or abs(flt(candidate, precision)) > max_returnable:
            frappe.throw(
                _("Credit Note exceeds the current returnable quantity for Item {0}.").format(row.item_code)
            )
        returned_raw[source_row_name] = returned_raw.get(source_row_name, 0.0) + abs(
            float(row.get(measure) or 0)
        )


def _require_supported_return_posting_path(doc: Document) -> None:
    """Fail closed for native Sales Invoice posting paths whose references are not sealed here."""
    unsupported = bool(
        doc.get("is_pos")
        or doc.get("is_internal_customer")
        or doc.get("is_internal_transfer")
        or doc.get("allocate_advances_automatically")
        or doc.get("advances")
        or doc.get("payments")
        or doc.get("redeem_loyalty_points")
        or doc.get("loyalty_points")
        or doc.get("loyalty_amount")
        or doc.get("cash_bank_account")
        or doc.get("change_amount")
        or doc.get("account_for_change_amount")
        or doc.get("tax_withholding_category")
        or doc.get("apply_tds")
        or any(
            row.get("is_fixed_asset")
            or row.get("asset")
            or row.get("serial_no")
            or row.get("batch_no")
            or row.get("serial_and_batch_bundle")
            or row.get("use_serial_batch_fields")
            for row in (doc.get("items") or [])
        )
    )
    if unsupported:
        frappe.throw(
            _(
                "This Credit Note uses a POS, advance, loyalty, withholding, internal-transfer, fixed-asset, or serial/batch posting path that requires separate approval controls."
            )
        )


def _capture(
    doc: Document,
    action: str,
    *,
    protected: bool,
    roles: tuple[str, ...],
    maker: str = "",
    previous: tuple[str, ...] = (),
    source_projection: tuple[frappe._dict, list[frappe._dict], dict[str, dict[str, Any]]] | None = None,
) -> None:
    route = get_route(ROUTE)
    if protected:
        snapshot = authorize_approval_field_write(doc, ROUTE, action, roles, maker, previous)
        field = "approval_reviewer_user" if action == route.review_action else "approval_authorized_user"
        doc.set(field, snapshot.user)
        prefix = "checked" if action == route.review_action else "authorized"
        doc.set(f"{prefix}_by", snapshot.employee)
        doc.set(f"{prefix}_at", snapshot.acted_at)
        doc.set(f"{prefix}_signature", snapshot.signature)
    else:
        user = authorize_workflow_field_write(doc, ROUTE, action, roles)
        if action == route.send_action:
            doc.set("approval_maker_user", user)
    if action != route.approve_action:
        source, source_items, masters = source_projection or (None, None, None)
        doc.set("approval_critical_digest", critical_payload_digest(doc, source, source_items, masters))


def capture_maker(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        _capture(
            doc,
            route.resubmit_action if doc.get("approval_maker_user") else route.send_action,
            protected=False,
            roles=route.maker_roles,
        )


def capture_review(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        _require_supported_return_posting_path(doc)
        source, source_items, returns, masters, target_projection = _lock_and_read_return_rows(doc)
        _require_target_projection_matches(doc, target_projection)
        _validate_cumulative_return_quantity(doc, source_items, returns)
        _capture(
            doc,
            route.review_action,
            protected=True,
            roles=route.reviewer_roles,
            maker=str(doc.get("approval_maker_user") or ""),
            source_projection=(source, source_items, masters),
        )


def capture_approval(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        _require_supported_return_posting_path(doc)
        source, source_items, returns, masters, target_projection = _lock_and_read_return_rows(doc)
        _require_target_projection_matches(doc, target_projection)
        _validate_cumulative_return_quantity(doc, source_items, returns)
        if not str(doc.get("approval_critical_digest") or "").strip() or str(
            doc.get("approval_critical_digest")
        ) != critical_payload_digest(doc, source, source_items, masters):
            frappe.throw(_("Credit Note changed after review; resubmit it for review."))
        previous = (str(doc.get("approval_reviewer_user") or ""),)
        _capture(
            doc,
            route.approve_action,
            protected=True,
            roles=route.final_approver_roles,
            maker=str(doc.get("approval_maker_user") or ""),
            previous=previous,
            source_projection=(source, source_items, masters),
        )


def clear_on_return(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(doc, ROUTE, route.return_action, route.reviewer_roles)
        for field in APPROVAL_FIELDS - {"approval_maker_user"}:
            doc.set(field, None)


def clear_on_reject(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(doc, ROUTE, route.reject_action, route.final_approver_roles)
        for field in APPROVAL_FIELDS - {"approval_maker_user"}:
            doc.set(field, None)


def validate_approval_fields(doc: Document, method: str | None = None) -> None:
    del method
    if (
        doc.get("doctype") == "Sales Invoice"
        and doc.get("is_return")
        and not str(doc.get("return_against") or "").strip()
    ):
        frappe.throw(_("Credit Note must reference a submitted Sales Invoice."))
    if doc.get("doctype") == "Sales Invoice" and not doc.is_new():
        before = doc.get_doc_before_save()
        if (
            before
            and (
                before.get("is_return")
                or doc.get("is_return")
                or before.get("return_against")
                or doc.get("return_against")
            )
            and (
                bool(before.get("is_return")) != bool(doc.get("is_return"))
                or str(before.get("return_against") or "") != str(doc.get("return_against") or "")
            )
        ):
            frappe.throw(_("Credit Note route identity cannot be changed after creation."))
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    _require_supported_return_posting_path(doc)
    if doc.is_new():
        if doc.get("amended_from"):
            doc.set("workflow_state", route.draft_state)
            for field in APPROVAL_FIELDS:
                doc.set(field, None)
        elif any(doc.get(field) for field in APPROVAL_FIELDS):
            frappe.throw(_("New Credit Notes cannot contain pre-existing approval evidence."))
        require_native_terminal_state(doc, route.submitted_state, route.cancelled_state or "")
        return
    require_native_terminal_state(doc, route.submitted_state, route.cancelled_state or "")
    previous = doc.get_doc_before_save()
    if previous:
        before, after = previous.get("workflow_state"), doc.get("workflow_state")
        action = next(
            (
                a
                for a, old, new in (
                    (route.send_action, route.draft_state, route.pending_review_state),
                    (route.resubmit_action, route.returned_state, route.pending_review_state),
                    (route.review_action, route.pending_review_state, route.reviewed_state),
                    (route.approve_action, route.reviewed_state, route.approved_state),
                    (route.return_action, route.pending_review_state, route.returned_state),
                    (route.return_action, route.approved_state, route.returned_state),
                    (route.reject_action, route.reviewed_state, route.returned_state),
                    (route.execute_action, route.approved_state, route.submitted_state),
                )
                if before == old and after == new
            ),
            None,
        )
        if action:
            changed = {field for field in APPROVAL_FIELDS if doc.get(field) != previous.get(field)}
            allowed = {
                route.send_action: {"approval_maker_user", "approval_critical_digest"},
                route.resubmit_action: {"approval_critical_digest"},
                route.review_action: {
                    "approval_reviewer_user",
                    "approval_critical_digest",
                    "checked_by",
                    "checked_at",
                    "checked_signature",
                },
                route.approve_action: {
                    "approval_authorized_user",
                    "authorized_by",
                    "authorized_at",
                    "authorized_signature",
                },
                route.return_action: APPROVAL_FIELDS - {"approval_maker_user"},
                route.reject_action: APPROVAL_FIELDS - {"approval_maker_user"},
                route.execute_action: set(),
            }[action]
            if not changed.issubset(allowed):
                frappe.throw(_("Approval evidence changed outside the native Workflow action."))
            if action != route.execute_action:
                consume_approval_field_grant(doc, ROUTE, action)
        elif any(doc.get(field) != previous.get(field) for field in APPROVAL_FIELDS):
            frappe.throw(_("Approval evidence may only be changed by a native Workflow action."))


def validate_after_submit_update(doc: Document, method: str | None = None) -> None:
    """Keep submitted approval facts immutable before native ERPNext repost effects."""
    del method
    if is_credit_note(doc):
        require_locked_submitted_update(doc, get_route(ROUTE).submitted_state)
        if SalesInvoice.check_if_fields_updated(
            cast(SalesInvoice, doc),
            [
                "additional_discount_account",
                "cash_bank_account",
                "account_for_change_amount",
                "write_off_account",
                "loyalty_redemption_account",
                "unrealized_profit_loss_account",
                "is_opening",
            ],
            {
                "items": ("income_account", "expense_account", "discount_account"),
                "taxes": ("account_head",),
            },
        ):
            frappe.throw(_("Submitted Credit Note accounting facts cannot be changed."))
        previous = doc.get_doc_before_save()
        if not previous:
            frappe.throw(_("Submitted Credit Note history cannot be verified."))
        if any(doc.get(field) != previous.get(field) for field in APPROVAL_FIELDS):
            frappe.throw(_("Submitted Credit Note approval evidence cannot be changed."))
        if critical_payload_digest(doc) != critical_payload_digest(previous):
            frappe.throw(_("Submitted Credit Note accounting facts cannot be changed."))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    if doc.get("workflow_state") != SUBMITTED_STATE:
        frappe.throw(_("Credit Notes must be approved through the Sales Invoice Credit Workflow."))
    source_name = str(doc.get("return_against") or "").strip()
    if not source_name:
        frappe.throw(_("Credit Note must reference a submitted Sales Invoice."))
    source, source_items, returns, masters, target_projection = _lock_and_read_return_rows(doc)
    _require_target_projection_matches(doc, target_projection)
    persisted = frappe.db.get_value(
        "Sales Invoice",
        doc.name,
        [
            "workflow_state",
            "approval_critical_digest",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "checked_by",
            "checked_at",
            "checked_signature",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        ],
        as_dict=True,
        for_update=True,
    )
    # Native ERPNext validation remains authoritative for quantities, taxes, and
    # stock. Run it under both locks before comparing approval-critical values
    # because validation may normalize them.
    doc.validate()  # ty: ignore[unresolved-attribute] - ERPNext Sales Invoice controller method
    _validate_cumulative_return_quantity(doc, source_items, returns)
    if not persisted or persisted.workflow_state != APPROVED_STATE:
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    if (
        not source
        or source.docstatus != 1
        or source.company != doc.get("company")
        or source.customer != doc.get("customer")
        or source.currency != doc.get("currency")
    ):
        frappe.throw(
            _("Credit Note reference must be a submitted Sales Invoice for the same customer and company.")
        )
    for field in (
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        if not str(doc.get(field) or "").strip() or str(persisted.get(field) or "") != str(
            doc.get(field) or ""
        ):
            frappe.throw(_("Credit Note approval evidence is incomplete or stale."))
    if str(persisted.approval_critical_digest or "") != str(doc.get("approval_critical_digest") or ""):
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    if str(doc.get("approval_critical_digest") or "") != critical_payload_digest(
        doc, source, source_items, masters
    ):
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    maker = resolve_user(str(doc.get("approval_maker_user") or ""))
    reviewer = resolve_user(str(doc.get("approval_reviewer_user") or ""))
    approver = resolve_user(str(doc.get("approval_authorized_user") or ""))
    require_distinct_actors(maker, reviewer, (approver,))
    current_user = resolve_user(str(frappe.session.user or ""))
    if not set(frappe.get_roles(current_user)).intersection(route.execution_roles):
        frappe.throw(_("Only an authorized Accounts Manager may post this Credit Note."))
    require_permission(doc, "submit")
    consume_approval_field_grant(doc, ROUTE, route.execute_action)


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(
            doc, ROUTE, route.execute_action, route.execution_roles, permission="submit"
        )


def authorize_cancel_transition(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        if not route.cancel_action or not route.cancelled_state or not route.cancel_roles:
            frappe.throw(_("Credit Note cancellation is not configured."))
        authorize_workflow_field_write(
            doc, ROUTE, route.cancel_action, route.cancel_roles, permission="cancel"
        )


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    if not route.cancel_action or not route.cancelled_state or not route.cancel_roles:
        frappe.throw(_("Credit Note cancellation is not configured."))
    if doc.get("workflow_state") != route.cancelled_state:
        frappe.throw(_("Credit Notes must be cancelled through the Sales Invoice Credit Workflow."))
    persisted_state = frappe.db.get_value("Sales Invoice", doc.name, "workflow_state", for_update=True)
    if persisted_state != route.submitted_state:
        frappe.throw(_("Credit Note cancellation state is stale; reload the document and try again."))
    current_user = resolve_user(str(frappe.session.user or ""))
    if not set(frappe.get_roles(current_user)).intersection(route.cancel_roles):
        frappe.throw(_("Only an authorized Sales Manager may cancel this Credit Note."))
    require_permission(doc, "cancel")
    consume_approval_field_grant(doc, ROUTE, route.cancel_action)
