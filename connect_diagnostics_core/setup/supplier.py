"""Custom field / property setter definitions for Supplier."""

CUSTOM_FIELDS = {
    "Supplier": [
        {
            "fieldname": "branch_code",
            "label": "Branch Code",
            "fieldtype": "Data",
            "insert_after": "tax_id",
            "default": "00000",
            "is_system_generated": 1,
        },
        {
            "fieldname": "alternative_names",
            "label": "Alternative Names",
            "fieldtype": "Table",
            "insert_after": "supplier_name",
            "options": "Supplier Alternative Name",
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Supplier": [
        (None, "quick_entry", "0", "Check"),
        (
            "naming_series",
            "description",
            "Supplier ID naming series.",
            "Text",
        ),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "default", "5B.###", "Text"),
        ("naming_series", "options", "5B.###\nSUP-#####", "Text"),
        ("naming_series", "reqd", "1", "Check"),
        ("supplier_type", "options", "Company\nIndividual\nPartnership\nPublic Company Limited", "Text"),
    ],
}
