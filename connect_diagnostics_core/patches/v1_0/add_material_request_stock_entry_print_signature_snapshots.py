# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Add print-action snapshot fields for material issue documents."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.print_action_fields import CUSTOM_FIELDS

NEW_PRINT_SIGNATURE_FIELDS = {
    "Stock Entry": CUSTOM_FIELDS["Stock Entry"],
}


def execute() -> None:
    """Create the hidden action fields on existing sites idempotently."""
    create_custom_fields(NEW_PRINT_SIGNATURE_FIELDS, update=True, ignore_validate=True)
