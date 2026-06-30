"""Custom field / property setter definitions for Supplier."""

CUSTOM_FIELDS = {
    "Supplier": [
        {
            "fieldname": "branch_code",
            "label": "Branch Code",
            "fieldtype": "Data",
            "insert_after": "tax_id",
            "default": "00000",
            "is_system_generated": 1,
        },
        {
            "fieldname": "has_dksh_code",
            "label": "Has DKSH Code",
            "fieldtype": "Check",
            "insert_after": "naming_series",
            "default": "0",
        },
        {
            "fieldname": "supplier_code_is_dksh_code",
            "label": "Supplier Code is DKSH Code",
            "fieldtype": "Check",
            "insert_after": "has_dksh_code",
            "default": "0",
            "depends_on": "eval:doc.has_dksh_code",
            "description": "Tick when the supplier has no CD code yet and the DKSH code is used as the Supplier ID. Untick and save to issue a CD code (the DKSH code is kept).",
        },
        {
            "fieldname": "dksh_supplier_code",
            "label": "DKSH Supplier Code",
            "fieldtype": "Data",
            "insert_after": "supplier_code_is_dksh_code",
            "bold": 1,
            "depends_on": "eval:doc.has_dksh_code",
            "description": "When 'Supplier Code is DKSH Code' is ticked, enter the DKSH code here — it becomes the Supplier ID.",
            "in_global_search": 1,
            "search_index": 1,
            "unique": 1,
        },
        {
            "fieldname": "alternative_names",
            "label": "Alternative Names",
            "fieldtype": "Table",
            "insert_after": "supplier_name",
            "options": "Supplier Alternative Name",
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Supplier": [
        (None, "quick_entry", "0", "Check"),
        (
            "naming_series",
            "description",
            "CD code. Ignored when the DKSH code is used as the Supplier ID.",
            "Text",
        ),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "default", "5B.###", "Text"),
        ("naming_series", "options", "5B.###\nSUP-#####", "Text"),
        ("naming_series", "reqd", "1", "Check"),
        ("supplier_type", "options", "Company\nIndividual\nPartnership\nPublic Company Limited", "Text"),
    ],
}
