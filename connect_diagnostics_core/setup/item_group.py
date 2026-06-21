"""Custom field / property setter definitions for Item Group."""

CUSTOM_FIELDS = {
    'Item Group': [
        {
            'fieldname': 'mat_group_code',
            'label': 'Mat Group Code',
            'fieldtype': 'Data',
            'insert_after': 'column_break_5',
        },
        {
            'fieldname': 'mat_group_desc',
            'label': 'Mat Group Desc',
            'fieldtype': 'Data',
            'insert_after': 'mat_group4_code',
        },
        {
            'fieldname': 'mat_group4_code',
            'label': 'Mat Group4 Code',
            'fieldtype': 'Data',
            'insert_after': 'mat_group_code',
        },
    ],
}
