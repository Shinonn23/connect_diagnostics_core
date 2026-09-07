# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

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

    from_delivery_date_value = filters.get("from_delivery_date")
    to_delivery_date_value = filters.get("to_delivery_date")
    from_delivery_date = getdate(from_delivery_date_value) if from_delivery_date_value else None
    to_delivery_date = getdate(to_delivery_date_value) if to_delivery_date_value else None
    if from_delivery_date and to_delivery_date and from_delivery_date > to_delivery_date:
        frappe.throw(_("From Delivery Date cannot be greater than To Delivery Date."))


def _get_columns() -> list[ReportColumn]:
    return [
        {"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 100},
        {
            "label": _("Sales Order"),
            "fieldname": "sales_order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "width": 150,
        },
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 140,
        },
        {
            "label": _("Customer Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Delivery Date"),
            "fieldname": "delivery_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Overdue Days"),
            "fieldname": "overdue_days",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 150,
        },
        {
            "label": _("Department"),
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 170,
        },
        {
            "label": _("Territory"),
            "fieldname": "territory",
            "fieldtype": "Link",
            "options": "Territory",
            "width": 130,
        },
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
        {
            "label": _("Delivered Qty"),
            "fieldname": "delivered_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Pending Qty"),
            "fieldname": "pending_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("UOM"),
            "fieldname": "uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 90,
        },
        {
            "label": _("Net Rate"),
            "fieldname": "net_rate",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "label": _("Pending Amount"),
            "fieldname": "pending_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "label": _("Currency"),
            "fieldname": "currency",
            "fieldtype": "Link",
            "options": "Currency",
            "width": 100,
        },
        {
            "label": _("Company"),
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 160,
        },
    ]


def _get_data(filters: ReportFilters) -> list[ReportRow]:
    params: dict[str, Any] = {
        "company": filters.company,
        "from_delivery_date": filters.get("from_delivery_date") or None,
        "to_delivery_date": filters.get("to_delivery_date") or None,
        "customer": filters.get("customer") or None,
        "sales_order": filters.get("sales_order") or None,
        "item": filters.get("item") or None,
        "warehouse": filters.get("warehouse") or None,
        "department": filters.get("department") or None,
        "territory": filters.get("territory") or None,
    }

    rows = cast(
        list[ReportRow],
        frappe.db.sql(
            """
            SELECT
                so.transaction_date AS order_date,
                so.name AS sales_order,
                so.status,
                so.customer,
                so.customer_name,
                soi.delivery_date,
                soi.item_code,
                soi.item_name,
                soi.warehouse,
                soi.department,
                soi.territory,
                soi.qty,
                soi.delivered_qty,
                soi.uom,
                soi.net_rate,
                so.currency,
                so.company
            FROM `tabSales Order` so
            INNER JOIN `tabSales Order Item` soi
                ON soi.parent = so.name
                AND soi.parenttype = 'Sales Order'
                AND soi.parentfield = 'items'
            WHERE so.company = %(company)s
                AND so.docstatus = 1
                AND so.skip_delivery_note = 0
                AND so.status NOT IN ('On Hold', 'Closed', 'Completed', 'Cancelled')
                AND soi.qty > soi.delivered_qty
                AND (%(from_delivery_date)s IS NULL OR soi.delivery_date >= %(from_delivery_date)s)
                AND (%(to_delivery_date)s IS NULL OR soi.delivery_date <= %(to_delivery_date)s)
                AND (%(customer)s IS NULL OR so.customer = %(customer)s)
                AND (%(sales_order)s IS NULL OR so.name = %(sales_order)s)
                AND (%(item)s IS NULL OR soi.item_code = %(item)s)
                AND (%(warehouse)s IS NULL OR soi.warehouse = %(warehouse)s)
                AND (%(department)s IS NULL OR soi.department = %(department)s)
                AND (%(territory)s IS NULL OR soi.territory = %(territory)s)
            ORDER BY soi.delivery_date ASC, so.name ASC, soi.idx ASC
            """,
            params,
            as_dict=True,
        ),
    )

    current_date = cast(date, getdate(today()))
    for row in rows:
        pending_qty = flt(row.qty) - flt(row.delivered_qty)
        row.pending_qty = pending_qty
        row.pending_amount = pending_qty * flt(row.net_rate)
        delivery_date = getdate(row.delivery_date)
        row.overdue_days = max(date_diff(current_date, delivery_date), 0) if delivery_date else 0

    return rows
