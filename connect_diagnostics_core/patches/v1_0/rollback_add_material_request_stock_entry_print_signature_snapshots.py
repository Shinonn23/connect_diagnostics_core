# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback material request and stock entry print-action snapshot fields."""

from __future__ import annotations

import frappe

NEW_FIELDS = {
    "Material Request": (
        "submit_by",
        "submit_at",
        "submit_signature",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ),
    "Stock Entry": (
        "submit_by",
        "submit_at",
        "submit_signature",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ),
}


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
