# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire the obsolete, site-configured DKSH Sales Settings Single DocType."""

from __future__ import annotations

import frappe

DKSH_SALES_SETTINGS_DOCTYPE = "DKSH Sales Settings"


def execute() -> None:
    """Remove the retired metadata and Single values safely on every site."""
    if frappe.db.exists("DocType", DKSH_SALES_SETTINGS_DOCTYPE):
        frappe.delete_doc(
            "DocType",
            DKSH_SALES_SETTINGS_DOCTYPE,
            force=True,
            ignore_missing=True,
        )
    frappe.db.delete("Singles", {"doctype": DKSH_SALES_SETTINGS_DOCTYPE})
    frappe.clear_cache()
