# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

type ReportColumn = dict[str, Any]
type ReportRow = dict[str, Any]


def execute(_filters: dict[str, Any] | None = None) -> tuple[list[ReportColumn], list[ReportRow]]:
    frappe.only_for("System Manager")
    models = frappe.get_all(
        "Equipment Model",
        fields=[
            "name",
            "stock_item",
            "fixed_asset_item",
            "allow_demo",
            "allow_stock_to_asset_conversion",
            "default_asset_category",
            "disabled",
        ],
        order_by="model_code asc",
    )
    stock_items = frappe.get_all(
        "Item",
        filters={"is_stock_item": 1, "is_fixed_asset": 0},
        fields=["name", "is_stock_item", "is_fixed_asset", "disabled", "asset_category"],
        order_by="name asc",
    )
    fixed_asset_items = frappe.get_all(
        "Item",
        filters={"is_stock_item": 0, "is_fixed_asset": 1},
        fields=["name", "is_stock_item", "is_fixed_asset", "disabled", "asset_category"],
        order_by="name asc",
    )
    items = {row.name: row for row in [*stock_items, *fixed_asset_items]}
    return _columns(), _build_rows(models, items, stock_items, fixed_asset_items)


def _columns() -> list[ReportColumn]:
    return [
        {
            "label": _("Stock Item"),
            "fieldname": "stock_item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "label": _("Proposed Equipment Model"),
            "fieldname": "proposed_equipment_model",
            "fieldtype": "Link",
            "options": "Equipment Model",
            "width": 190,
        },
        {
            "label": _("Fixed Asset Item"),
            "fieldname": "fixed_asset_item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {"label": _("Allow Demo"), "fieldname": "allow_demo", "fieldtype": "Check", "width": 95},
        {
            "label": _("Allow Conversion"),
            "fieldname": "allow_stock_to_asset_conversion",
            "fieldtype": "Check",
            "width": 120,
        },
        {
            "label": _("Asset Category"),
            "fieldname": "asset_category",
            "fieldtype": "Link",
            "options": "Asset Category",
            "width": 150,
        },
        {
            "label": _("Mapping Status"),
            "fieldname": "mapping_status",
            "fieldtype": "Data",
            "width": 150,
        },
    ]


def _build_rows(
    models: list[frappe._dict],
    items: dict[str, frappe._dict],
    stock_items: list[frappe._dict],
    fixed_asset_items: list[frappe._dict],
) -> list[ReportRow]:
    rows: list[ReportRow] = []
    mapped_stock_items: set[str] = set()
    mapped_fixed_asset_items: set[str] = set()

    for model in models:
        stock_item_code = str(model.stock_item or "")
        fixed_asset_item_code = str(model.fixed_asset_item or "")
        if stock_item_code:
            mapped_stock_items.add(stock_item_code)
        if fixed_asset_item_code:
            mapped_fixed_asset_items.add(fixed_asset_item_code)
        stock_item = items.get(stock_item_code)
        fixed_asset_item = items.get(fixed_asset_item_code)
        rows.append(
            {
                "stock_item": stock_item_code or None,
                "proposed_equipment_model": model.name,
                "fixed_asset_item": fixed_asset_item_code or None,
                "allow_demo": model.allow_demo,
                "allow_stock_to_asset_conversion": model.allow_stock_to_asset_conversion,
                "asset_category": model.default_asset_category
                or (fixed_asset_item.asset_category if fixed_asset_item else None),
                "mapping_status": _mapping_status(model, stock_item, fixed_asset_item),
            }
        )

    rows.extend(
        {
            "stock_item": item.name,
            "proposed_equipment_model": None,
            "fixed_asset_item": None,
            "allow_demo": 0,
            "allow_stock_to_asset_conversion": 0,
            "asset_category": None,
            "mapping_status": "Unmapped Stock Item",
        }
        for item in stock_items
        if item.name not in mapped_stock_items
    )
    rows.extend(
        {
            "stock_item": None,
            "proposed_equipment_model": None,
            "fixed_asset_item": item.name,
            "allow_demo": 0,
            "allow_stock_to_asset_conversion": 0,
            "asset_category": item.asset_category,
            "mapping_status": "Unmapped Fixed Asset Item",
        }
        for item in fixed_asset_items
        if item.name not in mapped_fixed_asset_items
    )
    return rows


def _mapping_status(
    model: frappe._dict,
    stock_item: frappe._dict | None,
    fixed_asset_item: frappe._dict | None,
) -> str:
    if model.disabled:
        return "Disabled Model"
    if (
        not stock_item
        or not stock_item.is_stock_item
        or stock_item.is_fixed_asset
        or not fixed_asset_item
        or fixed_asset_item.is_stock_item
        or not fixed_asset_item.is_fixed_asset
    ):
        return "Invalid Mapping"
    if (model.allow_demo or model.allow_stock_to_asset_conversion) and (
        stock_item.disabled or fixed_asset_item.disabled
    ):
        return "Invalid Mapping"
    return "Mapped"
