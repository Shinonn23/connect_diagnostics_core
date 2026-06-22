"""Custom field / property setter definitions for Customer."""

CUSTOM_FIELDS = {
    "Customer": [
        {
            "fieldname": "branch_code",
            "label": "Branch Code",
            "fieldtype": "Data",
            "insert_after": "tax_id",
            "default": "00000",
            "is_system_generated": 1,
        },
        {
            "fieldname": "cd_customer_code",
            "label": "CD Customer Code",
            "fieldtype": "Data",
            "insert_after": "naming_series",
            "bold": 1,
            "description": "Used as Customer ID if filled. Lower priority than DKSH Customer Code. Customer will be renamed if DKSH code is later added.",
            "translatable": 1,
            "unique": 1,
        },
        {
            "fieldname": "customer_name_th",
            "label": "Customer Name TH",
            "fieldtype": "Data",
            "insert_after": "customer_name",
            "bold": 1,
            "in_global_search": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "dksh_customer_code",
            "label": "DKSH Customer Code",
            "fieldtype": "Data",
            "insert_after": "cd_customer_code",
            "bold": 1,
            "in_global_search": 1,
            "search_index": 1,
            "translatable": 1,
            "unique": 1,
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Customer": [
        ("customer_type", "options", "Company\nIndividual\nPartnership\nPublic Company Limited", "Text"),
        (
            "gender",
            "depends_on",
            "eval:!['Company','Public Company Limited'].includes(doc.customer_type)",
            "Data",
        ),
        (None, "customer_type", "Company\nIndividual\nPartnership\nPublic Company Limited", "options"),
        (None, "quick_entry", "0", "Check"),
        ("naming_series", "default", "CUS-#####", "Text"),
        ("naming_series", "description", "If CD code is set, naming series will be ignored.", "Text"),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "options", "CUS-#####", "Text"),
        (
            "salutation",
            "depends_on",
            "eval:!['Company','Public Company Limited'].includes(doc.customer_type)",
            "Data",
        ),
    ],
}
