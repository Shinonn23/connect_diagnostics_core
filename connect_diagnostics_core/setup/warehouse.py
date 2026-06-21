"""Custom field / property setter definitions for Warehouse."""

CUSTOM_FIELDS = {
    'Warehouse': [
        {
            'fieldname': 'dksh_sloc_code',
            'label': 'DKSH SLOC Code',
            'fieldtype': 'Data',
            'insert_after': 'warehouse_name',
        },
    ],
}
