# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Restore Property Setters removed with the retired fixture."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from connect_diagnostics_core.patches.v1_0.remove_obsolete_property_setter_fixture_values import (
    OBSOLETE_PROPERTY_SETTERS,
)


def execute() -> None:
    changed_doctypes: set[str] = set()
    for doctype, fieldname, property_name, value, property_type in OBSOLETE_PROPERTY_SETTERS:
        make_property_setter(
            doctype,
            fieldname,
            property_name,
            value,
            property_type,
            validate_fields_for_doctype=False,
            is_system_generated=False,
        )
        changed_doctypes.add(doctype)

    for doctype in changed_doctypes:
        frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
