# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from connect_diagnostics_core.setup import procure_to_pay


def execute() -> None:
    for doctype, fields in procure_to_pay.CUSTOM_FIELDS.items():
        for field in fields:
            custom_field = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]})
            if custom_field:
                frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)
    frappe.clear_cache()
