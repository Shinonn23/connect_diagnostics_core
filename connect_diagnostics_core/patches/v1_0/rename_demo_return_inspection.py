# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Rename the prototype return inspection DocTypes without losing submitted data."""

from __future__ import annotations

import frappe

RENAMES = (
    ("DocType", "Demo Return Inspection", "Borrowed Asset Return Inspection"),
    ("DocType", "Demo Return Inspection Check", "Borrowed Asset Return Inspection Check"),
    ("Print Format", "Demo Return Inspection", "Borrowed Asset Return Inspection"),
)


def execute() -> None:
    for doctype, old_name, new_name in RENAMES:
        if frappe.db.exists(doctype, old_name) and not frappe.db.exists(doctype, new_name):
            frappe.rename_doc(doctype, old_name, new_name, force=True)
        elif doctype == "Print Format" and frappe.db.exists(doctype, old_name):
            # A previous partial sync may have created the replacement before this
            # patch ran. The old app-owned format is then an obsolete duplicate.
            frappe.delete_doc(doctype, old_name, force=True, ignore_permissions=True)
