"""Rollback for remove_cd_supplier_code_field — recreate the field.

The original per-record values cannot be recovered (the column was dropped); this
only restores the empty Custom Field so the schema matches the pre-removal state.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    if frappe.db.exists("Custom Field", "Supplier-cd_supplier_code"):
        return

    create_custom_field(
        "Supplier",
        {
            "fieldname": "cd_supplier_code",
            "label": "CD Supplier Code",
            "fieldtype": "Data",
            "insert_after": "naming_series",
            "unique": 1,
        },
    )
    frappe.db.commit()
