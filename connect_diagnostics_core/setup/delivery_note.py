"""Custom field / property setter definitions for Delivery Note."""

CUSTOM_FIELDS = {
    "Delivery Note": [
        {
            "fieldname": "serial_no_summary_section",
            "label": "Serial No Verification",
            "fieldtype": "Section Break",
            "insert_after": "items",
            "is_system_generated": 1,
        },
        {
            "fieldname": "serial_no_summary",
            "label": "Serial No Summary",
            "fieldtype": "HTML",
            "options": "",
            "insert_after": "serial_no_summary_section",
            "description": "Read-only overview of serial numbers per item, for quick verification.",
            "is_system_generated": 1,
        },
    ],
}
