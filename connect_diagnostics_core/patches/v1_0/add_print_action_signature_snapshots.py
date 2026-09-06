# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, see license.txt

"""Add workflow action signature snapshot fields to transaction documents."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.print_action_fields import CUSTOM_FIELDS


def execute() -> None:
    """Create the code-managed action fields on existing sites."""
    create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
