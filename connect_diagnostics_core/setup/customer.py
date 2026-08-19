# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field / property setter definitions for Customer."""

from __future__ import annotations


def _sales_requirement_fields() -> list[dict[str, object]]:
    """Build the Customer sales-document requirement fields.

    Print behaviour is now chosen per print in the print sidebar, so the Customer
    keeps only the process gate it enforces: whether an order must be quoted first.
    """
    return [
        {
            "fieldname": "sales_requirements_section",
            "label": "Sales Document Requirements",
            "fieldtype": "Tab Break",
            "insert_after": "portal_users",
            "description": "What this Customer requires before a sale can proceed.",
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
        *_sales_requirement_fields(),
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
