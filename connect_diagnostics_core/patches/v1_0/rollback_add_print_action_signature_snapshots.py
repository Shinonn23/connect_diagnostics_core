# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, see license.txt

"""Rollback the workflow action signature snapshot fields."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.setup.print_action_fields import PRINT_ACTIONS

NEW_FIELDS = {}
for doctype, actions in PRINT_ACTIONS.items():
    fieldnames = {action.signature_field for action in actions}
    for action in actions:
        if action.key == "submit" or (doctype == "Purchase Receipt" and action.key == "authorized"):
            fieldnames.update({action.employee_field, action.datetime_field})
    NEW_FIELDS[doctype] = fieldnames


def execute() -> None:
    """Remove only fields introduced by the matching forward patch."""
    for doctype, fieldnames in NEW_FIELDS.items():
        for fieldname in fieldnames:
            custom_field = f"{doctype}-{fieldname}"
            if frappe.db.exists("Custom Field", custom_field):
                frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)
            if frappe.db.has_column(doctype, fieldname):
                frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")

    frappe.db.commit()
