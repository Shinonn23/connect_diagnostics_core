"""Custom field definitions for Stock Settings.

`default_holding_warehouse` is the single per-site quarantine ("คลังพัก")
warehouse that a monthly Stock Count moves short / mismatched items into.
"""

CUSTOM_FIELDS = {
    "Stock Settings": [
        {
            "fieldname": "default_holding_warehouse",
            "label": "Default Holding Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "insert_after": "sample_retention_warehouse",
            "description": "Quarantine warehouse a monthly Stock Count transfers short or mismatched items into.",
            "is_system_generated": 1,
        },
    ],
}
