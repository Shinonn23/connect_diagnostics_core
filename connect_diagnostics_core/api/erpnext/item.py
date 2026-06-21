# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def validate(doc, method=None):
    if doc.has_dksh_code:
        if doc.item_code_is_dksh_code:
            # OPTI / DKSH-only: item_code itself is the DKSH code. Do NOT copy it into
            # dksh_item_code — a CD-coded item may legitimately map to the same
            # DKSH code via that field, and copying it would trip the unique constraint.
            # Search still matches these items by item_code (= name).
            doc.dksh_item_code = None
        elif not doc.dksh_item_code:
            frappe.throw(_("DKSH Item Code is required when 'Has DKSH Code' is ticked."))
    else:
        # keep data clean + free the unique value when unticked
        doc.item_code_is_dksh_code = 0
        doc.dksh_item_code = None


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_with_stock(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None = None,
) -> list[tuple]:
    frappe.has_permission("Item", throw=True)

    search_string = f"%{txt}%"
    warehouse: str = (filters or {}).get("warehouse", "")

    def _format(rows: list[tuple]) -> list[tuple]:
        return [(r[0], r[1], f"{r[2]:g} QTY.") for r in rows]

    params = {
        "txt": search_string,
        "start": start,
        "page_len": page_len,
    }

    if warehouse:
        params["warehouse"] = warehouse
        return _format(
            frappe.db.sql(
                """
                SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
                FROM `tabItem` i
                LEFT JOIN `tabBin` b ON i.name = b.item_code AND b.warehouse = %(warehouse)s
                LEFT JOIN `tabItem Alternative Name` ian ON ian.parent = i.name
                WHERE i.disabled = 0
                  AND (
                    i.name LIKE %(txt)s
                    OR i.item_name LIKE %(txt)s
                    OR i.dksh_item_code LIKE %(txt)s
                    OR i.model LIKE %(txt)s
                    OR ian.name_value LIKE %(txt)s
                  )
                GROUP BY i.name
                LIMIT %(start)s, %(page_len)s
                """,
                params,
            )
        )

    return _format(
        frappe.db.sql(
            """
            SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code
            LEFT JOIN `tabItem Alternative Name` ian ON ian.parent = i.name
            WHERE i.disabled = 0
              AND (
                i.name LIKE %(txt)s
                OR i.item_name LIKE %(txt)s
                OR i.dksh_item_code LIKE %(txt)s
                OR i.model LIKE %(txt)s
                OR ian.name_value LIKE %(txt)s
              )
            GROUP BY i.name
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )
    )
