# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared values and custom field definitions for Quotation."""

SIGNATORY_SALES_REPRESENTATIVE = "Sales Representative"
SIGNATORY_MANAGING_DIRECTOR = "Managing Director"
SIGNATORY_TYPES = (
    SIGNATORY_SALES_REPRESENTATIVE,
    SIGNATORY_MANAGING_DIRECTOR,
)

DOCUMENT_LANGUAGE_OPTIONS = ("Thai", "English", "Thai / English")

CUSTOM_FIELDS = {
    "Quotation": [
        {
            "fieldname": "quotation_signatory_type",
            "label": "Quotation Signatory Type",
            "fieldtype": "Select",
            "options": "\n".join(SIGNATORY_TYPES),
            "insert_after": "valid_till",
            "description": "Default pulled from Customer. Determines who signs the quotation.",
        },
        {
            "fieldname": "quotation_authorized_signatory_employee",
            "label": "Quotation Authorized Signatory Employee",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "quotation_signatory_type",
            "depends_on": f"eval:doc.quotation_signatory_type == '{SIGNATORY_MANAGING_DIRECTOR}'",
            "description": "Override employee for Managing Director signatory. Defaults from Company.",
        },
    ],
}
