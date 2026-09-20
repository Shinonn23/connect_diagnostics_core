# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove legacy requester/checked MR print snapshots after site backup."""

from __future__ import annotations

import frappe

REMOVED_FIELDS = (
    ("submit_by", "Link", "Employee"),
    ("submit_at", "Datetime", None),
    ("submit_signature", "Signature", None),
    ("checked_by", "Link", "Employee"),
    ("checked_at", "Datetime", None),
    ("checked_signature", "Signature", None),
)


def execute() -> None:
    for fieldname, _fieldtype, _options in REMOVED_FIELDS:
        custom_field = f"Material Request-{fieldname}"
        if frappe.db.exists("Custom Field", custom_field):
            frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)
        if frappe.db.has_column("Material Request", fieldname):
            frappe.db.sql_ddl(f"ALTER TABLE `tabMaterial Request` DROP COLUMN `{fieldname}`")
    frappe.db.commit()
