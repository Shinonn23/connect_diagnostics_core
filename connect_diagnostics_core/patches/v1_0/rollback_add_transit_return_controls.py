# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Remove only the custom fields introduced by add_transit_return_controls."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.add_transit_return_controls import NEW_FIELDS


def execute() -> None:
    for doctype, fields in NEW_FIELDS.items():
        for field in fields:
            fieldname = str(field["fieldname"])
            custom_field = f"{doctype}-{fieldname}"
            if frappe.db.exists("Custom Field", custom_field):
                frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)
            if frappe.db.has_column(doctype, fieldname):
                frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")
    frappe.db.commit()
