"""Custom field / property setter definitions for Sales Order Item."""

CUSTOM_FIELDS = {
    'Sales Order Item': [
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
    'Sales Order Item': [
        ('accounting_dimensions_section', 'collapsible', '0', 'Check'),
    ],
}
