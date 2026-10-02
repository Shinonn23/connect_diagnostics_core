"""Custom field / property setter definitions for Journal Entry Account."""

CUSTOM_FIELDS = {
    "Journal Entry Account": [
        {
            "fieldname": "column_break_cun7x",
            "fieldtype": "Column Break",
            "insert_after": "tax_invoice_date",
            "is_system_generated": 1,
        },
        {
            "fieldname": "customer",
            "label": "Customer",
            "fieldtype": "Link",
            "insert_after": "supplier",
            "is_system_generated": 1,
            "options": "Customer",
        },
        {
            "fieldname": "is_petty_cash_account",
            "label": "Is Petty Cash Account",
            "fieldtype": "Check",
            "insert_after": "party",
            "fetch_from": "account.is_petty_cash_account",
            "hidden": 1,
            "is_system_generated": 1,
            "read_only": 1,
        },
        {
            "fieldname": "overwrite_tax_invoice",
            "label": "Overwrite Tax Invoice",
            "fieldtype": "Section Break",
            "insert_after": "credit",
            "collapsible": 0,
            "depends_on": "eval:doc.account_type == 'Tax'",
            "is_system_generated": 1,
        },
        {
            "fieldname": "petty_cash_holder",
            "label": "Petty Cash Holder",
            "fieldtype": "Link",
            "insert_after": "is_petty_cash_account",
            "depends_on": "eval:doc.is_petty_cash_account == 1;",
            "is_system_generated": 1,
            "link_filters": '[["Petty Cash Holder","petty_cash_account","=","eval: doc.account"]]',
            "mandatory_depends_on": "eval:doc.is_petty_cash_account == 1;",
            "options": "Petty Cash Holder",
        },
        {
            "fieldname": "petty_cash_holder_name",
            "label": "Petty Cash Holder Name",
            "fieldtype": "Data",
            "insert_after": "petty_cash_holder",
            "depends_on": "eval:doc.is_petty_cash_account == 1;",
            "fetch_from": "petty_cash_holder.petty_cash_holder",
            "is_system_generated": 1,
            "read_only": 1,
        },
        {
            "fieldname": "supplier",
            "label": "Supplier",
            "fieldtype": "Link",
            "insert_after": "column_break_cun7x",
            "is_system_generated": 1,
            "options": "Supplier",
        },
        {
            "fieldname": "tax_base_amount",
            "label": "Tax Base Amount",
            "fieldtype": "Float",
            "insert_after": "customer",
            "description": "Leave this value to 0 and system will auto calculate based on tax rate.",
            "is_system_generated": 1,
        },
        {
            "fieldname": "tax_invoice_date",
            "label": "Tax Invoice Date",
            "fieldtype": "Date",
            "insert_after": "tax_invoice_number",
            "is_system_generated": 1,
        },
        {
            "fieldname": "tax_invoice_number",
            "label": "Tax Invoice Number",
            "fieldtype": "Data",
            "insert_after": "overwrite_tax_invoice",
            "is_system_generated": 1,
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Journal Entry Account": [
        ("accounting_dimensions_section", "collapsible", "0", "Check"),
    ],
}
