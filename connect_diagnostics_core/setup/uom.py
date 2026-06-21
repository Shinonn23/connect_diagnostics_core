"""Custom field / property setter definitions for UOM."""

CUSTOM_FIELDS = {
    "UOM": [
        {
            "fieldname": "abbr",
            "label": "Abbr",
            "fieldtype": "Data",
            "insert_after": "uom_name",
            "translatable": 1,
        },
    ],
}
