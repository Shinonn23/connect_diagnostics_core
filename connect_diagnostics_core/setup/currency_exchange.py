"""Custom field / property setter definitions for Currency Exchange."""

CUSTOM_FIELDS = {
    "Currency Exchange": [
        {
            "fieldname": "remark",
            "label": "Remark",
            "fieldtype": "Select",
            "insert_after": "column_break_5",
            "default": "Base currency",
            "options": "Base currency\nDirect rate\nReverse rate",
            "reqd": 1,
        },
    ],
}
