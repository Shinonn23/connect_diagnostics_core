from __future__ import annotations

import frappe

ITEM_TYPE_MAP = {
    "ITEM01": "01",
    "ITEM02": "02",
    "ITEM03": "03",
}


def get_item_prefix(doc, key: str) -> str:
    """Named series variable: resolves ITEM01/ITEM02/ITEM03 → 01-{supplier_abbr}-{type}"""
    type_code = ITEM_TYPE_MAP.get(key, "01")
    supplier = doc.get("primary_supplier")
    if not supplier:
        return f"01-XX-{type_code}"
    abbr = frappe.db.get_value("Supplier", supplier, "abbr") or "XX"
    return f"01-{abbr.upper()}-{type_code}"
