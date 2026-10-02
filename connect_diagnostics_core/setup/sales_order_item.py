"""Custom field / property setter definitions for Sales Order Item."""

CUSTOM_FIELDS = {
    "Sales Order Item": [],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Sales Order Item": [
        ("accounting_dimensions_section", "collapsible", "0", "Check"),
        ("delivery_date", "in_list_view", "0", "Check"),
        ("item_name", "in_list_view", "1", "Check"),
        ("uom", "in_list_view", "1", "Check"),
    ],
}
