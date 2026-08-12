# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Per-batch/serial breakdown of what a submitted Purchase Receipt actually
received, sourced from the Stock Ledger (the same tracked/untracked split used
by Stock Count's fetch_items) so the figures always match what was posted.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _

type ReportColumn = dict[str, Any]
type ReportFilters = frappe._dict[str, Any]
type ReportRow = frappe._dict[str, Any]


def execute(filters: dict[str, Any] | None = None) -> tuple[list[ReportColumn], list[ReportRow]]:
    report_filters: ReportFilters = frappe._dict(filters or {})
    _validate_filters(report_filters)
    rows = _tracked_rows(report_filters) + _untracked_rows(report_filters)
    _fill_expiry_dates(rows)
    rows.sort(key=lambda row: (row.received_date, row.purchase_receipt, row.item_code))
    return _get_columns(), rows


def _validate_filters(filters: ReportFilters) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required."))

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date and from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date."))


def _get_columns() -> list[ReportColumn]:
    return [
        {
            "label": _("Purchase Receipt"),
            "fieldname": "purchase_receipt",
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "width": 140,
        },
        {"label": _("Date of Receive"), "fieldname": "received_date", "fieldtype": "Date", "width": 110},
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 130,
        },
        {"label": _("Description"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
        {"label": _("Serial No"), "fieldname": "serial_no", "fieldtype": "Data", "width": 110},
        {
            "label": _("Batch No"),
            "fieldname": "batch_no",
            "fieldtype": "Link",
            "options": "Batch",
            "width": 110,
        },
        {"label": _("Expiry Date"), "fieldname": "expiry_date", "fieldtype": "Date", "width": 100},
        {
            "label": _("Ref. PO No."),
            "fieldname": "purchase_order",
            "fieldtype": "Link",
            "options": "Purchase Order",
            "width": 130,
        },
    ]


def _params(filters: ReportFilters) -> dict[str, Any]:
    return {
        "company": filters.company,
        "from_date": filters.get("from_date") or None,
        "to_date": filters.get("to_date") or None,
        "purchase_receipt": filters.get("purchase_receipt") or None,
        "supplier": filters.get("supplier") or None,
        "item": filters.get("item") or None,
    }


def _tracked_rows(filters: ReportFilters) -> list[ReportRow]:
    return cast(
        list[ReportRow],
        frappe.db.sql(
            """
            SELECT
                pr.name AS purchase_receipt,
                pr.posting_date AS received_date,
                sle.item_code, i.item_name,
                sbe.batch_no, sbe.serial_no,
                sbe.qty AS qty,
                pri.purchase_order
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = sle.voucher_no
            LEFT JOIN `tabPurchase Receipt Item` pri ON pri.name = sle.voucher_detail_no
            WHERE sle.voucher_type = 'Purchase Receipt'
                AND pr.docstatus = 1
                AND pr.company = %(company)s
                AND sle.is_cancelled = 0
                AND sbe.qty > 0
                AND (%(from_date)s IS NULL OR pr.posting_date >= %(from_date)s)
                AND (%(to_date)s IS NULL OR pr.posting_date <= %(to_date)s)
                AND (%(purchase_receipt)s IS NULL OR pr.name = %(purchase_receipt)s)
                AND (%(supplier)s IS NULL OR pr.supplier = %(supplier)s)
                AND (%(item)s IS NULL OR sle.item_code = %(item)s)
            """,
            _params(filters),
            as_dict=True,
        ),
    )


def _untracked_rows(filters: ReportFilters) -> list[ReportRow]:
    return cast(
        list[ReportRow],
        frappe.db.sql(
            """
            SELECT
                pr.name AS purchase_receipt,
                pr.posting_date AS received_date,
                sle.item_code, i.item_name,
                NULL AS batch_no, NULL AS serial_no,
                sle.actual_qty AS qty,
                pri.purchase_order
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = sle.voucher_no
            LEFT JOIN `tabPurchase Receipt Item` pri ON pri.name = sle.voucher_detail_no
            WHERE sle.voucher_type = 'Purchase Receipt'
                AND pr.docstatus = 1
                AND pr.company = %(company)s
                AND sle.is_cancelled = 0
                AND sle.serial_and_batch_bundle IS NULL
                AND sle.actual_qty > 0
                AND (%(from_date)s IS NULL OR pr.posting_date >= %(from_date)s)
                AND (%(to_date)s IS NULL OR pr.posting_date <= %(to_date)s)
                AND (%(purchase_receipt)s IS NULL OR pr.name = %(purchase_receipt)s)
                AND (%(supplier)s IS NULL OR pr.supplier = %(supplier)s)
                AND (%(item)s IS NULL OR sle.item_code = %(item)s)
            """,
            _params(filters),
            as_dict=True,
        ),
    )


def _fill_expiry_dates(rows: list[ReportRow]) -> None:
    batch_nos = {row.batch_no for row in rows if row.get("batch_no")}
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
    for row in rows:
        row.expiry_date = expiry.get(row.batch_no) if row.get("batch_no") else None
