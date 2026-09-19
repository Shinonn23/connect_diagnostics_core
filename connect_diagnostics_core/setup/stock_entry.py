"""Custom fields linking native stock effects back to their source evidence."""

CUSTOM_FIELDS = {
    "Stock Entry": [
        {
            "fieldname": "stock_count",
            "label": "Stock Count",
            "fieldtype": "Link",
            "options": "Stock Count",
            "insert_after": "purpose",
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
            "is_system_generated": 1,
        },
    ],
    "Stock Reconciliation": [
        {
            "fieldname": "stock_count",
            "label": "Stock Count",
            "fieldtype": "Link",
            "options": "Stock Count",
            "insert_after": "purpose",
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
            "is_system_generated": 1,
        },
    ],
}
