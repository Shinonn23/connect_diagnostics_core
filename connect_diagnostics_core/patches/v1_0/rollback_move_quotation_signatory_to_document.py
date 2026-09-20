# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reverse ``move_quotation_signatory_to_document``.

Recreates the retired Company, Quotation, and Customer fields and removes the
ones the move introduced. Values are **not** restored: deleting a Custom Field
drops its column, so the Customer-level validity wording and the authorized
signatory Employee links are gone. Only the schema is undone, matching
``rollback_rebuild_print_configuration``.

Idempotent: recreating an existing Custom Field and deleting a missing one are
both no-ops on a second run.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

RESTORED_FIELDS = {
    "Company": [
        {
            "fieldname": "quotation_authorized_signatory_employee",
            "label": "Quotation Authorized Signatory Employee",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "default_sales_contact",
            "description": (
                "Employee whose name, designation, and mobile number are printed when "
                "Managing Director is selected as the Quotation signatory."
            ),
        },
    ],
    "Quotation": [
        {
            "fieldname": "quotation_authorized_signatory_employee",
            "label": "Quotation Authorized Signatory Employee",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "quotation_signatory_type",
            "depends_on": "eval:doc.quotation_signatory_type == 'Managing Director'",
            "description": "Override employee for Managing Director signatory. Defaults from Company.",
        },
    ],
    "Customer": [
        {
            "fieldname": "override_quotation_validity_text",
            "label": "Override validity text",
            "fieldtype": "Check",
            "insert_after": "quotation_signatory_type",
            "description": "Use custom text instead of the Quotation Valid Till date.",
        },
        {
            "fieldname": "quotation_custom_validity_text",
            "label": "Quotation Custom Validity Text",
            "fieldtype": "Small Text",
            "insert_after": "override_quotation_validity_text",
            "depends_on": "eval:doc.override_quotation_validity_text",
        },
    ],
}

INTRODUCED_FIELDS = {
    "Quotation": [
        "sales_representative_employee",
        "override_quotation_validity_text",
        "quotation_custom_validity_text",
    ],
}


def execute() -> None:
    """Restore the retired fields and drop the ones the move introduced."""
    create_custom_fields(RESTORED_FIELDS, ignore_validate=True)
    delete_custom_fields(INTRODUCED_FIELDS, bypass_hooks=True)
    frappe.clear_cache()
