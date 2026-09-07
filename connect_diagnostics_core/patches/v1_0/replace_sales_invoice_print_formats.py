# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Replace retired Sales Invoice Print Format names with Thai fixtures."""

from __future__ import annotations

from typing import Any

import frappe

FORMAT_REPLACEMENTS = {
    # Keep aliases for both the retired English names and the previous Thai
    # slug-style names so existing Property Setters/Print Format rows migrate.
    "Tax Invoice Delivery Note and Invoice": "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
    "Abbreviated Tax Invoice And Receipt": "ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ",
    "ใบกำกับภาษี-ใบแจ้งหนี้-ใบส่งของ": "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
    "ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ": "ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ",
    "ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ": "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ",
}
PRINT_FORMAT_FIXTURES = (
    "ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ",
    "ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ",
    "ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ",
)


def execute() -> None:
    """Install replacement fixtures, repoint defaults, and remove retired records."""
    for fixture in PRINT_FORMAT_FIXTURES:
        frappe.reload_doc("Connect Diagnostics Print", "print_format", fixture, force=True)
    _replace_default_format_references()
    _remove_retired_print_formats()
    frappe.clear_cache(doctype="Sales Invoice")


def _replace_default_format_references() -> None:
    property_setters: list[dict[str, Any]] = frappe.get_all(
        "Property Setter",
        filters={
            "property": "default_print_format",
            "value": ["in", tuple(FORMAT_REPLACEMENTS)],
        },
        fields=["name", "value"],
    )
    for property_setter in property_setters:
        frappe.db.set_value(
            "Property Setter",
            property_setter["name"],
            "value",
            FORMAT_REPLACEMENTS[property_setter["value"]],
            update_modified=False,
        )


def _remove_retired_print_formats() -> None:
    for print_format in FORMAT_REPLACEMENTS:
        if frappe.db.exists("Print Format", print_format):
            frappe.delete_doc("Print Format", print_format, force=True, ignore_missing=True)
