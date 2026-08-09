# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared, read-only values used by the Regulatory Script Reports."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe.utils import date_diff, getdate, today


def registration_rows(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    conditions: dict[str, Any] = {}
    for fieldname in (
        "official_status",
        "responsible_user",
        "product_family_name",
        "product_owner",
        "device_category",
    ):
        if filters.get(fieldname):
            conditions[fieldname] = filters[fieldname]
    rows = frappe.get_all(
        "Medical Device Product Registration",
        filters=conditions,
        fields=[
            "name",
            "registration_number",
            "certificate_type",
            "device_category",
            "risk_class",
            "product_family_name",
            "establishment_registration",
            "issue_date",
            "expiry_date",
            "renewal_status",
            "responsible_user",
            "official_status",
        ],
        order_by="expiry_date asc",
    )
    within_days = filters.get("expiry_within_days")
    result: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        row["days_remaining"] = (
            date_diff(cast(date, getdate(row["expiry_date"])), cast(date, getdate(today())))
            if row.get("expiry_date")
            else None
        )
        if (
            within_days is not None
            and row["days_remaining"] is not None
            and row["days_remaining"] > int(within_days)
        ):
            continue
        row.update(registration_impact(row["name"]))
        result.append(row)
    return result


def registration_impact(registration: str) -> dict[str, Any]:
    mapped_items = frappe.get_all(
        "Medical Device Registered Product", filters={"parent": registration}, pluck="item_code"
    )
    item_codes = sorted({item_code for item_code in mapped_items if item_code})
    if not item_codes:
        return {
            "affected_item_count": 0,
            "current_stock_qty": 0,
            "stock_value": 0,
            "open_po_qty": 0,
            "open_so_qty": 0,
        }
    stock = frappe.db.sql(
        "SELECT COALESCE(SUM(actual_qty), 0) AS qty, COALESCE(SUM(stock_value), 0) AS value FROM `tabBin` WHERE item_code IN %(items)s",
        {"items": tuple(item_codes)},
        as_dict=True,
    )[0]
    open_po = frappe.db.sql(
        "SELECT COALESCE(SUM(item.qty - item.received_qty), 0) AS qty FROM `tabPurchase Order Item` item INNER JOIN `tabPurchase Order` parent ON parent.name = item.parent WHERE parent.docstatus = 1 AND item.item_code IN %(items)s",
        {"items": tuple(item_codes)},
        as_dict=True,
    )[0]
    open_so = frappe.db.sql(
        "SELECT COALESCE(SUM(item.qty - item.delivered_qty), 0) AS qty FROM `tabSales Order Item` item INNER JOIN `tabSales Order` parent ON parent.name = item.parent WHERE parent.docstatus = 1 AND item.item_code IN %(items)s",
        {"items": tuple(item_codes)},
        as_dict=True,
    )[0]
    return {
        "affected_item_count": len(item_codes),
        "current_stock_qty": stock.qty,
        "stock_value": stock.value,
        "open_po_qty": open_po.qty,
        "open_so_qty": open_so.qty,
    }
