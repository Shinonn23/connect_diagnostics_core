# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""ของที่ยังไม่คืน: outbound less accepted returns, recovery, settlement and write-off."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate

type ReportColumn = dict[str, Any]
type ReportRow = frappe._dict[str, Any]


def execute(filters: dict[str, Any] | None = None) -> tuple[list[ReportColumn], list[ReportRow]]:
    report_filters = frappe._dict(filters or {})
    if not report_filters.get("company"):
        frappe.throw(_("Company is required."))
    if not report_filters.get("as_of_date"):
        report_filters.as_of_date = getdate()
    return get_columns(), get_outstanding_rows(report_filters)


def get_outstanding_rows(filters: dict[str, Any]) -> list[ReportRow]:
    """Return outstanding rows for the report and Material Request close guard."""
    report_filters = frappe._dict(filters)
    as_of_date = getdate(report_filters.get("as_of_date"))
    params: dict[str, Any] = {
        "company": report_filters.get("company"),
        "as_of_datetime": get_datetime(f"{as_of_date} 23:59:59"),
        "as_of_date": as_of_date,
        "request_usage": report_filters.get("request_usage") or None,
        "responsible_employee": report_filters.get("responsible_employee") or None,
        "customer": report_filters.get("customer") or None,
        "material_request": report_filters.get("material_request") or None,
        "overdue_only": cint(report_filters.get("overdue_only")),
    }

    return cast(
        list[ReportRow],
        frappe.db.sql(
            """
            WITH accepted_returns AS (
                SELECT dt.against_dispatch_transfer,
                    SUM(CASE WHEN (
                        (dt.reference_doctype = 'Stock Entry' AND EXISTS (
                            SELECT 1 FROM `tabQuality Inspection` qi
                            WHERE qi.docstatus = 1 AND qi.status = 'Accepted'
                                AND qi.modified <= %(as_of_datetime)s
                                AND qi.return_dispatch_transfer = dt.name
                                AND qi.child_row_reference = dt.end_transit_stock_entry_detail
                        )) OR (dt.reference_doctype = 'Asset Movement' AND EXISTS (
                            SELECT 1 FROM `tabBorrowed Asset Return Inspection` bari
                            WHERE bari.docstatus = 1 AND bari.inspection_result = 'Accepted'
                                AND bari.modified <= %(as_of_datetime)s
                                AND bari.return_dispatch_transfer = dt.name
                        ))
                    ) THEN dt.qty ELSE 0 END) AS returned_qty,
                    SUM(CASE WHEN NOT (
                        (dt.reference_doctype = 'Stock Entry' AND EXISTS (
                            SELECT 1 FROM `tabQuality Inspection` qi
                            WHERE qi.docstatus = 1 AND qi.status = 'Accepted'
                                AND qi.modified <= %(as_of_datetime)s
                                AND qi.return_dispatch_transfer = dt.name
                                AND qi.child_row_reference = dt.end_transit_stock_entry_detail
                        )) OR (dt.reference_doctype = 'Asset Movement' AND EXISTS (
                            SELECT 1 FROM `tabBorrowed Asset Return Inspection` bari
                            WHERE bari.docstatus = 1 AND bari.inspection_result = 'Accepted'
                                AND bari.modified <= %(as_of_datetime)s
                                AND bari.return_dispatch_transfer = dt.name
                        ))
                    ) THEN dt.qty ELSE 0 END) AS pending_qa_qty
                FROM `tabDispatch Transfer` dt
                INNER JOIN `tabDispatch` d ON d.name = dt.parent
                WHERE d.dispatch_type = 'Return'
                    AND d.docstatus = 1
                    AND d.delivery_status = 'Delivered'
                    AND d.received_at <= %(as_of_datetime)s
                GROUP BY dt.against_dispatch_transfer
            ), resolutions AS (
                SELECT ri.material_request_item, ri.asset,
                    SUM(CASE WHEN r.resolution_type = 'Settlement' THEN ri.qty ELSE 0 END) AS settled_qty,
                    SUM(CASE WHEN r.resolution_type = 'Write-off' THEN ri.qty ELSE 0 END) AS written_off_qty
                FROM `tabBorrowed Item Resolution Item` ri
                INNER JOIN `tabBorrowed Item Resolution` r ON r.name = ri.parent
                WHERE r.docstatus = 1
                    AND r.resolution_date <= %(as_of_date)s
                    AND r.modified <= %(as_of_datetime)s
                GROUP BY ri.material_request_item, ri.asset
            ), outbound AS (
                SELECT d.material_request, dt.material_request_item, dt.asset,
                    dt.item_code, dt.uom, d.dispatched_at,
                    dt.qty AS outbound_qty,
                    CASE WHEN d.delivery_status = 'Returned to Origin'
                        AND d.delivery_confirmed_at <= %(as_of_datetime)s
                        THEN dt.qty ELSE 0 END
                        AS returned_to_origin_qty,
                    COALESCE(ar.returned_qty, 0) AS returned_qty,
                    COALESCE(ar.pending_qa_qty, 0) AS pending_qa_qty,
                    COALESCE(r.settled_qty, 0) AS settled_qty,
                    COALESCE(r.written_off_qty, 0) AS written_off_qty
                FROM `tabDispatch Transfer` dt
                INNER JOIN `tabDispatch` d ON d.name = dt.parent
                LEFT JOIN accepted_returns ar ON ar.against_dispatch_transfer = dt.name
                LEFT JOIN resolutions r
                    ON r.material_request_item = dt.material_request_item
                    AND COALESCE(r.asset, '') = COALESCE(dt.asset, '')
                WHERE d.dispatch_type = 'Outbound'
                    AND d.docstatus = 1
                    AND d.dispatched_at <= %(as_of_datetime)s
            )
            SELECT o.material_request, o.material_request_item, o.asset, o.item_code,
                o.uom, mr.responsible_employee, mr.request_usage,
                mr.destination_customer AS customer,
                COALESCE(mr.destination_customer, mr.responsible_employee, mr.asset_location) AS destination,
                MIN(o.dispatched_at) AS dispatched_at,
                mr.expected_return_date,
                SUM(o.outbound_qty) AS outbound_qty,
                SUM(o.returned_qty + o.returned_to_origin_qty) AS returned_qty,
                SUM(o.pending_qa_qty) AS pending_qa_qty,
                SUM(o.settled_qty) AS settled_qty,
                SUM(o.written_off_qty) AS written_off_qty,
                SUM(
                    o.outbound_qty - o.returned_qty - o.returned_to_origin_qty
                    - o.settled_qty - o.written_off_qty
                ) AS outstanding_qty,
                CASE
                    WHEN mr.expected_return_date < %(as_of_date)s
                    THEN DATEDIFF(%(as_of_date)s, mr.expected_return_date)
                    ELSE 0
                END AS overdue_days
            FROM outbound o
            INNER JOIN `tabMaterial Request` mr ON mr.name = o.material_request
            INNER JOIN `tabMaterial Request Item` mri ON mri.name = o.material_request_item
            WHERE mr.request_usage IN ('Employee Borrow', 'Customer Demo', 'Customer Loan')
                AND mr.company = %(company)s
                AND (%(request_usage)s IS NULL OR mr.request_usage = %(request_usage)s)
                AND (
                    %(responsible_employee)s IS NULL
                    OR mr.responsible_employee = %(responsible_employee)s
                )
                AND (%(customer)s IS NULL OR mr.destination_customer = %(customer)s)
                AND (%(material_request)s IS NULL OR mr.name = %(material_request)s)
                AND (
                    %(overdue_only)s = 0
                    OR mr.expected_return_date < %(as_of_date)s
                )
            GROUP BY o.material_request, o.material_request_item, o.asset, o.item_code,
                o.uom, mr.responsible_employee, mr.request_usage,
                mr.destination_customer, mr.asset_location, mr.expected_return_date
            HAVING SUM(
                o.outbound_qty - o.returned_qty - o.returned_to_origin_qty
                - o.settled_qty - o.written_off_qty
            ) > 0
            ORDER BY overdue_days DESC, mr.expected_return_date, o.material_request, o.item_code
            """,
            params,
            as_dict=True,
        ),
    )


