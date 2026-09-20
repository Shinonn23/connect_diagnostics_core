# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server methods for the Stock Count doctype.

`fetch_items` builds count lines from the Stock Ledger, per selected
warehouse -- each warehouse is a leaf node in the native Warehouse tree, so
Bin/SLE's item + warehouse aggregation is already the finest grain there is.
"""

from __future__ import annotations

import math
import random
from typing import Any, cast

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe import _
from frappe.utils import flt, get_datetime

MONTHLY = "Cycle Count (Monthly)"
YEARLY = "Yearly Count"

_VARIANCE_EPSILON = 0.000001

_LineKey = tuple[str, str, str, str]


@frappe.whitelist()
def fetch_items(stock_count: str) -> dict[str, Any]:
    """Populate a draft Stock Count with current on-hand lines across its warehouses.

    Yearly counts always cover every selected warehouse. Monthly counts honour
    the selection method (manual, random by count / percentage, or one random
    warehouse). Existing entered counts are preserved across re-fetches.
    """
    doc = frappe.get_doc("Stock Count", stock_count)
    frappe.has_permission("Stock Count", doc=doc, ptype="write", throw=True)
    if doc.docstatus != 0:
        frappe.throw(_("Items can only be fetched while the Stock Count is a draft."))

    selected = [row.warehouse for row in doc.warehouses]
    chosen_warehouse = None
    if doc.count_type == MONTHLY and (doc.selection_method or "Manual") == "Random by Warehouse":
        chosen_warehouse = random.choice(selected)
        selected = [chosen_warehouse]

    warehouses = _leaf_warehouses(selected)
    cutoff = get_datetime(f"{doc.posting_date} {doc.posting_time}")

    candidates = _candidate_lines(doc.company, warehouses, cutoff)
    candidates = _apply_selection(doc, candidates)

    preserved = _existing_counts(doc)
    doc.set("items", [])
    for line in candidates:
        doc.append("items", {**line, "count_qty": preserved.get(_line_key(line), 0.0)})
    doc.save()

    count = len(doc.items)
    if chosen_warehouse:
        message = _("Fetched {0} count lines from {1}.").format(count, chosen_warehouse)
    else:
        message = _("Fetched {0} count lines.").format(count)
    return {"data": {"count": count}, "message": message}


def _leaf_warehouses(warehouses: list[str]) -> list[str]:
    from frappe.utils.nestedset import get_descendants_of

    leaves: list[str] = []
    for warehouse in warehouses:
        if frappe.get_cached_value("Warehouse", warehouse, "is_group"):
            leaves += get_descendants_of("Warehouse", warehouse, ignore_permissions=True)
        else:
            leaves.append(warehouse)
    return list(dict.fromkeys(leaves))


def _candidate_lines(company: str, warehouses: list[str], cutoff: Any) -> list[dict[str, Any]]:
    if not warehouses:
        return []
    lines = _tracked_lines(company, warehouses, cutoff)
    lines += _untracked_lines(company, warehouses, cutoff)
    _fill_expiry_dates(lines)
    _fill_valuation_rates(lines)
    return lines


def _tracked_lines(company: str, warehouses: list[str], cutoff: Any) -> list[dict[str, Any]]:
    """Serial/batch items: net the signed Serial and Batch Entry qty per warehouse."""
    rows = frappe.db.sql(
        """
        select
            sle.item_code, i.item_name, i.stock_uom,
            sle.warehouse,
            sbe.batch_no, sbe.serial_no,
            sum(sbe.qty) as net_qty
        from `tabStock Ledger Entry` sle
        inner join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
        inner join `tabItem` i on i.name = sle.item_code
        where sle.company = %(company)s
            and sle.warehouse in %(warehouses)s
            and sle.is_cancelled = 0
            and sle.serial_and_batch_bundle is not null
            and sle.posting_datetime <= %(cutoff)s
            and ifnull(i.disabled, 0) = 0
            and i.is_stock_item = 1
        group by sle.item_code, sle.warehouse, sbe.batch_no, sbe.serial_no
        having net_qty > 0.000001
        """,
        {
            "company": company,
            "warehouses": tuple(warehouses),
            "cutoff": cutoff,
        },
        as_dict=True,
    )
    return [_line_from_row(row) for row in rows]


def _untracked_lines(company: str, warehouses: list[str], cutoff: Any) -> list[dict[str, Any]]:
    """Plain items (no serial/batch bundle): aggregate SLE actual_qty per warehouse."""
    rows = frappe.db.sql(
        """
        select
            sle.item_code, i.item_name, i.stock_uom,
            sle.warehouse,
            sum(sle.actual_qty) as net_qty
        from `tabStock Ledger Entry` sle
        inner join `tabItem` i on i.name = sle.item_code
        where sle.company = %(company)s
            and sle.warehouse in %(warehouses)s
            and sle.is_cancelled = 0
            and sle.serial_and_batch_bundle is null
            and sle.posting_datetime <= %(cutoff)s
            and ifnull(i.disabled, 0) = 0
            and i.is_stock_item = 1
        group by sle.item_code, sle.warehouse
        having net_qty > 0.000001
        """,
        {
            "company": company,
            "warehouses": tuple(warehouses),
            "cutoff": cutoff,
        },
        as_dict=True,
    )
    return [_line_from_row(row) for row in rows]


def _line_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_code": row["item_code"],
        "item_name": row.get("item_name"),
        "stock_uom": row.get("stock_uom"),
        "warehouse": row["warehouse"],
        "batch_no": row.get("batch_no"),
        "serial_no": row.get("serial_no"),
        "system_qty": row["net_qty"],
    }


def _fill_valuation_rates(lines: list[dict[str, Any]]) -> None:
    """Approximate each line's rate from the item+warehouse Bin valuation.

    Location/batch-level valuation isn't tracked separately, so the current
    Bin rate (the same figure `get_stock_balance` reports) is the best available
    per-item estimate; it drives the value posted by the generated correction.
    """
    keys = {(line["item_code"], line["warehouse"]) for line in lines}
    if not keys:
        return
    rates: dict[tuple[str, str], float] = {}
    for item_code, warehouse in keys:
        rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
        rates[(item_code, warehouse)] = rate or 0.0
    for line in lines:
        line["valuation_rate"] = rates.get((line["item_code"], line["warehouse"]), 0.0)


def _fill_expiry_dates(lines: list[dict[str, Any]]) -> None:
    batch_nos = {line["batch_no"] for line in lines if line.get("batch_no")}
    if not batch_nos:
        return
    expiry = dict(
        frappe.get_all(
            "Batch",
            filters={"name": ("in", list(batch_nos))},
            fields=["name", "expiry_date"],
            as_list=True,
        )
    )
    for line in lines:
        if line.get("batch_no"):
            line["expiry_date"] = expiry.get(line["batch_no"])


def _apply_selection(doc: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Narrow the fetched lines for a monthly cycle count.

    Sampling is done at the count-line grain -- each distinct item / warehouse /
    batch / serial combination is one unit -- so "Random by Count = 50" yields
    at most 50 lines total, not 50 items' worth of lines. "Random by Warehouse"
    has already narrowed the candidate warehouse in `fetch_items`, so every
    candidate line reaching this point is kept, same as "Manual".
    """
    if doc.count_type == YEARLY:
        return candidates

    method = doc.selection_method or "Manual"
    if method in ("Manual", "Random by Warehouse"):
        return candidates

    if method == "Random by Count":
        sample_size = min(int(doc.sample_count or 0), len(candidates))
    else:  # Random by Percentage
        sample_size = min(math.ceil(len(candidates) * (doc.sample_percentage or 0) / 100.0), len(candidates))

    if sample_size <= 0:
        return []
    return random.sample(candidates, sample_size)


