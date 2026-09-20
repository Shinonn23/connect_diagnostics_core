# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the withholding-tax-type Custom Fields from Item, Purchase Invoice Item, and
Sales Invoice Item.

Their declarations were already dropped from setup/item.py, setup/purchase_invoice_item.py,
and setup/sales_invoice_item.py; this patch removes the matching Custom Field records (and
their columns) from any site that already had them installed. Idempotent.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old

_FIELDS: tuple[tuple[str, str], ...] = (
    ("Item", "withholding_tax_type"),
    ("Item", "withholding_tax_type_pay_supplier"),
    ("Item", "withholding_tax_type_pay_individual"),
    ("Item", "section_break_6buh1"),
    ("Item", "column_break_lhwzh"),
    ("Purchase Invoice Item", "withholding_tax_type"),
    ("Sales Invoice Item", "withholding_tax_type"),
)


def execute() -> None:
    for doctype, field in _FIELDS:
        _drop_old(doctype, field)
    frappe.db.commit()
