# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Replace the legacy Quotation validity selector with an explicit override."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

from connect_diagnostics_core.setup import customer

LEGACY_VALIDITY_MODE_FIELD = "quotation_validity_mode"
CUSTOM_VALIDITY_MODE = "Custom Text"
OVERRIDE_VALIDITY_TEXT_FIELD = "override_quotation_validity_text"


def execute() -> None:
    """Preserve custom validity choices before retiring the Customer selector."""
    create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True)
    _migrate_custom_validity_overrides("Customer")
    _migrate_custom_validity_overrides("Print Configuration Template")
    delete_custom_fields({"Customer": [LEGACY_VALIDITY_MODE_FIELD]}, bypass_hooks=True)
    frappe.clear_cache()


def _migrate_custom_validity_overrides(doctype: str) -> None:
    if not (
        frappe.db.has_column(doctype, LEGACY_VALIDITY_MODE_FIELD)
        and frappe.db.has_column(doctype, OVERRIDE_VALIDITY_TEXT_FIELD)
    ):
        return

    table = frappe.qb.DocType(doctype)
    rows = cast(
        list[dict[str, Any]],
        frappe.qb.from_(table)
        .select(table.name)
        .where(table[LEGACY_VALIDITY_MODE_FIELD] == CUSTOM_VALIDITY_MODE)
        .run(as_dict=True),
    )
    updates = {cast(str, row["name"]): {OVERRIDE_VALIDITY_TEXT_FIELD: 1} for row in rows}
    if updates:
        frappe.db.bulk_update(doctype, updates, update_modified=False)
