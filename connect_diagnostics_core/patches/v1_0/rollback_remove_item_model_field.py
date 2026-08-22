# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_item_model_field — recreate the field.

The original ``model`` values cannot be recovered here (the Custom Field was deleted
and its column dropped); this only restores the empty ``Item-model`` Data field so the
schema matches the pre-removal state. The insert position is approximate and does not
affect data.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute() -> None:
    if frappe.db.exists("Custom Field", "Item-model"):
        return

    create_custom_field(
        "Item",
        {
            "fieldname": "model",
            "label": "Model",
            "fieldtype": "Data",
            "insert_after": "stock_uom",
        },
    )
    frappe.db.commit()
