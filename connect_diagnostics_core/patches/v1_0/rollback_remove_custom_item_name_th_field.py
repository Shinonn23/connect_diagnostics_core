# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_custom_item_name_th_field — recreate the field.

The original per-record Thai item names cannot be recovered here (the Custom Field
was deleted and the column later dropped by drop_custom_item_name_th_column); this
only restores the empty ``Item-custom_item_name_th`` Data field so the schema matches
the pre-removal state. The insert position is approximate and does not affect data.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute() -> None:
    if frappe.db.exists("Custom Field", "Item-custom_item_name_th"):
        return

    create_custom_field(
        "Item",
        {
            "fieldname": "custom_item_name_th",
            "label": "Item Name (Thai)",
            "fieldtype": "Data",
            "insert_after": "item_name",
            "in_global_search": 1,
        },
    )
    frappe.db.commit()
