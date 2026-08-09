# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Drop the ``cd_`` prefix from the app's custom fields.

Field names must describe the data they hold; the ``cd_`` prefix added no
meaning. The definitions in ``connect_diagnostics_core/setup`` now use the
stripped names (e.g. ``cd_print_date`` -> ``print_date``). This patch migrates
an upgrading site: it creates the new field, copies the old column's data
across, then removes the old Custom Field / column. Layout fields (Section
Break, Tab Break, HTML) have no column, so only their Custom Field record is
replaced.

Idempotent and a no-op on fresh installs (the old fields never exist there;
``after_install`` creates the stripped names directly).
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ensure_new_field,
    _field_def,
    _ident,
)

# (doctype, old fieldname, new fieldname) — ordered so each insert_after target
# already exists when the field is created.
RENAMES: list[tuple[str, str, str]] = [
    ("Customer", "cd_document_preferences_section", "document_preferences_section"),
    ("Customer", "cd_use_quotation", "use_quotation"),
    ("Customer", "cd_use_customer_po", "use_customer_po"),
    ("Customer", "cd_use_tax_invoice", "use_tax_invoice"),
    ("Customer", "cd_use_receipt", "use_receipt"),
    ("Customer", "cd_use_abbreviated_tax_invoice", "use_abbreviated_tax_invoice"),
    ("Customer", "cd_print_date", "print_date"),
    ("Delivery Note", "cd_serial_no_summary_section", "serial_no_summary_section"),
    ("Delivery Note", "cd_serial_no_summary", "serial_no_summary"),
    ("Item", "cd_product_group", "product_group"),
]


def execute() -> None:
    for doctype, old, new in RENAMES:
        _ensure_new_field(doctype, new, _field_def(doctype, new))

        if frappe.db.has_column(doctype, old) and frappe.db.has_column(doctype, new):
            table = frappe.qb.DocType(_ident(doctype))
            new_col, old_col = _ident(new), _ident(old)
            frappe.qb.update(table).set(table[new_col], table[old_col]).where(
                table[old_col].isnotnull()
            ).run()

        _drop_old(doctype, old)

    frappe.db.commit()
