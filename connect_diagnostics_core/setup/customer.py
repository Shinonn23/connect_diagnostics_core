# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field / property setter definitions for Customer."""

from __future__ import annotations

from connect_diagnostics_core.setup import quotation as quotation_setup


def _print_configuration_fields() -> list[dict[str, object]]:
    """Build the Customer-side print configuration overrides.

    Per-document settings live in the two child tables, which stay empty while a
    Customer simply inherits its Template. Adding a row overrides that document
    for this Customer only.
    """
    return [
        {
            "fieldname": "print_documents_section",
            "label": "Document Overrides",
            "fieldtype": "Section Break",
            "insert_after": "customer_print_name",
            "description": (
                "Leave empty to inherit every document setting from the selected "
                "Print Configuration Template."
            ),
        },
        {
            "fieldname": "print_documents",
            "label": "Documents",
            "fieldtype": "Table",
            "options": "Print Document Configuration",
            "insert_after": "print_documents_section",
        },
        {
            "fieldname": "print_copies_section",
            "label": "Copy Overrides",
            "fieldtype": "Section Break",
            "insert_after": "print_documents",
        },
        {
            "fieldname": "print_copies",
            "label": "Copies",
            "fieldtype": "Table",
            "options": "Print Copy Configuration",
            "insert_after": "print_copies_section",
        },
        {
            "fieldname": "quotation_print_section",
            "label": "Quotation",
            "fieldtype": "Section Break",
            "insert_after": "print_copies",
        },
        {
            "fieldname": "quotation_signatory_type",
            "label": "Quotation Signatory Type",
            "fieldtype": "Select",
            "options": "\n".join(quotation_setup.SIGNATORY_TYPES),
            "insert_after": "quotation_print_section",
            "default": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
        },
        {
            "fieldname": "quotation_delivery_terms",
            "label": "Quotation Delivery Terms",
            "fieldtype": "Small Text",
            "insert_after": "quotation_signatory_type",
            "description": ("Default delivery commitment copied to each new Quotation for this Customer."),
        },
        {
            "fieldname": "sales_requirements_section",
            "label": "Sales Document Requirements",
            "fieldtype": "Section Break",
            "insert_after": "quotation_delivery_terms",
            "description": (
                "What this Customer requires before a sale can proceed. These are "
                "process rules, not print settings."
            ),
        },
        {
            "fieldname": "quotation_required",
            "label": "Quotation Required Before Sales Order",
            "fieldtype": "Check",
            "insert_after": "sales_requirements_section",
            "default": "0",
            "description": (
                "This Customer only accepts an order that was quoted first. A Sales "
                "Order with no linked Quotation is rejected."
            ),
        },
        {
            "fieldname": "purchase_order_copy_preferences_section",
            "label": "Source Purchase Order Copy",
            "fieldtype": "Section Break",
            "insert_after": "quotation_required",
        },
        {
            "fieldname": "source_purchase_order_copy_required",
            "label": "Source Purchase Order Copy Required",
            "fieldtype": "Check",
            "insert_after": "purchase_order_copy_preferences_section",
            "default": "0",
            "description": (
                "This Customer requires a copy of the Purchase Order we placed with "
                "our supplier, to confirm the origin of the products sold."
            ),
        },
        {
            "fieldname": "purchase_order_copy_count",
            "label": "Copy Count",
            "fieldtype": "Int",
            "insert_after": "source_purchase_order_copy_required",
            "default": "1",
            "non_negative": 1,
            "depends_on": "eval:doc.source_purchase_order_copy_required",
        },
    ]


CUSTOM_FIELDS = {
    "Customer": [
        {
            "fieldname": "customer_code",
            "label": "Customer Code",
            "fieldtype": "Data",
            "insert_after": "customer_name",
            "reqd": 1,
            "bold": 1,
            "in_global_search": 1,
            "search_index": 1,
            "unique": 1,
            "description": (
                "Manual ERPNext Customer ID. It can be corrected until the Customer has "
                "its first quotation, order, invoice, or delivery note."
            ),
        },
        {
            "fieldname": "branch_code",
            "label": "Branch Code",
            "fieldtype": "Data",
            "insert_after": "tax_id",
            "default": "00000",
            "is_system_generated": 1,
        },
        {
            "fieldname": "source_dksh_customer",
            "label": "Source DKSH Customer",
            "fieldtype": "Link",
            "options": "DKSH Customer",
            "insert_after": "customer_code",
            "read_only": 1,
            "no_copy": 1,
            "description": (
                "The DKSH Customer this Customer was converted from. Set automatically "
                "by Convert to CD Customer."
            ),
        },
        {
            "fieldname": "document_preferences_section",
            "label": "Document / Print Configuration",
            "fieldtype": "Tab Break",
            "insert_after": "portal_users",
        },
        {
            "fieldname": "print_configuration_template",
            "label": "Print Configuration Template",
            "fieldtype": "Link",
            "options": "Print Configuration Template",
            "insert_after": "document_preferences_section",
        },
        {
            "fieldname": "customer_print_name",
            "label": "Customer Print Name",
            "fieldtype": "Data",
            "insert_after": "print_configuration_template",
            "description": "Default customer name used only on printed documents.",
        },
        *_print_configuration_fields(),
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Customer": [
        ("customer_type", "options", "Company\nIndividual\nPartnership\nPublic Company Limited", "Text"),
        (
            "gender",
            "depends_on",
            "eval:!['Company','Public Company Limited'].includes(doc.customer_type)",
            "Data",
        ),
        (None, "customer_type", "Company\nIndividual\nPartnership\nPublic Company Limited", "options"),
        (None, "quick_entry", "0", "Check"),
        ("naming_series", "default", "", "Text"),
        (
            "naming_series",
            "description",
            "Customer Code is entered manually.",
            "Text",
        ),
        ("naming_series", "hidden", "1", "Check"),
        ("naming_series", "options", "", "Text"),
        (
            "salutation",
            "depends_on",
            "eval:!['Company','Public Company Limited'].includes(doc.customer_type)",
            "Data",
        ),
    ],
}
