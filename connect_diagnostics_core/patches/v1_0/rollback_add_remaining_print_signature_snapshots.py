# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback fields added for the remaining app-owned signature print formats."""

from __future__ import annotations

import frappe

NEW_FIELDS = {
    "Quotation": ("signatory_by", "signatory_at", "signatory_signature"),
    "Withholding Tax Cert": ("signed_by", "signed_at", "signed_signature"),
}


def execute() -> None:
    """Remove only the fields introduced by the matching forward patch."""
    for doctype, fieldnames in NEW_FIELDS.items():
        for fieldname in fieldnames:
            custom_field = f"{doctype}-{fieldname}"
            if frappe.db.exists("Custom Field", custom_field):
                frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)
            if frappe.db.has_column(doctype, fieldname):
                frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")

    frappe.db.commit()
