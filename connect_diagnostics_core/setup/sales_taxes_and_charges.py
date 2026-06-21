"""Custom field / property setter definitions for Sales Taxes and Charges."""

CUSTOM_FIELDS = {
    'Sales Taxes and Charges': [
        {
            'fieldname': 'department',
            'label': 'Department',
            'fieldtype': 'Link',
            'insert_after': 'accounting_dimensions_section',
            'is_system_generated': 1,
            'options': 'Accounting Department',
        },
        {
            'fieldname': 'territory',
            'label': 'Territory',
            'fieldtype': 'Link',
            'insert_after': 'dimension_col_break',
            'is_system_generated': 1,
            'options': 'Territory',
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    'Sales Taxes and Charges': [
        ('rate', 'precision', '6', 'Select'),
    ],
}
