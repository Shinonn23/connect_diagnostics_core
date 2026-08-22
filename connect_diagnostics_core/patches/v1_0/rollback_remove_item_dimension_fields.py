# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_item_dimension_fields — recreate the fields.

The original Length/Width/Height values cannot be recovered here (the Custom Fields
were deleted and their columns dropped); this only restores the empty fields so the
schema matches the pre-removal state. The insert position is approximate and does not
affect data.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

_FIELDS: tuple[dict[str, str], ...] = (
    {
        "fieldname": "width",
        "label": "Width",
        "fieldtype": "Float",
        "insert_after": "weight_per_unit",
    },
    {
        "fieldname": "height",
        "label": "Height",
        "fieldtype": "Float",
        "insert_after": "width",
    },
    {
        "fieldname": "length",
        "label": "Length",
        "fieldtype": "Float",
        "insert_after": "height",
    },
)


def execute() -> None:
    for field in _FIELDS:
        if frappe.db.exists("Custom Field", f"Item-{field['fieldname']}"):
            continue
        create_custom_field("Item", field)
    frappe.db.commit()
