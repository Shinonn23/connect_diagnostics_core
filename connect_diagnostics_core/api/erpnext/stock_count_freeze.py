# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Blocks stock transactions against items/warehouses under an active Stock Count.

Monthly cycle counts freeze the specific (item_code, warehouse) pairs being
counted; yearly counts cover an entire warehouse, so they freeze every item in
each selected warehouse instead. The freeze window is Fetch Items (the first
point count lines exist) through Submit or Cancel of the Stock Count -- a
draft Stock Count with no lines yet does not freeze anything. This is a hard
block with no bypass.
"""

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

MONTHLY = "Cycle Count (Monthly)"
YEARLY = "Yearly Count"

# doctype -> warehouse fieldnames to check on each row of its "items" child table
_WAREHOUSE_FIELDS: dict[str, tuple[str, ...]] = {
    "Stock Entry": ("s_warehouse", "t_warehouse"),
    "Delivery Note": ("warehouse", "target_warehouse"),
    "Purchase Receipt": ("warehouse", "rejected_warehouse"),
    "Sales Invoice": ("warehouse", "target_warehouse"),
    "Purchase Invoice": ("warehouse", "rejected_warehouse"),
    "Stock Reconciliation": ("warehouse",),
    "Pick List": ("warehouse",),
}
_UPDATE_STOCK_DOCTYPES = frozenset({"Sales Invoice", "Purchase Invoice"})


def validate_transaction(doc: Document, method: str | None = None) -> None:
    """Block submit when a row's item+warehouse (or whole warehouse, for Yearly counts) is under active count."""
    del method
    if doc.doctype in _UPDATE_STOCK_DOCTYPES and not doc.get("update_stock"):
        return

    pairs, warehouses = _rows_to_check(doc)
    if not pairs and not warehouses:
        return

    messages = _check_item_level(pairs) + _check_warehouse_level(warehouses)
    if messages:
        frappe.throw("<br>".join(messages), title=_("Stock Count in progress"))


def _rows_to_check(doc: Document) -> tuple[set[tuple[str, str]], set[str]]:
    fields = _WAREHOUSE_FIELDS.get(doc.doctype, ())
    pairs: set[tuple[str, str]] = set()
    warehouses: set[str] = set()
    for row in doc.get("items", []):
        item_code = cast(str, row.get("item_code") or "")
        for fieldname in fields:
            warehouse = cast(str, row.get(fieldname) or "")
            if not warehouse:
                continue
            warehouses.add(warehouse)
            if item_code:
                pairs.add((item_code, warehouse))
    return pairs, warehouses


def _check_item_level(pairs: set[tuple[str, str]]) -> list[str]:
    """Monthly cycle counts: block only the exact (item_code, warehouse) pairs being counted."""
    if not pairs:
        return []
    item_codes = tuple({item_code for item_code, _warehouse in pairs})
    warehouses = tuple({warehouse for _item_code, warehouse in pairs})
    rows = frappe.db.sql(
        """
        select sci.item_code, sci.warehouse, sc.name as stock_count
        from `tabStock Count Item` sci
        inner join `tabStock Count` sc on sc.name = sci.parent
        where sc.docstatus = 0
            and sc.count_type = %(monthly)s
            and sci.item_code in %(item_codes)s
            and sci.warehouse in %(warehouses)s
        """,
        {"monthly": MONTHLY, "item_codes": item_codes, "warehouses": warehouses},
        as_dict=True,
    )
    return [
        _("Item {0} in Warehouse {1} is frozen by Stock Count {2} (count in progress).").format(
            frappe.bold(row.item_code), frappe.bold(row.warehouse), frappe.bold(row.stock_count)
        )
        for row in rows
        if (row.item_code, row.warehouse) in pairs
    ]


def _check_warehouse_level(warehouses: set[str]) -> list[str]:
    """Yearly counts cover the whole warehouse: block every item in a selected warehouse."""
    if not warehouses:
        return []
    rows = frappe.db.sql(
        """
        select distinct scw.warehouse, sc.name as stock_count
        from `tabStock Count Warehouse` scw
        inner join `tabStock Count` sc on sc.name = scw.parent
        where sc.docstatus = 0
            and sc.count_type = %(yearly)s
            and scw.warehouse in %(warehouses)s
            and exists (select 1 from `tabStock Count Item` sci where sci.parent = sc.name)
        """,
        {"yearly": YEARLY, "warehouses": tuple(warehouses)},
        as_dict=True,
    )
    return [
        _("Warehouse {0} is frozen by Stock Count {1} (yearly count in progress).").format(
            frappe.bold(row.warehouse), frappe.bold(row.stock_count)
        )
        for row in rows
    ]
