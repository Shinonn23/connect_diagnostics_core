"""
Switch Item naming from manual "Item Code" entry to "Naming Series",
and seed Series counters to match existing data.
"""

from __future__ import annotations

import re

import frappe


def execute() -> None:
    from connect_diagnostics_core.setup import apply_all

    apply_all()
    _set_item_naming_by_series()
    _seed_customer_supplier_counters()
    _seed_item_counters()
    frappe.db.commit()


def _set_item_naming_by_series() -> None:
    frappe.db.set_single_value("Stock Settings", "item_naming_by", "Naming Series")


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


def _seed_item_counters() -> None:
    """Set Series counters for each 01-{abbr}-{type} prefix from existing items."""
    items = frappe.db.sql(
        "SELECT name FROM `tabItem` WHERE name REGEXP '^01-[A-Z]+-0[123][0-9]+$'",
        as_list=True,
    )
    max_by_prefix: dict[str, int] = {}
    pattern = re.compile(r"^(01-[A-Z]+-0[123])(\d+)$")
    for (item_name,) in items:
        m = pattern.match(item_name)
        if m:
            prefix, num_str = m.group(1), m.group(2)
            max_by_prefix[prefix] = max(max_by_prefix.get(prefix, 0), int(num_str))

    for prefix, current in max_by_prefix.items():
        _upsert_series(prefix, current)


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
