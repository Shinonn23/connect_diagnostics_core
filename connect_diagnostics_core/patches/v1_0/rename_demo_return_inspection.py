# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Rename the prototype return inspection DocTypes without losing submitted data."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc

RENAMES = (
    ("DocType", "Demo Return Inspection", "Borrowed Asset Return Inspection"),
    ("DocType", "Demo Return Inspection Check", "Borrowed Asset Return Inspection Check"),
    ("Print Format", "Demo Return Inspection", "Borrowed Asset Return Inspection"),
)

DOCTYPE_RENAMES = RENAMES[:2]


def _drop_empty_synced_target(doctype: str) -> None:
    """Remove an empty target created by a partial model sync before renaming the source."""
    table_exists = frappe.db.table_exists(doctype)
    if table_exists and frappe.db.count(doctype):
        frappe.throw(
            _(
                "Cannot migrate {0}: the replacement table already contains data. "
                "Restore the backup and reconcile the duplicate DocTypes before migrating."
            ).format(doctype)
        )
    frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
    if table_exists:
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def execute() -> None:
    for doctype, old_name, new_name in DOCTYPE_RENAMES:
        old_exists = frappe.db.exists(doctype, old_name)
        new_exists = frappe.db.exists(doctype, new_name)
        if old_exists and new_exists:
            _drop_empty_synced_target(new_name)
            new_exists = False
        if old_exists and not new_exists:
            rename_doc(doctype, old_name, new_name, force=True, ignore_permissions=True)

    if frappe.db.exists("Print Format", "Demo Return Inspection"):
        # A previous partial sync may have created the replacement before this
        # patch ran. The old app-owned format is then an obsolete duplicate.
        frappe.delete_doc("Print Format", "Demo Return Inspection", force=True, ignore_permissions=True)
