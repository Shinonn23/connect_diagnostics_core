# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field definitions for Company."""

CUSTOM_FIELDS = {
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
}
