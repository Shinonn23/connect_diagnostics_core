# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any, cast

import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_with_stock(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | str | None = None,
) -> list[tuple[Any, ...]]:
    """Return enabled Item link-search rows with aggregate stock quantities."""
    frappe.has_permission("Item", throw=True)
    search_string = f"%{txt}%"
    if isinstance(filters, str):
        filters = cast(dict[str, Any], json.loads(filters))
    query_filters = filters or {}
    warehouse: str = cast(str, query_filters.get("warehouse", ""))

    def format_rows(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
        return [(row[0], row[1], f"{row[2]:g} QTY.") for row in rows]

    params = {
        "txt": search_string,
        "start": start,
        "page_len": page_len,
    }
    if warehouse:
        params["warehouse"] = warehouse
        rows = frappe.db.sql(
            """
            SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code AND b.warehouse = %(warehouse)s
            WHERE i.disabled = 0
              AND (
                i.name LIKE %(txt)s
                OR i.item_name LIKE %(txt)s
                OR i.dksh_item_code LIKE %(txt)s
                OR i.model LIKE %(txt)s
                OR EXISTS (
                    SELECT 1
                    FROM `tabItem Alternative Name` ian
                    WHERE ian.parent = i.name
                      AND ian.parenttype = 'Item'
                      AND ian.parentfield = 'alternative_names'
                      AND ian.name_value LIKE %(txt)s
                )
              )
            GROUP BY i.name
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )
    else:
        rows = frappe.db.sql(
            """
            SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code
            WHERE i.disabled = 0
              AND (
                i.name LIKE %(txt)s
                OR i.item_name LIKE %(txt)s
                OR i.dksh_item_code LIKE %(txt)s
                OR i.model LIKE %(txt)s
                OR EXISTS (
                    SELECT 1
                    FROM `tabItem Alternative Name` ian
                    WHERE ian.parent = i.name
                      AND ian.parenttype = 'Item'
                      AND ian.parentfield = 'alternative_names'
                      AND ian.name_value LIKE %(txt)s
                )
              )
            GROUP BY i.name
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )
    return format_rows(rows)
