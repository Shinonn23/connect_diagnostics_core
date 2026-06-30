"""Rollback for remove_cd_customer_code_field — recreate the field.

The original per-record values cannot be recovered (the column was dropped); this
only restores the empty Custom Field so the schema matches the pre-removal state.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    if frappe.db.exists("Custom Field", "Customer-cd_customer_code"):
        return

    create_custom_field(
        "Customer",
        {
            "fieldname": "cd_customer_code",
            "label": "CD Customer Code",
            "fieldtype": "Data",
            "insert_after": "naming_series",
            "unique": 1,
        },
    )
    frappe.db.commit()