def _existing_counts(doc: Any) -> dict[_LineKey, float]:
    counts: dict[_LineKey, float] = {}
    for row in doc.items:
        if row.count_qty:
            counts[_line_key(_line_from_child(row))] = cast(float, row.count_qty)
    return counts


def _line_from_child(row: Any) -> dict[str, Any]:
    return {
        "item_code": row.item_code,
        "warehouse": row.warehouse,
        "batch_no": row.batch_no,
        "serial_no": row.serial_no,
    }


def _line_key(line: dict[str, Any]) -> _LineKey:
    return (
        line.get("item_code") or "",
        line.get("warehouse") or "",
        line.get("batch_no") or "",
        (line.get("serial_no") or "").strip(),
    )


@frappe.whitelist()
def generate_holding_transfer(stock_count: str) -> dict[str, Any]:
    """Monthly only: create a native holding-transfer draft.

    The draft is deliberately not submitted here. Native Stock Entry Workflow
    approval and posting remain the only source of stock effects.
    """
    doc = _load_submitted_stock_count(stock_count, MONTHLY)
    if not doc.holding_warehouse:
        frappe.throw(_("Set a Holding Warehouse before generating the transfer."))
    if any(row.entry_type == "Material Transfer" and row.stock_entry for row in doc.adjustments):
        frappe.throw(_("A holding transfer has already been generated for this Stock Count."))

    rows = [row for row in doc.items if abs(row.variance_qty or 0.0) > _VARIANCE_EPSILON]
    if not rows:
        return {"data": None, "message": _("No mismatched lines; nothing to transfer.")}

    entry = cast(StockEntry, frappe.new_doc("Stock Entry"))
    entry.stock_entry_type = "Material Transfer"
    entry.company = doc.company
    source_warehouses = {row.warehouse for row in rows}
    if len(source_warehouses) == 1:
        entry.from_warehouse = source_warehouses.pop()
    entry.to_warehouse = doc.holding_warehouse
    entry.posting_date = doc.posting_date
    entry.posting_time = doc.posting_time
    entry.set_posting_time = 1
    entry.stock_count = doc.name  # ty: ignore[unresolved-attribute] - runtime-injected custom field (setup/stock_entry.py)
    entry.remarks = _("Auto-generated from {0} (Cycle Count / mismatched lines)").format(doc.name)
    for row in rows:
        entry.append(
            "items",
            _stock_entry_row(row, s_warehouse=row.warehouse, t_warehouse=doc.holding_warehouse),
        )
    entry.insert(ignore_permissions=True)
    entry_name = cast(str, entry.name)

    _append_adjustment(
        doc, "Material Transfer", entry_name, None, _("{0} mismatched line(s)").format(len(rows))
    )
    doc.save(ignore_permissions=True)

    return {
        "data": {"stock_entry": entry_name, "count": len(rows)},
        "message": _(
            "Created holding transfer draft {0} for {1} line(s); submit it through its Workflow."
        ).format(entry_name, len(rows)),
    }


