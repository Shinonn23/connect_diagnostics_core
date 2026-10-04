# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Permission-aware evidence of outbound Customer Borrow deliveries."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import date_diff, today

FILTER_COLUMNS = {
    "company": "`tabMaterial Request`.company",
    "customer": "`tabMaterial Request`.borrow_customer",
    "employee": "`tabMaterial Request`.borrow_employee",
    "item_code": "detail.item_code",
    "material_request": "`tabMaterial Request`.name",
    "warehouse": "`tabMaterial Request`.borrow_warehouse",
}


def execute(
    filters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    frappe.has_permission("Material Request", "read", throw=True)
    frappe.has_permission("Stock Entry", "read", throw=True)
    report_filters = _validate_filters(filters)
    rows = _get_data(report_filters)
    current_date = today()
    for row in rows:
        row["days_borrowed"] = max(0, date_diff(current_date, row["posting_date"]))
        due_date = row.get("expected_return_date")
        row["days_overdue"] = max(0, date_diff(current_date, due_date)) if due_date else None
        row["return_schedule"] = _("Scheduled") if due_date else _("No due date")
    return (
        _get_columns(),
        rows,
        _("Recorded outbound loans. Quantities do not include returns."),
    )


def _validate_filters(filters: dict[str, Any] | None) -> dict[str, str]:
    if filters is not None and not isinstance(filters, dict):
        frappe.throw(_("Report filters must be an object."))
    result: dict[str, str] = {}
    for fieldname, value in (filters or {}).items():
        if fieldname not in FILTER_COLUMNS:
            frappe.throw(_("Unsupported Customer Borrow filter: {0}.").format(fieldname))
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            frappe.throw(_("Customer Borrow filter values must be text."))
        result[fieldname] = value
    return result


def _get_data(filters: dict[str, str]) -> list[dict[str, Any]]:
    # Only Frappe-generated permission clauses and allowlisted column names enter
    # SQL text. All user-supplied values remain bound parameters. Keep both parent
    # table names unaliased because permission conditions reference those names.
    conditions = get_match_cond("Material Request") + get_match_cond("Stock Entry")
    params: dict[str, str] = {}
    for fieldname, value in filters.items():
        conditions += f" AND {FILTER_COLUMNS[fieldname]} = %({fieldname})s"
        params[fieldname] = value
    return cast(
        list[dict[str, Any]],
        frappe.db.sql(
            """
            SELECT
                `tabMaterial Request`.company,
                `tabMaterial Request`.borrow_customer AS customer,
                `tabMaterial Request`.borrow_employee AS employee,
                `tabMaterial Request`.borrow_warehouse AS warehouse,
                `tabMaterial Request`.borrow_expected_return_date AS expected_return_date,
                `tabMaterial Request`.name AS material_request,
                detail.material_request_item,
                detail.name AS stock_entry_detail,
                detail.item_code, detail.transfer_qty AS qty, detail.stock_uom,
                detail.s_warehouse AS source_warehouse,
                detail.serial_and_batch_bundle,
                `tabStock Entry`.name AS stock_entry,
                `tabStock Entry`.posting_date
            FROM `tabStock Entry`
            INNER JOIN `tabStock Entry Detail` detail ON detail.parent = `tabStock Entry`.name
                AND detail.parenttype = 'Stock Entry' AND detail.parentfield = 'items'
            INNER JOIN `tabMaterial Request`
                ON `tabMaterial Request`.name = `tabStock Entry`.borrow_material_request
                AND detail.material_request = `tabMaterial Request`.name
            INNER JOIN `tabMaterial Request Item` request_item
                ON request_item.name = detail.material_request_item
                AND request_item.parent = `tabMaterial Request`.name
                AND request_item.parenttype = 'Material Request' AND request_item.parentfield = 'items'
                AND request_item.item_code = detail.item_code
            WHERE `tabStock Entry`.docstatus = 1
                AND detail.docstatus = 1
                AND `tabMaterial Request`.docstatus = 1
                AND `tabMaterial Request`.material_request_type = 'Customer Borrow'
                AND `tabStock Entry`.purpose = 'Material Transfer'
                AND COALESCE(`tabStock Entry`.add_to_transit, 0) = 0
                AND COALESCE(`tabStock Entry`.outgoing_stock_entry, '') = ''
                AND detail.t_warehouse = `tabMaterial Request`.borrow_warehouse
                AND detail.transfer_qty > 0
            """
            + conditions
            + " ORDER BY `tabStock Entry`.posting_date, `tabStock Entry`.posting_time, "
            "`tabStock Entry`.name, detail.idx",
            params,
            as_dict=True,
        ),
    )


def _get_columns() -> list[dict[str, Any]]:
    return [
        _link_column("company", "Company", "Company", 130),
        _link_column("customer", "Customer", "Customer", 160),
        _link_column("employee", "Responsible Employee", "Employee", 150),
        _link_column("item_code", "Item", "Item", 150),
        {"fieldname": "qty", "label": _("Sent quantity"), "fieldtype": "Float", "width": 110},
        _link_column("stock_uom", "Stock UOM", "UOM", 90),
        _link_column("warehouse", "Borrow Warehouse", "Warehouse", 160),
        _link_column("source_warehouse", "Source Warehouse", "Warehouse", 160),
        {"fieldname": "posting_date", "label": _("Sent on"), "fieldtype": "Date", "width": 110},
        {"fieldname": "days_borrowed", "label": _("Days borrowed"), "fieldtype": "Int", "width": 110},
        {
            "fieldname": "expected_return_date",
            "label": _("Expected return date"),
            "fieldtype": "Date",
            "width": 140,
        },
        {
            "fieldname": "return_schedule",
            "label": _("Return schedule"),
            "fieldtype": "Data",
            "width": 120,
        },
        {"fieldname": "days_overdue", "label": _("Days overdue"), "fieldtype": "Int", "width": 110},
        _link_column("material_request", "Material Request", "Material Request", 170),
        _link_column("stock_entry", "Stock Entry", "Stock Entry", 170),
        _link_column("serial_and_batch_bundle", "Serial and Batch Bundle", "Serial and Batch Bundle", 170),
    ]


def _link_column(fieldname: str, label: str, options: str, width: int) -> dict[str, Any]:
    return {"fieldname": fieldname, "label": _(label), "fieldtype": "Link", "options": options, "width": width}
