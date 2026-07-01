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
            "fieldname": "has_dksh_code",
            "label": "Has DKSH Code",
            "fieldtype": "Check",
            "insert_after": "naming_series",
            "default": "0",
        },
        {
            "fieldname": "customer_code_is_dksh_code",
            "label": "Customer Code is DKSH Code",
            "fieldtype": "Check",
            "insert_after": "has_dksh_code",
            "default": "0",
            "depends_on": "eval:doc.has_dksh_code",
            "description": "Tick when the customer has no CD code yet and the DKSH code is used as the Customer ID. Untick and save to issue a CD code (the DKSH code is kept).",
        },
        {
            "fieldname": "dksh_customer_code",
            "label": "DKSH Customer Code",
            "fieldtype": "Data",
            "insert_after": "customer_code_is_dksh_code",
            "bold": 1,
            "depends_on": "eval:doc.has_dksh_code",
            "description": "When 'Customer Code is DKSH Code' is ticked, enter the DKSH code here — it becomes the Customer ID.",
            "in_global_search": 1,
            "search_index": 1,
            "unique": 1,
        },
        {
            "fieldname": "alternative_names",
            "label": "Alternative Names",
            "fieldtype": "Table",
            "insert_after": "customer_name",
            "options": "Customer Alternative Name",
        },
        {
            "fieldname": "cd_document_preferences_section",
            "label": "Document / Print Preferences",
            "fieldtype": "Tab Break",
            "insert_after": "portal_users",
        },
        {
            "fieldname": "cd_use_quotation",
            "label": "Quotation",
            "fieldtype": "Check",
            "insert_after": "cd_document_preferences_section",
            "default": "0",
        },
        {
            "fieldname": "cd_use_customer_po",
            "label": "Purchase Order (PO)",
            "fieldtype": "Check",
            "insert_after": "cd_use_quotation",
            "default": "0",
        },
        {
            "fieldname": "cd_use_tax_invoice",
            "label": "Tax Invoice / Delivery Note / Invoice",
            "fieldtype": "Check",
            "insert_after": "cd_use_customer_po",
            "default": "0",
        },
        {
            "fieldname": "cd_use_receipt",
            "label": "Receipt",
            "fieldtype": "Check",
            "insert_after": "cd_use_tax_invoice",
            "default": "0",
        },
        {
            "fieldname": "cd_use_abbreviated_tax_invoice",
            "label": "Abbreviated Tax Invoice / Receipt",
            "fieldtype": "Check",
            "insert_after": "cd_use_receipt",
            "default": "0",
        },
        {
            "fieldname": "cd_print_date",
            "label": "Print Date",
            "fieldtype": "Check",
            "insert_after": "cd_use_abbreviated_tax_invoice",
            "default": "1",
            "description": "When ticked, printed documents show the document date. Untick for customers who use pre-printed forms where the date is filled in by hand.",
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
        ("naming_series", "default", "2S.###", "Text"),
        (
            "naming_series",
            "description",
            "CD code, auto-selected by customer type: Individual→2S, Company→4A, Hospital/Gov→4H. Ignored when the DKSH code is used as the Customer ID.",
            "Text",
        ),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "options", "2S.###\n4A.###\n4H.###", "Text"),
        (
            "salutation",
            "depends_on",
            "eval:!['Company','Public Company Limited'].includes(doc.customer_type)",
            "Data",
        ),
    ],
}
