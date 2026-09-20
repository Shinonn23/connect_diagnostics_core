# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Restore fields required by ERPNext Thailand's Payment Entry withholding flow.

The earlier removal patch treated these fields as unused, but ERPNext Thailand
reads them directly while deciding whether a Payment Entry needs withholding
tax and while deriving withholding rows from invoice items.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import item, purchase_invoice_item, sales_invoice_item

THAI_WITHHOLDING_FIELDNAMES: dict[str, tuple[str, ...]] = {
    "Item": (
        "section_break_6buh1",
        "withholding_tax_type",
        "column_break_lhwzh",
        "withholding_tax_type_pay_supplier",
        "withholding_tax_type_pay_individual",
    ),
    "Purchase Invoice Item": ("withholding_tax_type",),
    "Sales Invoice Item": ("withholding_tax_type",),
}

_SETUP_FIELDS = {
    "Item": item.CUSTOM_FIELDS["Item"],
    "Purchase Invoice Item": purchase_invoice_item.CUSTOM_FIELDS["Purchase Invoice Item"],
    "Sales Invoice Item": sales_invoice_item.CUSTOM_FIELDS["Sales Invoice Item"],
}

THAI_WITHHOLDING_CUSTOM_FIELDS = {
    doctype: [
        field
        for field in _SETUP_FIELDS[doctype]
        if field["fieldname"] in THAI_WITHHOLDING_FIELDNAMES[doctype]
    ]
    for doctype in THAI_WITHHOLDING_FIELDNAMES
}


def execute() -> None:
    """Recreate the dependency fields idempotently; removed values remain unrecoverable."""
    create_custom_fields(THAI_WITHHOLDING_CUSTOM_FIELDS, update=True, ignore_validate=True)
    frappe.clear_cache()
