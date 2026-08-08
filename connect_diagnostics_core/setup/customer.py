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
        {
            "fieldname": "legacy_print_preferences_section",
            "label": "Legacy Print Behavior",
            "fieldtype": "Section Break",
            "insert_after": "purchase_order_copy_count",
            "collapsible": 1,
        },
        {
            "fieldname": "print_date",
            "label": "Legacy Global Print Date (Current Print Formats)",
            "fieldtype": "Check",
            "insert_after": "legacy_print_preferences_section",
            "default": "1",
            "description": (
                "Read directly by the Sales Order Print Format, which has no "
                "Customer print configuration of its own."
            ),
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
            "read_only_depends_on": "eval:doc.customer_onboarding_state=='Customer Active'",
            "description": "Manual ERPNext Customer ID. It cannot be changed after activation.",
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
            "fieldname": "customer_onboarding_section",
            "label": "Customer Onboarding",
            "fieldtype": "Tab Break",
            "insert_after": "portal_users",
        },
        {
            "fieldname": "customer_onboarding_state",
            "label": "Customer Onboarding State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "insert_after": "customer_onboarding_section",
            "read_only": 1,
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "correction_reason",
            "label": "Correction Reason",
            "fieldtype": "Small Text",
            "insert_after": "customer_onboarding_state",
            "no_copy": 1,
            "description": "The reviewer must save this reason before choosing Return for correction. It is cleared when Sales sends the Customer for duplicate verification again.",
        },
        {
            "fieldname": "readiness_section",
            "label": "Document Readiness",
            "fieldtype": "Section Break",
            "insert_after": "correction_reason",
        },
        {
            "fieldname": "quotation_readiness",
            "label": "Quotation Readiness",
            "fieldtype": "Select",
            "options": "Ready\nMissing information\nNot applicable",
            "insert_after": "readiness_section",
            "read_only": 1,
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "delivery_readiness",
            "label": "Delivery Readiness",
            "fieldtype": "Select",
            "options": "Ready\nMissing information\nNot applicable",
            "insert_after": "quotation_readiness",
            "read_only": 1,
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "tax_invoice_readiness",
            "label": "Tax Invoice Readiness",
            "fieldtype": "Select",
            "options": "Ready\nMissing information\nNot applicable",
            "insert_after": "delivery_readiness",
            "read_only": 1,
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "email_readiness",
            "label": "Email Readiness",
            "fieldtype": "Select",
            "options": "Ready\nMissing information\nNot applicable",
            "insert_after": "tax_invoice_readiness",
            "read_only": 1,
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "customer_readiness_summary",
            "label": "Readiness Summary",
            "fieldtype": "Small Text",
            "insert_after": "email_readiness",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "no_delivery_required",
            "label": "No Delivery Required",
            "fieldtype": "Check",
            "insert_after": "customer_readiness_summary",
            "default": "0",
        },
        {
            "fieldname": "no_delivery_reason",
            "label": "No Delivery Reason",
            "fieldtype": "Small Text",
            "insert_after": "no_delivery_required",
            "depends_on": "eval:doc.no_delivery_required",
        },
        {
            "fieldname": "alternative_names",
            "label": "Alternative Names",
            "fieldtype": "Table",
            "insert_after": "customer_name",
            "options": "Customer Alternative Name",
        },
        {
            "fieldname": "document_preferences_section",
            "label": "Document / Print Configuration",
            "fieldtype": "Tab Break",
            "insert_after": "no_delivery_reason",
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
