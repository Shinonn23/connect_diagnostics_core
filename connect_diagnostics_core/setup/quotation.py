# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared values and custom field definitions for Quotation."""

SIGNATORY_SALES_REPRESENTATIVE = "Sales Representative"
SIGNATORY_MANAGING_DIRECTOR = "Managing Director"
SIGNATORY_TYPES = (
    SIGNATORY_SALES_REPRESENTATIVE,
    SIGNATORY_MANAGING_DIRECTOR,
)

# Printed under the signature line. A fixed caption per signatory type, not the
# Employee's designation: the caption states the role the signature carries on
# the quotation, which is not the signer's job title.
SIGNATORY_CAPTIONS: dict[str, tuple[str, str]] = {
    SIGNATORY_SALES_REPRESENTATIVE: ("ผู้เสนอราคา", "Sales Representative"),
    SIGNATORY_MANAGING_DIRECTOR: ("กรรมการผู้จัดการ", "Managing Director"),
}

# Managing Director quotations print an empty name so the director signs and
# writes the name by hand, so only these types resolve an Employee name.
SIGNATORY_PRINTS_NAME = frozenset({SIGNATORY_SALES_REPRESENTATIVE})

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
            "fieldname": "sales_representative_employee",
            "label": "Sales Representative",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "quotation_signatory_type",
            "description": (
                "Employee who issues this quotation. Printed in the contact block, and "
                "signs it when the signatory is a Sales Representative."
            ),
        },
        {
            "fieldname": "override_quotation_validity_text",
            "label": "Override validity text",
            "fieldtype": "Check",
            "insert_after": "sales_representative_employee",
            "description": "Use custom text instead of the Valid Till date.",
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
