# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Drop the removed Customer print-configuration and source-PO schema.

The per-Customer print configuration (``Print Configuration Template`` and the
Customer "Print" tab) and the source-Purchase-Order-copy feature were removed:
print options are now chosen per print in the print sidebar. This patch deletes
their custom fields and DocTypes from sites that still carry them. Each delete is
guarded by existence, so the patch is idempotent and safe to re-run.
"""

from __future__ import annotations

import frappe

CUSTOM_FIELDS = {
    "Customer": (
        "print_configuration_template",
        "customer_print_name",
        "document_preferences_section",
        "print_documents_section",
        "print_documents",
        "print_copies_section",
        "print_copies",
        "quotation_print_section",
        "quotation_signatory_type",
        "quotation_delivery_terms",
        "purchase_order_copy_preferences_section",
        "source_purchase_order_copy_required",
        "purchase_order_copy_count",
    ),
    "Sales Invoice": (
        "source_purchase_order_section",
        "source_purchase_orders",
        "requirement_override_reason",
    ),
}

DOCTYPES = (
    "Print Configuration Template",
    "Print Document Configuration",
    "Print Copy Configuration",
    "Sales Invoice Source Purchase Order",
)


def execute() -> None:
    for doctype, fieldnames in CUSTOM_FIELDS.items():
        for fieldname in fieldnames:
            name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
            if name:
                frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

    for doctype in DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)
