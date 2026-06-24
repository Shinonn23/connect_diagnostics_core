"""
Seed Customer / Supplier Series counters to match existing data.

Item naming-by-series was removed (Item Code is entered manually); see
v1_0/revert_item_naming_series. This patch now only seeds the Customer and
Supplier series counters so their auto-numbering continues from existing data.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    from connect_diagnostics_core.setup import apply_all

    apply_all()
    _seed_customer_supplier_counters()
    frappe.db.commit()


def _seed_customer_supplier_counters() -> None:
    """Set Series counters for 2S, 4A, 4H, 5B to match current max in DB."""
    series_map = {
        "2S": _max_numeric_suffix("Customer", "2S"),
        "4A": _max_numeric_suffix("Customer", "4A"),
        "4H": _max_numeric_suffix("Customer", "4H"),
        "5B": _max_numeric_suffix("Supplier", "5B"),
    }
    for key, current in series_map.items():
        if current == 0:
            continue
        _upsert_series(key, current)


def _max_numeric_suffix(doctype: str, prefix: str) -> int:
    names = frappe.db.get_all(doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name")
    max_val = 0
    for name in names:
        suffix = name[len(prefix) :]
        if suffix.isdigit():
            max_val = max(max_val, int(suffix))
    return max_val


def _upsert_series(key: str, current: int) -> None:
    exists = frappe.db.sql("SELECT name FROM `tabSeries` WHERE name = %s", (key,), as_list=True)
    if exists:
        frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = %s", (current, key))
    else:
        frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (key, current))
