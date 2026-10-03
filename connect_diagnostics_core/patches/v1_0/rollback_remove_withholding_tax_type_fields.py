# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_withholding_tax_type_fields — recreate the fields.

The original Withholding Tax Type values cannot be recovered here (the Custom Fields
were deleted and their columns dropped); this only restores the empty fields so the
schema matches the pre-removal state. The insert position is approximate and does not
affect data.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

_ITEM_FIELDS: tuple[dict[str, str | int], ...] = (
    {
        "fieldname": "section_break_6buh1",
        "label": "Thai Tax",
        "fieldtype": "Section Break",
        "insert_after": "item_tax_section_break",
        "is_system_generated": 1,
    },
    {
        "fieldname": "withholding_tax_type",
        "label": "Withholding Tax Type (Customer)",
        "fieldtype": "Link",
        "insert_after": "section_break_6buh1",
        "description": "Select withholding tax type for service amount withheld when recevice from customer.",
        "is_system_generated": 1,
        "options": "Withholding Tax Type",
    },
    {
        "fieldname": "column_break_lhwzh",
        "fieldtype": "Column Break",
        "insert_after": "withholding_tax_type",
        "is_system_generated": 1,
    },
    {
        "fieldname": "withholding_tax_type_pay_supplier",
        "label": "Withholding Tax Type (Supplier)",
        "fieldtype": "Link",
        "insert_after": "column_break_lhwzh",
        "description": "Select withholding tax type for service amount to be withheld when pay to supplier.",
        "is_system_generated": 1,
        "options": "Withholding Tax Type",
    },
    {
        "fieldname": "withholding_tax_type_pay_individual",
        "label": "Withholding Tax Type (Individual)",
        "fieldtype": "Link",
        "insert_after": "withholding_tax_type_pay_supplier",
        "description": "Select withholding tax type for service amount to be withheld when pay to individual.",
        "is_system_generated": 1,
        "options": "Withholding Tax Type",
    },
)

_PURCHASE_INVOICE_ITEM_FIELD: dict[str, str | int] = {
    "fieldname": "withholding_tax_type",
    "label": "Withholding Tax Type",
    "fieldtype": "Link",
    "insert_after": "item_tax_template",
    "description": "Default Withholding Tax Type setup on Item",
    "fetch_from": "item_code.withholding_tax_type_pay_supplier",
    "fetch_if_empty": 1,
    "is_system_generated": 1,
    "options": "Withholding Tax Type",
    "print_hide": 1,
    "read_only": 1,
}

_SALES_INVOICE_ITEM_FIELD: dict[str, str | int] = {
    "fieldname": "withholding_tax_type",
    "label": "Withholding Tax Type",
    "fieldtype": "Link",
    "insert_after": "item_tax_template",
    "description": "Default Withholding Tax Type setup on Item",
    "fetch_from": "item_code.withholding_tax_type",
    "fetch_if_empty": 1,
    "is_system_generated": 1,
    "options": "Withholding Tax Type",
    "print_hide": 1,
    "read_only": 1,
}


def execute() -> None:
    for field in _ITEM_FIELDS:
        _create_if_missing("Item", field)
    _create_if_missing("Purchase Invoice Item", _PURCHASE_INVOICE_ITEM_FIELD)
    _create_if_missing("Sales Invoice Item", _SALES_INVOICE_ITEM_FIELD)
    frappe.db.commit()


def _create_if_missing(doctype: str, field: dict[str, str | int]) -> None:
    if frappe.db.exists("Custom Field", f"{doctype}-{field['fieldname']}"):
        return
    create_custom_field(doctype, field)
