"""Custom field / property setter definitions for Purchase Taxes and Charges."""

CUSTOM_FIELDS = {
    "Purchase Taxes and Charges": [],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Purchase Taxes and Charges": [
        ("rate", "precision", "6", "Select"),
    ],
}