def get_columns() -> list[ReportColumn]:
    return [
        {
            "label": _("Material Request"),
            "fieldname": "material_request",
            "fieldtype": "Link",
            "options": "Material Request",
            "width": 150,
        },
        {
            "label": _("MR Item"),
            "fieldname": "material_request_item",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 130,
        },
        {
            "label": _("Asset"),
            "fieldname": "asset",
            "fieldtype": "Link",
            "options": "Asset",
            "width": 130,
        },
        {"label": _("Usage"), "fieldname": "request_usage", "fieldtype": "Data", "width": 120},
        {
            "label": _("Responsible Employee"),
            "fieldname": "responsible_employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 150,
        },
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 140,
        },
        {"label": _("Destination"), "fieldname": "destination", "fieldtype": "Data", "width": 140},
        {
            "label": _("Dispatched At"),
            "fieldname": "dispatched_at",
            "fieldtype": "Datetime",
            "width": 145,
        },
        {
            "label": _("Expected Return"),
            "fieldname": "expected_return_date",
            "fieldtype": "Date",
            "width": 115,
        },
        {
            "label": _("Outstanding Qty"),
            "fieldname": "outstanding_qty",
            "fieldtype": "Float",
            "width": 115,
        },
        {"label": _("Returned Qty"), "fieldname": "returned_qty", "fieldtype": "Float", "width": 105},
        {
            "label": _("Pending QA Qty"),
            "fieldname": "pending_qa_qty",
            "fieldtype": "Float",
            "width": 115,
        },
        {"label": _("Settled Qty"), "fieldname": "settled_qty", "fieldtype": "Float", "width": 105},
        {
            "label": _("Written-off Qty"),
            "fieldname": "written_off_qty",
            "fieldtype": "Float",
            "width": 115,
        },
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
        {
            "label": _("Overdue Days"),
            "fieldname": "overdue_days",
            "fieldtype": "Int",
            "width": 105,
        },
    ]
