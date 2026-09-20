# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rename Quotation's validity-override fields to match their new Desk UX.

``override_quotation_validity_text`` -> ``edit_validity_text`` and
``quotation_custom_validity_text`` -> ``validity_text``: the custom text field
is now always visible and shown read-only with a computed preview when the
checkbox is unchecked, so the names needed to describe that behavior instead
of the old "override" framing. This patch migrates an upgrading site: it
creates the new field, copies the old column's data across, then removes the
old Custom Field / column.

Idempotent and a no-op on fresh installs (the old fields never exist there;
``after_install`` creates the new names directly).
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ensure_new_field,
    _field_def,
    _ident,
)

QUOTATION = "Quotation"
# (doctype, old fieldname, new fieldname) — ordered so each insert_after
# target already exists when the field is created.
RENAMES: list[tuple[str, str, str]] = [
    (QUOTATION, "override_quotation_validity_text", "edit_validity_text"),
    (QUOTATION, "quotation_custom_validity_text", "validity_text"),
]


def execute() -> None:
    for doctype, old, new in RENAMES:
        if not frappe.db.has_column(doctype, old):
            continue  # fresh install or already migrated

        field_def = _field_def(doctype, new)
        if field_def is None:
            _drop_old(doctype, old)
            continue

        _ensure_new_field(doctype, new, field_def)
        table = frappe.qb.DocType(_ident(doctype))
        new_col, old_col = _ident(new), _ident(old)
        frappe.qb.update(table).set(table[new_col], table[old_col]).where(table[old_col].isnotnull()).run()
        _drop_old(doctype, old)

    frappe.db.commit()
