# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_legacy_print_formats — restore the default_print_format links.

The deleted legacy ``Print Format`` documents themselves cannot be recreated
(their JSON definitions were removed from the codebase in the same change);
this only points ``default_print_format`` Property Setters back at the
legacy names so the schema matches the pre-removal state.
"""

import frappe

from connect_diagnostics_core.patches.v1_0.remove_legacy_print_formats import (
    DEFAULT_PRINT_FORMAT_RENAMES,
)

LEGACY_PRINT_FORMAT_NAMES = {new: old for old, new in DEFAULT_PRINT_FORMAT_RENAMES.items()}


def execute() -> None:
    property_setters = frappe.get_all(
        "Property Setter",
        filters={
            "property": "default_print_format",
            "value": ["in", tuple(LEGACY_PRINT_FORMAT_NAMES)],
        },
        fields=["name", "doc_type", "value"],
    )

    changed_doctypes = set()
    for property_setter in property_setters:
        frappe.db.set_value(
            "Property Setter",
            property_setter["name"],
            "value",
            LEGACY_PRINT_FORMAT_NAMES[property_setter["value"]],
            update_modified=False,
        )
        if property_setter.get("doc_type"):
            changed_doctypes.add(property_setter["doc_type"])

    for doctype in changed_doctypes:
        frappe.clear_cache(doctype=doctype)

    frappe.db.commit()
