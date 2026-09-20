# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove obsolete Property Setters formerly distributed through fixtures."""

from __future__ import annotations

import frappe

LEGACY_NAMING_SERIES = {
    "Closing Stock Balance": "CSB.YY-BE.MM.####",
    "Driver": "DV.YY-BE.MM.####",
    "Journal Entry Template": "JVT.YY-BE.MM.####",
    "Petty Cash Holder": "PCH.YY-BE.MM.####",
    "Pricing Rule": "PCR.YY-BE.MM.####",
    "Serial and Batch Bundle": "SBB.YY-BE.MM.####",
    "Shareholder": "SH.YY-BE.MM.####",
}

# doctype, fieldname, property, value, property_type
OBSOLETE_PROPERTY_SETTERS: tuple[tuple[str, str, str, str, str], ...] = (
    *(
        (doctype, "naming_series", property_name, value, "Text")
        for doctype, value in LEGACY_NAMING_SERIES.items()
        for property_name in ("default", "options")
    ),
    ("Purchase Order Item", "required_by", "in_list_view", "0", "Check"),
)


def execute() -> None:
    changed_doctypes: set[str] = set()
    for doctype, fieldname, property_name, value, _property_type in OBSOLETE_PROPERTY_SETTERS:
        property_setter = frappe.db.exists(
            "Property Setter",
            {
                "doc_type": doctype,
                "field_name": fieldname,
                "property": property_name,
                "value": value,
            },
        )
        if not property_setter:
            continue
        frappe.delete_doc(
            "Property Setter",
            property_setter,
            ignore_permissions=True,
            force=True,
        )
        changed_doctypes.add(doctype)

    for doctype in changed_doctypes:
        frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
