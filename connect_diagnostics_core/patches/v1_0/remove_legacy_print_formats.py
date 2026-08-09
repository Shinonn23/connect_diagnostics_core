# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove obsolete Connect Diagnostics print formats.

Deleting print format JSON files from the app does not remove existing
``Print Format`` records from installed sites. This patch removes the old CD
formats so they are not left behind after migration.
"""

import frappe

LEGACY_PRINT_FORMATS = (
    "CD Abbreviated Tax Invoice Print",
    "CD Payment Voucher Print",
    "CD Purchase Order Print",
    "CD Quotation Print",
    "CD Receipt Voucher Print",
    "CD Sales Invoice Print",
    "CD Sales Order Print",
    "CD Withholding Tax Cert Image Print",
    "CD DIRUI PM Checklist",
    "CD GPP100 PM Checklist",
    "CD I20 PM Checklist",
    "CD OMRON PM Checklist",
    "CD TD2300 PM Checklist",
    "CD ZYBIO Z5 PM Checklist",
)
DEFAULT_PRINT_FORMAT_RENAMES = {
    "CD Abbreviated Tax Invoice Print": "Abbreviated Tax Invoice And Receipt",
    "CD Purchase Order Print": "Purchase Order",
    "CD Quotation Print": "Quotation",
    "CD Receipt Voucher Print": "Receipt",
    "CD Sales Invoice Print": "Sales Invoice Print",
    "CD Sales Order Print": "Sales Order",
    "CD Withholding Tax Cert Image Print": "Withholding Tax Cert",
}


def execute() -> None:
    _rename_default_print_formats()
    _delete_legacy_print_formats()
    frappe.clear_cache()
    frappe.db.commit()


def _rename_default_print_formats() -> None:
    property_setters = frappe.get_all(
        "Property Setter",
        filters={
            "property": "default_print_format",
            "value": ["in", tuple(DEFAULT_PRINT_FORMAT_RENAMES)],
        },
        fields=["name", "doc_type", "value"],
    )

    changed_doctypes = set()
    for property_setter in property_setters:
        frappe.db.set_value(
            "Property Setter",
            property_setter["name"],
            "value",
            DEFAULT_PRINT_FORMAT_RENAMES[property_setter["value"]],
            update_modified=False,
        )
        if property_setter.get("doc_type"):
            changed_doctypes.add(property_setter["doc_type"])

    for doctype in changed_doctypes:
        frappe.clear_cache(doctype=doctype)


def _delete_legacy_print_formats() -> None:
    for print_format in LEGACY_PRINT_FORMATS:
        if frappe.db.exists("Print Format", print_format):
            frappe.delete_doc(
                "Print Format",
                print_format,
                force=True,
                ignore_missing=True,
            )
