# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_custom_cd_item_code_field — recreate the field.

The original per-record values cannot be recovered (the Custom Field was deleted and
its column dropped); this only restores the empty ``Item-custom_cd_item_code`` Data
field so the schema matches the pre-removal state. The insert position is approximate
and does not affect data.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute() -> None:
    if frappe.db.exists("Custom Field", "Item-custom_cd_item_code"):
        return

    create_custom_field(
        "Item",
        {
            "fieldname": "custom_cd_item_code",
            "label": "CD Item Code",
            "fieldtype": "Data",
            "insert_after": "item_code",
            "in_global_search": 1,
        },
    )
    frappe.db.commit()
