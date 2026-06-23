"""Custom field / property setter definitions for Supplier."""

CUSTOM_FIELDS = {
    "Supplier": [
        {
            "fieldname": "abbr",
            "label": "Abbreviation",
            "fieldtype": "Data",
            "insert_after": "supplier_name",
            "description": "2-4 ตัวอักษรย่อ (พิมพ์ใหญ่) ใช้สร้าง Item Code เช่น AD, ZY, WP",
            "length": 4,
            "in_list_view": 1,
        },
        {
            "fieldname": "branch_code",
            "label": "Branch Code",
            "fieldtype": "Data",
            "insert_after": "tax_id",
            "default": "00000",
            "is_system_generated": 1,
        },
        {
            "fieldname": "cd_supplier_code",
            "label": "CD Supplier Code",
            "fieldtype": "Data",
            "insert_after": "naming_series",
            "bold": 1,
            "description": "Used as Customer ID if filled. Lower priority than DKSH Customer Code. Customer will be renamed if DKSH code is later added.",
            "unique": 1,
        },
        {
            "fieldname": "dksh_supplier_code",
            "label": "DKSH Supplier Code",
            "fieldtype": "Data",
            "insert_after": "cd_supplier_code",
            "bold": 1,
            "in_global_search": 1,
            "search_index": 1,
            "unique": 1,
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Supplier": [
        (None, "quick_entry", "0", "Check"),
        ("naming_series", "description", "If CD code is set, naming series will be ignored.", "Text"),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "default", "5B.###", "Text"),
        ("naming_series", "options", "5B.###\nSUP-#####", "Text"),
        ("naming_series", "reqd", "1", "Check"),
        ("supplier_type", "options", "Company\nIndividual\nPartnership\nPublic Company Limited", "Text"),
    ],
}
