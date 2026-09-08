"""Custom field / property setter definitions for Sales Invoice Item."""

CUSTOM_FIELDS = {
    "Sales Invoice Item": [
        {
            "fieldname": "department",
            "label": "Department",
            "fieldtype": "Link",
            "insert_after": "accounting_dimensions_section",
            "is_system_generated": 1,
            "options": "Department",
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
        {
            "fieldname": "withholding_tax_type",
            "label": "Withholding Tax Type",
            "fieldtype": "Link",
            "insert_after": "item_tax_template",
            "description": "Default Withholding Tax Type setup on Item",
            "fetch_from": "item_code.withholding_tax_type",
            "fetch_if_empty": 1,
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
            "print_hide": 1,
            "read_only": 1,
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
