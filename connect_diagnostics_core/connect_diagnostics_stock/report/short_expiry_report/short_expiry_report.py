# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""On-hand batches whose remaining shelf life has fallen below the item's
configured ``min_remaining_shelf_life`` (an existing Item custom field with no
other consumer yet). ``days_ahead`` lets a run override that per-item threshold
ad hoc; items with neither the field nor a filter set are skipped -- there is
no fabricated default cutoff.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.utils import cint, date_diff, getdate

type ReportColumn = dict[str, Any]
type ReportFilters = frappe._dict[str, Any]
type ReportRow = frappe._dict[str, Any]


def execute(filters: dict[str, Any] | None = None) -> tuple[list[ReportColumn], list[ReportRow]]:
    report_filters: ReportFilters = frappe._dict(filters or {})
    _validate_filters(report_filters)
    as_of_date = getdate(report_filters.get("as_of_date")) if report_filters.get("as_of_date") else getdate()
    days_ahead_override = cint(report_filters.get("days_ahead")) or None

    rows = _get_data(report_filters, as_of_date)
    rows = [row for row in rows if _is_within_threshold(row, as_of_date, days_ahead_override)]
    return _get_columns(), rows


def _validate_filters(filters: ReportFilters) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required."))


def _get_columns() -> list[ReportColumn]:
    return [
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
        {"label": _("Days Remaining"), "fieldname": "days_remaining", "fieldtype": "Int", "width": 110},
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 130,
        },
    ]


def _is_within_threshold(row: ReportRow, as_of_date: Any, days_ahead_override: int | None) -> bool:
    threshold = days_ahead_override if days_ahead_override is not None else cint(row.min_remaining_shelf_life)
    if not threshold:
        return False
    # The caller only ever passes rows the SQL query already filtered to a
    # non-null expiry_date (see `b.expiry_date IS NOT NULL`), so this is never
    # actually None -- the cast just satisfies date_diff's signature.
    row.days_remaining = date_diff(cast(str, row.expiry_date), as_of_date)
    return row.days_remaining <= threshold


def _get_data(filters: ReportFilters, as_of_date: Any) -> list[ReportRow]:
    params: dict[str, Any] = {
        "company": filters.company,
        "as_of_date": as_of_date,
        "warehouse": filters.get("warehouse") or None,
        "item": filters.get("item") or None,
    }

    rows = cast(
        list[ReportRow],
        frappe.db.sql(
            """
            SELECT
                sle.item_code, i.item_name, i.min_remaining_shelf_life,
                sle.warehouse,
                sbe.batch_no, sbe.serial_no,
                b.expiry_date,
                SUM(sbe.qty) AS qty
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            INNER JOIN `tabBatch` b ON b.name = sbe.batch_no
            WHERE sle.company = %(company)s
                AND sle.is_cancelled = 0
                AND sle.serial_and_batch_bundle IS NOT NULL
                AND DATE(sle.posting_datetime) <= %(as_of_date)s
                AND IFNULL(i.disabled, 0) = 0
                AND b.expiry_date IS NOT NULL
                AND (%(warehouse)s IS NULL OR sle.warehouse = %(warehouse)s)
                AND (%(item)s IS NULL OR sle.item_code = %(item)s)
            GROUP BY sle.item_code, sle.warehouse, sbe.batch_no, sbe.serial_no
            HAVING qty > 0.000001
            ORDER BY b.expiry_date ASC
            """,
            params,
            as_dict=True,
        ),
    )
    return rows
