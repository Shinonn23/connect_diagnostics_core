"""Custom field / property setter definitions for Sales Invoice Item."""

CUSTOM_FIELDS = {
    "Sales Invoice Item": [
        {
            "fieldname": "department",
            "label": "Department",
            "fieldtype": "Link",
            "insert_after": "accounting_dimensions_section",
            "is_system_generated": 1,
            "options": "Accounting Department",
        },
        {
            "fieldname": "is_deposit_item",
            "label": "Is Deposit Item",
            "fieldtype": "Check",
            "insert_after": "item_code",
            "fetch_from": "item_code.is_deposit_item",
            "is_system_generated": 1,
            "read_only": 1,
        },
        {
            "fieldname": "territory",
            "label": "Territory",
            "fieldtype": "Link",
            "insert_after": "dimension_col_break",
            "is_system_generated": 1,
            "options": "Territory",
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Sales Invoice Item": [
        ("barcode", "hidden", "0", "Check"),
        ("discount_account", "hidden", "1", "Check"),
        ("discount_account", "mandatory_depends_on", "", "Code"),
        ("target_warehouse", "hidden", "1", "Check"),
    ],
}
