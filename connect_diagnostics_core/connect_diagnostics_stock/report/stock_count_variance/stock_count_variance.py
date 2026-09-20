# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Variance summary across Stock Count lines: only rows where the physical count
disagreed with the system quantity. Monthly counts use this to plan re-bins and
holding transfers; yearly counts use it to review the posting before approval.
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
    return _get_columns(), _get_data(report_filters)


def _validate_filters(filters: ReportFilters) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required."))


def _get_columns() -> list[ReportColumn]:
    return [
        {
            "label": _("Stock Count"),
            "fieldname": "stock_count",
            "fieldtype": "Link",
            "options": "Stock Count",
            "width": 140,
        },
        {"label": _("Count Type"), "fieldname": "count_type", "fieldtype": "Data", "width": 150},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 130,
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 130,
        },
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
        {
            "label": _("Batch No"),
            "fieldname": "batch_no",
            "fieldtype": "Link",
            "options": "Batch",
            "width": 110,
        },
        {"label": _("Serial No"), "fieldname": "serial_no", "fieldtype": "Data", "width": 110},
        {"label": _("System Qty"), "fieldname": "system_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Count Qty"), "fieldname": "count_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Variance Qty"), "fieldname": "variance_qty", "fieldtype": "Float", "width": 110},
        {
            "label": _("Valuation Rate"),
            "fieldname": "valuation_rate",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Variance Value"),
            "fieldname": "variance_value",
            "fieldtype": "Currency",
            "width": 120,
        },
    ]


def _get_data(filters: ReportFilters) -> list[ReportRow]:
    params: dict[str, Any] = {
        "company": filters.company,
        "stock_count": filters.get("stock_count") or None,
        "count_type": filters.get("count_type") or None,
        "warehouse": filters.get("warehouse") or None,
        "from_posting_date": filters.get("from_posting_date") or None,
        "to_posting_date": filters.get("to_posting_date") or None,
    }

    rows = cast(
        list[ReportRow],
        frappe.db.sql(
            """
            SELECT
                sc.name AS stock_count,
                sc.count_type,
                sc.posting_date,
                sci.warehouse,
                sci.item_code,
                sci.item_name,
                sci.batch_no,
                sci.serial_no,
                sci.system_qty,
                sci.count_qty,
                sci.variance_qty,
                sci.valuation_rate
            FROM `tabStock Count` sc
            INNER JOIN `tabStock Count Item` sci
                ON sci.parent = sc.name
                AND sci.parenttype = 'Stock Count'
                AND sci.parentfield = 'items'
            WHERE sc.company = %(company)s
                AND sc.docstatus < 2
                AND ABS(sci.variance_qty) > 0.000001
                AND (%(stock_count)s IS NULL OR sc.name = %(stock_count)s)
                AND (%(count_type)s IS NULL OR sc.count_type = %(count_type)s)
                AND (%(warehouse)s IS NULL OR sci.warehouse = %(warehouse)s)
                AND (%(from_posting_date)s IS NULL OR sc.posting_date >= %(from_posting_date)s)
                AND (%(to_posting_date)s IS NULL OR sc.posting_date <= %(to_posting_date)s)
            ORDER BY sc.posting_date DESC, sc.name ASC, sci.idx ASC
            """,
            params,
            as_dict=True,
        ),
    )

    for row in rows:
        row.variance_value = (row.variance_qty or 0) * (row.valuation_rate or 0)

    return rows
