# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Undo :mod:`move_item_dksh_fields_to_dksh_item`.

Recreates the five DKSH Custom Fields on Item, writes the values of every
``DKSH Item`` that links an Item back onto that Item, then removes those linked
``DKSH Item`` records. Stand-alone ``DKSH Item`` records (no ``item`` link) have no
Item to return to and are left in place; they never came from Item.

Idempotent: recreating an existing field is skipped, and a second run with no
linked ``DKSH Item`` records is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CODE_FIELD = "dksh_item_code"

# The definitions as they last stood in setup/item.py, kept here so the rollback
# does not depend on fields the forward patch removed from the live setup module.
FIELD_DEFS: list[dict[str, Any]] = [
    {
        "fieldname": "dksh_tab",
        "label": "DKSH",
        "fieldtype": "Tab Break",
        "insert_after": "description",
    },
    {
        "fieldname": "dksh_item_code",
        "label": "DKSH Item Code",
        "fieldtype": "Data",
        "insert_after": "dksh_tab",
        "bold": 1,
        "in_global_search": 1,
        "search_index": 1,
        "unique": 1,
    },
    {
        "fieldname": "supplier_product_code",
        "label": "Supplier Product Code",
        "fieldtype": "Data",
        "insert_after": "dksh_item_code",
    },
    {
        "fieldname": "mat_group_code",
        "label": "Mat Group Code",
        "fieldtype": "Data",
        "insert_after": "supplier_product_code",
        "fetch_from": "item_group.mat_group_code",
    },
    {
        "fieldname": "mat_group4_code",
        "label": "Mat Group4 Code",
        "fieldtype": "Data",
        "insert_after": "mat_group_code",
        "fetch_from": "item_group.mat_group4_code",
    },
    {
        "fieldname": "material_type_code",
        "label": "Material Type Code",
        "fieldtype": "Data",
        "insert_after": "mat_group4_code",
    },
]

REFERENCE_FIELDS = ("supplier_product_code", "mat_group_code", "mat_group4_code", "material_type_code")


def execute() -> None:
    """Recreate the Item fields and move linked DKSH Item values back."""
    create_custom_fields({"Item": FIELD_DEFS}, ignore_validate=True)

    linked = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "DKSH Item",
            filters={"item": ["is", "set"]},
            fields=["name", "item", CODE_FIELD, *REFERENCE_FIELDS],
        ),
    )
    for row in linked:
        item_name = _text(row.get("item"))
        if not frappe.db.exists("Item", item_name):
            continue
        frappe.db.set_value(
            "Item",
            item_name,
            {CODE_FIELD: _text(row.get(CODE_FIELD)), **{f: _text(row.get(f)) for f in REFERENCE_FIELDS}},
            update_modified=False,
        )
        frappe.delete_doc("DKSH Item", cast(str, row["name"]), ignore_permissions=True, force=True)

    frappe.db.commit()


def _text(value: Any) -> str:
    return str(value or "").strip()
