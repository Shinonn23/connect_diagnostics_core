# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field / property setter definitions for Customer."""

from __future__ import annotations

from connect_diagnostics_core.setup import quotation as quotation_setup

DOCUMENT_LANGUAGE_OPTIONS = "Thai\nEnglish\nThai / English"

DOCUMENT_PREFERENCES = (
    ("quotation", "Quotation", "use_quotation"),
    ("tax_invoice", "Tax Invoice", "use_tax_invoice"),
    ("delivery_note", "Delivery Note", "use_delivery_note"),
    ("invoice", "Invoice", "use_invoice"),
    ("abbreviated_tax_invoice", "Abbreviated Tax Invoice", "use_abbreviated_tax_invoice"),
    ("receipt", "Receipt", "use_receipt"),
)


def _document_preference_fields() -> list[dict[str, object]]:
    """Build fixed Customer print-preference sections in display order."""
    fields: list[dict[str, object]] = []
    insert_after = "document_preferences_section"

    for prefix, label, use_fieldname in DOCUMENT_PREFERENCES:
        section_fieldname = f"{prefix}_document_preferences_section"
        show_date_fieldname = f"show_{prefix}_date"
        language_fieldname = f"{prefix}_language"
        column_fieldname = f"{prefix}_document_preferences_column"
        original_count_fieldname = f"{prefix}_original_count"
        copy_count_fieldname = f"{prefix}_copy_count"
        enabled_depends_on = f"eval:doc.{use_fieldname}"
        show_date_insert_after = use_fieldname

        fields.append(
            {
                "fieldname": section_fieldname,
                "label": label,
                "fieldtype": "Section Break",
                "insert_after": insert_after,
            }
        )
        fields.append(
            {
                "fieldname": use_fieldname,
                "label": f"Use {label}",
                "fieldtype": "Check",
                "insert_after": section_fieldname,
                "default": "1",
            }
        )
        fields.extend(
            [
                {
                    "fieldname": show_date_fieldname,
                    "label": "Show Quotation Date" if prefix == "quotation" else "Show Date",
                    "fieldtype": "Check",
                    "insert_after": show_date_insert_after,
                    "default": "1",
                    "depends_on": enabled_depends_on,
                },
                {
                    "fieldname": language_fieldname,
                    "label": "Language",
                    "fieldtype": "Select",
                    "options": DOCUMENT_LANGUAGE_OPTIONS,
                    "insert_after": show_date_fieldname,
                    "default": "Thai",
                    "depends_on": enabled_depends_on,
                    "hidden": 1 if prefix == "tax_invoice" else 0,
                },
            ]
        )

        column_insert_after = language_fieldname
        if prefix == "tax_invoice":
            tax_invoice_selection_fields = (
                (
                    "show_tax_invoice_batch_serial",
                    "Show Batch / Serial Number",
                    language_fieldname,
                ),
                (
                    "print_tax_invoice_original",
                    "Print Original (Customer)",
                    "show_tax_invoice_batch_serial",
                ),
                (
                    "print_tax_invoice_customer_copy",
                    "Print Copy (Customer)",
                    "print_tax_invoice_original",
                ),
                (
                    "print_tax_invoice_accounting_copy",
                    "Print Copy (Accounting)",
                    "print_tax_invoice_customer_copy",
                ),
                (
                    "print_tax_invoice_sales_copy",
                    "Print Copy (Sales)",
                    "print_tax_invoice_accounting_copy",
                ),
            )
            fields.extend(
                {
                    "fieldname": fieldname,
                    "label": label,
                    "fieldtype": "Check",
                    "insert_after": insert_after_fieldname,
                    "default": "1",
                    "depends_on": enabled_depends_on,
                }
                for fieldname, label, insert_after_fieldname in tax_invoice_selection_fields
            )
            column_insert_after = "print_tax_invoice_sales_copy"
        if prefix == "quotation":
            fields.extend(
                [
                    {
                        "fieldname": "quotation_signatory_type",
                        "label": "Quotation Signatory Type",
                        "fieldtype": "Select",
                        "options": "\n".join(quotation_setup.SIGNATORY_TYPES),
                        "insert_after": language_fieldname,
                        "default": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
                        "depends_on": enabled_depends_on,
                    },
                    {
                        "fieldname": "override_quotation_validity_text",
                        "label": "Override validity text",
                        "fieldtype": "Check",
                        "insert_after": "quotation_signatory_type",
                        "depends_on": enabled_depends_on,
                        "description": "Use custom text instead of the Quotation Valid Till date.",
                    },
                    {
                        "fieldname": "quotation_custom_validity_text",
                        "label": "Quotation Custom Validity Text",
                        "fieldtype": "Small Text",
                        "insert_after": "override_quotation_validity_text",
                        "depends_on": "eval:doc.use_quotation && doc.override_quotation_validity_text",
                    },
                    {
                        "fieldname": "quotation_delivery_terms",
                        "label": "Quotation Delivery Terms",
                        "fieldtype": "Small Text",
                        "insert_after": "quotation_custom_validity_text",
                        "depends_on": enabled_depends_on,
                        "mandatory_depends_on": enabled_depends_on,
                        "description": (
                            "Default delivery commitment copied to each new Quotation for this Customer."
                        ),
                    },
                ]
            )
            column_insert_after = "quotation_delivery_terms"

        fields.extend(
            [
                {
                    "fieldname": column_fieldname,
                    "fieldtype": "Column Break",
                    "insert_after": column_insert_after,
                    "depends_on": enabled_depends_on,
                },
                {
                    "fieldname": original_count_fieldname,
                    "label": "Original Count",
                    "fieldtype": "Int",
                    "insert_after": column_fieldname,
                    "default": "1",
                    "non_negative": 1,
                    "depends_on": enabled_depends_on,
                    "hidden": 1 if prefix == "tax_invoice" else 0,
                },
                {
                    "fieldname": copy_count_fieldname,
                    "label": "Copy Count",
                    "fieldtype": "Int",
                    "insert_after": original_count_fieldname,
                    "default": "0",
                    "non_negative": 1,
                    "depends_on": enabled_depends_on,
                    "hidden": 1 if prefix == "tax_invoice" else 0,
                },
            ]
        )
        insert_after = copy_count_fieldname

    fields.extend(
        [
            {
                "fieldname": "purchase_order_copy_preferences_section",
                "label": "Source Purchase Order Copy",
                "fieldtype": "Section Break",
                "insert_after": insert_after,
            },
            {
                "fieldname": "use_customer_po",
                "label": "Attach Source Purchase Order Copy",
                "fieldtype": "Check",
                "insert_after": "purchase_order_copy_preferences_section",
                "default": "1",
                "description": (
                    "Attach a copy of the source Purchase Order to confirm the origin "
                    "of the products sold to this customer."
                ),
            },
            {
                "fieldname": "purchase_order_copy_count",
                "label": "Copy Count",
                "fieldtype": "Int",
                "insert_after": "use_customer_po",
                "default": "1",
                "non_negative": 1,
                "depends_on": "eval:doc.use_customer_po",
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
                    "Currently controls date display in the Quotation, Sales Order, "
                    "and Receipt Print Formats. It remains editable until those formats "
                    "use the per-document preferences."
                ),
            },
        ]
    )
    return fields


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
        *_document_preference_fields(),
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
