# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field and property setter definitions for Quotation printing."""

FORM_PRESET_01 = "Form 01"
FORM_PRESET_02 = "Form 02"
FORM_PRESET_03 = "Form 03"
FORM_PRESET_04 = "Form 04"
FORM_PRESET_CUSTOM = "Custom"
FORM_PRESETS = (
    FORM_PRESET_01,
    FORM_PRESET_02,
    FORM_PRESET_03,
    FORM_PRESET_04,
    FORM_PRESET_CUSTOM,
)

SIGNATORY_SALES_REPRESENTATIVE = "Sales Representative"
SIGNATORY_MANAGING_DIRECTOR = "Managing Director"
SIGNATORY_TYPES = (
    SIGNATORY_SALES_REPRESENTATIVE,
    SIGNATORY_MANAGING_DIRECTOR,
)

VALIDITY_VALID_TILL = "Valid Till"
VALIDITY_CUSTOM_TEXT = "Custom Text"
VALIDITY_MODES = (
    VALIDITY_VALID_TILL,
    VALIDITY_CUSTOM_TEXT,
)

DOCUMENT_LANGUAGE_OPTIONS = ("Thai", "English", "Thai / English")

PRESET_VALUES: dict[str, dict[str, int | str]] = {
    FORM_PRESET_01: {
        "show_quotation_date": 1,
        "quotation_signatory_type": SIGNATORY_SALES_REPRESENTATIVE,
        "quotation_validity_mode": VALIDITY_VALID_TILL,
    },
    FORM_PRESET_02: {
        "show_quotation_date": 0,
        "quotation_signatory_type": SIGNATORY_SALES_REPRESENTATIVE,
        "quotation_validity_mode": VALIDITY_VALID_TILL,
    },
    FORM_PRESET_03: {
        "show_quotation_date": 1,
        "quotation_signatory_type": SIGNATORY_MANAGING_DIRECTOR,
        "quotation_validity_mode": VALIDITY_VALID_TILL,
    },
    FORM_PRESET_04: {
        "show_quotation_date": 1,
        "quotation_signatory_type": SIGNATORY_MANAGING_DIRECTOR,
        "quotation_validity_mode": VALIDITY_CUSTOM_TEXT,
    },
}

DEFAULT_PRINT_CONFIGURATION: dict[str, int | str] = {
    "quotation_form_preset": FORM_PRESET_01,
    **PRESET_VALUES[FORM_PRESET_01],
    "quotation_language": "Thai",
    "quotation_original_count": 1,
    "quotation_copy_count": 0,
}

PRINT_CONFIGURATION_FIELDNAMES = (
    "quotation_form_preset",
    "show_quotation_date",
    "quotation_signatory_type",
    "quotation_sales_representative",
    "quotation_validity_mode",
    "quotation_custom_validity_text",
    "quotation_delivery_terms",
    "quotation_language",
    "quotation_original_count",
    "quotation_copy_count",
)

CUSTOM_FIELDS = {
    "Quotation": [
        {
            "fieldname": "quotation_print_configuration_section",
            "label": "Print Configuration",
            "fieldtype": "Tab Break",
            "insert_after": "language",
        },
        {
            "fieldname": "quotation_form_preset",
            "label": "Form Preset",
            "fieldtype": "Select",
            "options": "\n".join(FORM_PRESETS),
            "insert_after": "quotation_print_configuration_section",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "show_quotation_date",
            "label": "Show Date",
            "fieldtype": "Check",
            "insert_after": "quotation_form_preset",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_signatory_type",
            "label": "Signatory Type",
            "fieldtype": "Select",
            "options": "\n".join(SIGNATORY_TYPES),
            "insert_after": "show_quotation_date",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "quotation_sales_representative",
            "label": "Sales Representative",
            "fieldtype": "Link",
            "options": "Sales Person",
            "insert_after": "quotation_signatory_type",
            "depends_on": (
                f"eval:doc.quotation_signatory_type=='{SIGNATORY_SALES_REPRESENTATIVE}'"
            ),
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
            "mandatory_depends_on": (
                f"eval:doc.quotation_validity_mode=='{VALIDITY_CUSTOM_TEXT}'"
            ),
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
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Quotation": [
        (None, "track_changes", "1", "Check"),
    ],
}
