# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Add snapshot fields for the remaining app-owned signature print formats."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.print_action_fields import CUSTOM_FIELDS

NEW_PRINT_SIGNATURE_FIELDS = {
    doctype: CUSTOM_FIELDS[doctype] for doctype in ("Quotation", "Withholding Tax Cert")
}


def execute() -> None:
    """Create the Quotation and WHT signature action fields idempotently."""
    create_custom_fields(NEW_PRINT_SIGNATURE_FIELDS, update=True, ignore_validate=True)
