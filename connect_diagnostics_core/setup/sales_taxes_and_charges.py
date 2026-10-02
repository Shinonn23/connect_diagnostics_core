"""Custom field / property setter definitions for Sales Taxes and Charges."""

CUSTOM_FIELDS = {
    "Sales Taxes and Charges": [],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Sales Taxes and Charges": [
        ("rate", "precision", "6", "Select"),
    ],
}
