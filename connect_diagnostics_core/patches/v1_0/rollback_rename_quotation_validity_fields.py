# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for rename_quotation_validity_fields.

Recreates the old fields (definitions inlined as they were before the
rename), copies data back from the renamed columns, then removes the renamed
Custom Fields / columns. Run manually via ``bench execute`` together with
reverting the code change -- otherwise ``after_migrate`` recreates the new
names from ``connect_diagnostics_core/setup``.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.patches.v1_0.rename_quotation_validity_fields import RENAMES
from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ident,
)

OLD_DEFS: dict[str, list[dict[str, str | int]]] = {
    "Quotation": [
        {
            "fieldname": "override_quotation_validity_text",
            "label": "Override validity text",
            "fieldtype": "Check",
            "insert_after": "valid_till",
            "description": "Use custom text instead of the Valid Till date.",
        },
        {
            "fieldname": "quotation_custom_validity_text",
            "label": "Quotation Custom Validity Text",
            "fieldtype": "Small Text",
            "insert_after": "override_quotation_validity_text",
            "depends_on": "eval:doc.override_quotation_validity_text",
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
