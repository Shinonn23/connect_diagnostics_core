"""Custom field / property setter definitions for Account."""

CUSTOM_FIELDS = {
    "Account": [
        {
            "fieldname": "account_name_th",
            "label": "Account Name TH",
            "fieldtype": "Data",
            "insert_after": "account_name",
            "in_list_view": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "sub_account_type",
            "label": "Sub Account Type",
            "fieldtype": "Data",
            "insert_after": "account_type",
            "in_standard_filter": 1,
        },
        {
            "fieldname": "is_petty_cash_account",
            "label": "Is Petty Cash Account",
            "fieldtype": "Check",
            "insert_after": "balance_must_be",
            "is_system_generated": 1,
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Account": [
        (None, "default_view", "Tree", "Select"),
    ],
}
