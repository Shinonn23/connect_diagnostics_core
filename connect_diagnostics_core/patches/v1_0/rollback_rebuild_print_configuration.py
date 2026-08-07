# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reverse ``rebuild_print_configuration``.

Returns the print records to ``Connect Diagnostics Core`` and removes the child
tables the rebuild introduced. The retired flat Customer fields are **not**
recreated: they were dropped deliberately before go-live and their values are
gone, so restoring empty columns would be misleading rather than a real undo.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

from connect_diagnostics_core.patches.v1_0.rebuild_print_configuration import (
    MOVED_DOCTYPES,
    PRINT_FORMATS,
)

CORE_MODULE = "Connect Diagnostics Core"

INTRODUCED_CUSTOMER_FIELDS = (
    "print_documents_section",
    "print_documents",
    "print_copies_section",
    "print_copies",
)

INTRODUCED_DOCTYPES = (
    "Print Document Configuration",
    "Print Copy Configuration",
    "Print Log",
)


def execute() -> None:
    """Point the print records back at the core module and drop the new tables."""
    for print_format in PRINT_FORMATS:
        if frappe.db.exists("Print Format", print_format):
            frappe.db.set_value("Print Format", print_format, "module", CORE_MODULE)

    for doctype in MOVED_DOCTYPES:
        if doctype in INTRODUCED_DOCTYPES:
            continue
        if frappe.db.exists("DocType", doctype):
            frappe.db.set_value("DocType", doctype, "module", CORE_MODULE)

    delete_custom_fields({"Customer": list(INTRODUCED_CUSTOMER_FIELDS)}, bypass_hooks=True)

    for child_doctype in ("Print Document Configuration", "Print Copy Configuration"):
        if frappe.db.exists("DocType", child_doctype):
            frappe.db.delete(child_doctype)

    for doctype in INTRODUCED_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)

    frappe.clear_cache()
