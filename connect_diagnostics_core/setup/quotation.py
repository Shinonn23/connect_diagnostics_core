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
<<<<<<< HEAD
            "depends_on": f"eval:doc.quotation_signatory_type == '{SIGNATORY_MANAGING_DIRECTOR}'",
            "description": "Override employee for Managing Director signatory. Defaults from Company.",
=======
            "depends_on": (f"eval:doc.quotation_signatory_type=='{SIGNATORY_SALES_REPRESENTATIVE}'"),
            "mandatory_depends_on": (
                f"eval:doc.quotation_signatory_type=='{SIGNATORY_SALES_REPRESENTATIVE}'"
            ),
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_print_configuration_column",
            "fieldtype": "Column Break",
            "insert_after": "quotation_sales_representative",
        },
        {
            "fieldname": "quotation_validity_mode",
            "label": "Validity Mode",
            "fieldtype": "Select",
            "options": "\n".join(VALIDITY_MODES),
            "insert_after": "quotation_print_configuration_column",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_custom_validity_text",
            "label": "Custom Validity Text",
            "fieldtype": "Small Text",
            "insert_after": "quotation_validity_mode",
            "depends_on": f"eval:doc.quotation_validity_mode=='{VALIDITY_CUSTOM_TEXT}'",
            "mandatory_depends_on": (f"eval:doc.quotation_validity_mode=='{VALIDITY_CUSTOM_TEXT}'"),
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_delivery_terms",
            "label": "Delivery Terms",
            "fieldtype": "Small Text",
            "insert_after": "quotation_custom_validity_text",
            "reqd": 1,
            "allow_on_submit": 1,
            "description": "Required delivery commitment printed on this Quotation.",
        },
        {
            "fieldname": "quotation_language",
            "label": "Language",
            "fieldtype": "Select",
            "options": "\n".join(DOCUMENT_LANGUAGE_OPTIONS),
            "insert_after": "quotation_delivery_terms",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_original_count",
            "label": "Original Count",
            "fieldtype": "Int",
            "insert_after": "quotation_language",
            "non_negative": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_copy_count",
            "label": "Copy Count",
            "fieldtype": "Int",
            "insert_after": "quotation_original_count",
            "non_negative": 1,
            "allow_on_submit": 1,
>>>>>>> 4543b3b (feat: Add workflow action master and state fixtures for procure-to-pay workflow)
        },
    ],
}
