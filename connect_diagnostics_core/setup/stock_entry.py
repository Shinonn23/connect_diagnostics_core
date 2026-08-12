"""Custom field definitions for Stock Entry.

`stock_count` traces a Stock Count-generated adjustment (holding transfer, or a
yearly receipt/issue) back to the Stock Count that created it.
"""

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
}
