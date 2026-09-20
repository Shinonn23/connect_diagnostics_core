"""Custom field / property setter definitions for Department."""

CUSTOM_FIELDS = {
    "Department": [
        {
            "fieldname": "accounting_department",
            "label": "Accounting Department",
            "fieldtype": "Link",
            "insert_after": "payroll_cost_center",
            "is_system_generated": 1,
            "options": "Accounting Department",
        },
    ],
}