@frappe.whitelist()
def generate_stock_adjustment(stock_count: str) -> dict[str, Any]:
    """Yearly only: create one native Stock Reconciliation draft.

    The Count endpoint never creates a parallel receipt/issue posting engine or
    submits a reconciliation. Native Stock Reconciliation Workflow owns review,
    submit, ledger and GL effects.
    """
    doc = _load_submitted_stock_count(stock_count, YEARLY)
    if any(row.stock_reconciliation for row in doc.adjustments):
        frappe.throw(_("A stock adjustment has already been generated for this Stock Count."))

    rows = [row for row in doc.items if abs(row.variance_qty or 0.0) > _VARIANCE_EPSILON]
    if not rows:
        return {"data": None, "message": _("No variance; nothing to adjust.")}

    reconciliation = frappe.new_doc("Stock Reconciliation")
    reconciliation.set("company", doc.company)
    reconciliation.set("purpose", "Stock Reconciliation")
    reconciliation.set("posting_date", doc.posting_date)
    reconciliation.set("posting_time", doc.posting_time)
    reconciliation.set("set_posting_time", 1)
    reconciliation.set("stock_count", doc.name)
    reconciliation.set(
        "remarks",
        _("Generated from {0}; native review and posting required.").format(doc.name),
    )
    for row in rows:
        reconciliation.append(
            "items",
            {
                "item_code": row.item_code,
                "warehouse": row.warehouse,
                "qty": row.count_qty,
                "valuation_rate": row.valuation_rate,
                "use_serial_batch_fields": int(bool(row.batch_no or row.serial_no)),
                "batch_no": row.batch_no,
                "serial_no": row.serial_no,
            },
        )
    reconciliation.insert(ignore_permissions=True)
    reconciliation_name = cast(str, reconciliation.name)
    _append_adjustment(
        doc,
        "Stock Reconciliation",
        None,
        reconciliation_name,
        _("Variance: {0} line(s)").format(len(rows)),
    )
    doc.save(ignore_permissions=True)

    return {
        "data": {"stock_reconciliation": reconciliation_name, "count": len(rows)},
        "message": _("Created native Stock Reconciliation {0}; submit it through its Workflow.").format(
            reconciliation_name
        ),
    }


def _load_submitted_stock_count(stock_count: str, expected_count_type: str) -> Any:
    doc = frappe.get_doc("Stock Count", stock_count)
    roles = set(frappe.get_roles())
    if not roles & {"Stock Manager", "System Manager"}:
        frappe.throw(_("Only a Stock Manager can generate stock adjustments."))
    frappe.has_permission("Stock Count", doc=doc, ptype="write", throw=True)
    if doc.count_type != expected_count_type:
        frappe.throw(_("This action is only available for {0}.").format(expected_count_type))
    if doc.docstatus != 1:
        frappe.throw(_("The Stock Count must be submitted before generating adjustments."))
    return doc


def _stock_entry_row(
    row: Any,
    *,
    s_warehouse: str | None = None,
    t_warehouse: str | None = None,
) -> dict[str, Any]:
    """Build one Stock Entry Detail row from a counted Stock Count Item line."""
    item_row: dict[str, Any] = {
        "item_code": row.item_code,
        "qty": abs(row.variance_qty or 0.0),
        "uom": row.stock_uom,
        "stock_uom": row.stock_uom,
        "conversion_factor": 1,
        "basic_rate": flt(row.valuation_rate),
    }
    if s_warehouse:
        item_row["s_warehouse"] = s_warehouse
    if t_warehouse:
        item_row["t_warehouse"] = t_warehouse
    if row.batch_no or row.serial_no:
        item_row["use_serial_batch_fields"] = 1
        item_row["batch_no"] = row.batch_no
        item_row["serial_no"] = row.serial_no
    return item_row


def _append_adjustment(
    doc: Any,
    entry_type: str,
    stock_entry: str | None,
    stock_reconciliation: str | None,
    remarks: str,
) -> None:
    doc.append(
        "adjustments",
        {
            "entry_type": entry_type,
            "stock_entry": stock_entry,
            "stock_reconciliation": stock_reconciliation,
            "remarks": remarks,
        },
    )
