"""
Revert Item naming-by-series back to manual Item Code entry.

Removes the Item naming_series property setters, the supplier-abbr / primary-supplier
machinery that only existed to auto-generate Item Code, and switches Stock Settings
back to "Item Code". Existing Item names are left untouched.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.db.set_single_value("Stock Settings", "item_naming_by", "Item Code")

    # Drop the leftover Item naming_series property setters (default / options / reqd / hidden).
    frappe.db.delete("Property Setter", {"doc_type": "Item", "field_name": "naming_series"})

    # Drop custom fields that only fed the removed Item-Code generator.
    for doctype, fieldname in (("Supplier", "abbr"), ("Item", "primary_supplier")):
        name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
        if name:
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

    frappe.clear_cache(doctype="Item")
    frappe.clear_cache(doctype="Supplier")
    frappe.db.commit()
