# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_cd_prefix_from_custom_fields.

Recreates the ``cd_``-prefixed Custom Fields (definitions inlined as they were
before the rename), copies data back from the renamed columns, then removes the
renamed Custom Fields / columns. Run manually via ``bench execute`` together
with reverting the code change — otherwise ``after_migrate`` recreates the
stripped fields from ``connect_diagnostics_core/setup``.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.patches.v1_0.remove_cd_prefix_from_custom_fields import RENAMES
from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ident,
)

OLD_DEFS: dict[str, list[dict[str, str | int]]] = {
    "Customer": [
        {
            "fieldname": "cd_document_preferences_section",
            "label": "Document / Print Preferences",
            "fieldtype": "Section Break",
            "insert_after": "customer_code",
        },
        {
            "fieldname": "cd_use_quotation",
            "label": "ใบเสนอราคา (Quotation)",
            "fieldtype": "Check",
            "insert_after": "cd_document_preferences_section",
            "default": "0",
        },
        {
            "fieldname": "cd_use_customer_po",
            "label": "PO",
            "fieldtype": "Check",
            "insert_after": "cd_use_quotation",
            "default": "0",
        },
        {
            "fieldname": "cd_use_tax_invoice",
            "label": "ต้นฉบับใบกำกับภาษี/ใบส่งของ/ใบแจ้งหนี้",
            "fieldtype": "Check",
            "insert_after": "cd_use_customer_po",
            "default": "0",
        },
        {
            "fieldname": "cd_use_receipt",
            "label": "ต้นฉบับใบเสร็จรับเงิน",
            "fieldtype": "Check",
            "insert_after": "cd_use_tax_invoice",
            "default": "0",
        },
        {
            "fieldname": "cd_use_abbreviated_tax_invoice",
            "label": "ใบเสร็จรับเงิน/ใบกำกับภาษีอย่างย่อ",
            "fieldtype": "Check",
            "insert_after": "cd_use_receipt",
            "default": "0",
        },
        {
            "fieldname": "cd_print_date",
            "label": "ลงวันที่ในเอกสาร (Print Date)",
            "fieldtype": "Check",
            "insert_after": "cd_use_abbreviated_tax_invoice",
            "default": "1",
            "description": "When ticked, printed documents show the document date. Untick for customers who use pre-printed forms where the date is filled in by hand.",
        },
    ],
    "Delivery Note": [
        {
            "fieldname": "cd_serial_no_summary_section",
            "label": "Serial No Verification",
            "fieldtype": "Section Break",
            "insert_after": "items",
            "is_system_generated": 1,
        },
        {
            "fieldname": "cd_serial_no_summary",
            "label": "Serial No Summary",
            "fieldtype": "HTML",
            "options": "",
            "insert_after": "cd_serial_no_summary_section",
            "description": "Read-only overview of serial numbers per item, for quick verification.",
            "is_system_generated": 1,
        },
    ],
    "Item": [
        {
            "fieldname": "cd_product_group",
            "label": "Product Group",
            "fieldtype": "Link",
            "insert_after": "item_group",
            "options": "Product Group",
        },
    ],
}


def execute() -> None:
    create_custom_fields(OLD_DEFS, ignore_validate=True)

    for doctype, old, new in RENAMES:
        if frappe.db.has_column(doctype, old) and frappe.db.has_column(doctype, new):
            table = frappe.qb.DocType(_ident(doctype))
            new_col, old_col = _ident(new), _ident(old)
            frappe.qb.update(table).set(table[old_col], table[new_col]).where(
                table[new_col].isnotnull()
            ).run()

        _drop_old(doctype, new)

    frappe.db.commit()
