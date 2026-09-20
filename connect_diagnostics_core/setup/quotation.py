# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared values and custom field definitions for Quotation."""

from __future__ import annotations

import frappe

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

# Both signatory types resolve an Employee.  The selected Managing Director is
# still request-only (the Quotation stores the Sales Representative separately).
SIGNATORY_PRINTS_NAME = frozenset(SIGNATORY_TYPES)

# Roles allowed to be picked as sales_representative_employee. This is the
# Quotation's Sales Contact in both signatory modes; a Managing Director is
# selected independently from the Company's authorized-signatory table. Not
# enforced server-side at submit -- see validate_signatory_before_submit in
# api/erpnext/quotation.py.
SIGNATORY_EMPLOYEE_ROLES: dict[str, tuple[str, ...]] = {
    SIGNATORY_SALES_REPRESENTATIVE: ("Sales User", "Sales Manager"),
    # Retained for callers that inspect the legacy role map; the Manager
    # Signatory itself is now selected from the Company allow-list instead of
    # this Quotation Link field.
    SIGNATORY_MANAGING_DIRECTOR: ("Sales Manager",),
}

DOCUMENT_LANGUAGE_OPTIONS = ("Thai", "English", "Thai / English")

# Seeded once via ensure_configuration() so a fresh Quotation has something
# reasonable to pick immediately; this is the wording every historical
# Quotation print has used.
DEFAULT_DELIVERY_TERMS_TEMPLATE = "60 วัน นับถัดจากวันที่ได้รับใบสั่งซื้อ"

CUSTOM_FIELDS = {
    "Company": [
        {
            "fieldname": "quotation_authorized_signatories",
            "label": "Quotation Authorized Signatories",
            "fieldtype": "Table",
            "options": "Quotation Authorized Signatory",
            "insert_after": "company_description",
            "description": "Active Sales Managers allowed to sign Quotations for this Company.",
        },
    ],
    "Quotation": [
        {
            # A standalone tab, immediately after the Details tab and before
            # Address & Contact -- "pricing_rules" is the last Details-tab
            # field before ERPNext's own "address_and_contact_tab" Tab Break.
            "fieldname": "quotation_signatory_section",
            "label": "Signatory",
            "fieldtype": "Tab Break",
            "insert_after": "pricing_rules",
        },
        {
            # Left column: who issues the quotation.
            "fieldname": "sales_representative_employee",
            "label": "Sales Representative",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "quotation_signatory_section",
            "description": (
                "Employee who issues this quotation. Printed in the contact block, and "
                "signs it when the signatory is a Sales Representative. Filtered by role "
                "to match the selected Quotation Signatory Type."
            ),
        },
        {
            "fieldname": "sales_representative_name",
            "label": "Sales Representative Name",
            "fieldtype": "Data",
            "insert_after": "sales_representative_employee",
            "fetch_from": "sales_representative_employee.employee_name",
            "read_only": 1,
        },
        {
            "fieldname": "quotation_signatory_column_break",
            "fieldtype": "Column Break",
            "insert_after": "sales_representative_name",
        },
        {
            # Right column: who signs it.
            "fieldname": "quotation_signatory_type",
            "label": "Quotation Signatory Type",
            "fieldtype": "Select",
            "options": "\n".join(SIGNATORY_TYPES),
            "insert_after": "quotation_signatory_column_break",
            "description": "Determines who signs the quotation.",
        },
        {
            "fieldname": "edit_validity_text",
            "label": "Edit validity text",
            "fieldtype": "Check",
            "insert_after": "valid_till",
            "description": "Check to write Validity Text directly, instead of the computed Valid Till text.",
        },
        {
            # Always visible: shows the computed "N days from quotation date"
            # text read-only when unchecked (kept in sync client-side from
            # transaction_date/valid_till), and becomes free-text editable
            # when Edit validity text is checked.
            "fieldname": "validity_text",
            "label": "Validity Text",
            "fieldtype": "Data",
            "insert_after": "edit_validity_text",
            "read_only_depends_on": "eval:!doc.edit_validity_text",
        },
        {
            # Placed at the top of the standard "Terms" tab, alongside Payment
            # Terms Template and Terms and Conditions -- Delivery Terms is a
            # sibling of those, not part of the Details tab's Valid Till group.
            "fieldname": "delivery_terms_section",
            "label": "Delivery Terms",
            "fieldtype": "Section Break",
            "insert_after": "terms_tab",
        },
        {
            "fieldname": "delivery_terms_template",
            "label": "Delivery Terms Template",
            "fieldtype": "Link",
            "options": "Delivery Terms Template",
            "insert_after": "delivery_terms_section",
            "description": "Picking a template fills in Delivery Terms below, which stays editable.",
        },
        {
            "fieldname": "quotation_delivery_terms",
            "label": "Delivery Terms",
            "fieldtype": "Small Text",
            "insert_after": "delivery_terms_template",
            "description": "Printed as the quotation's delivery terms. Required before submit.",
        },
    ],
}


def ensure_configuration() -> None:
    """Seed the default Delivery Terms Template, keeping an existing one as-is."""
    if frappe.db.exists("Delivery Terms Template", DEFAULT_DELIVERY_TERMS_TEMPLATE):
        return

    frappe.get_doc(
        {
            "doctype": "Delivery Terms Template",
            "template_name": DEFAULT_DELIVERY_TERMS_TEMPLATE,
            "delivery_terms_text": DEFAULT_DELIVERY_TERMS_TEMPLATE,
        }
    ).insert(ignore_permissions=True)
