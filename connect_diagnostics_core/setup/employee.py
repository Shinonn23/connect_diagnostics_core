"""Custom field, property setter, and permission definitions for Employee."""

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

EMPLOYEE_DOCTYPE = "Employee"
HR_MANAGER_ROLE = "HR Manager"

CUSTOM_FIELDS = {
    "Employee": [
        {
            "fieldname": "approvers_section",
            "label": "Approvers",
            "fieldtype": "Section Break",
            "insert_after": "default_shift",
            "is_system_generated": 1,
        },
        {
            "fieldname": "column_break_45",
            "fieldtype": "Column Break",
            "insert_after": "leave_approver",
            "is_system_generated": 1,
        },
        {
            "fieldname": "first_name_en",
            "label": "First Name EN",
            "fieldtype": "Data",
            "insert_after": "column_break_9",
        },
        {
            "fieldname": "last_name_en",
            "label": "Last Name EN",
            "fieldtype": "Data",
            "insert_after": "first_name_en",
        },
        {
            "fieldname": "default_shift",
            "label": "Default Shift",
            "fieldtype": "Link",
            "insert_after": "holiday_list",
            "is_system_generated": 1,
            "options": "Shift Type",
        },
        {
            "fieldname": "employment_type",
            "label": "Employment Type",
            "fieldtype": "Link",
            "insert_after": "department",
            "ignore_user_permissions": 1,
            "is_system_generated": 1,
            "options": "Employment Type",
        },
        {
            "fieldname": "expense_approver",
            "label": "Expense Approver",
            "fieldtype": "Link",
            "insert_after": "approvers_section",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "grade",
            "label": "Grade",
            "fieldtype": "Link",
            "insert_after": "branch",
            "is_system_generated": 1,
            "options": "Employee Grade",
        },
        {
            "fieldname": "health_insurance_no",
            "label": "Health Insurance No",
            "fieldtype": "Data",
            "insert_after": "health_insurance_provider",
            "depends_on": "eval:doc.health_insurance_provider",
            "is_system_generated": 1,
        },
        {
            "fieldname": "health_insurance_provider",
            "label": "Health Insurance Provider",
            "fieldtype": "Link",
            "insert_after": "health_insurance_section",
            "is_system_generated": 1,
            "options": "Employee Health Insurance",
        },
        {
            "fieldname": "health_insurance_section",
            "label": "Health Insurance",
            "fieldtype": "Section Break",
            "insert_after": "health_details",
            "collapsible": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "job_applicant",
            "label": "Job Applicant",
            "fieldtype": "Link",
            "insert_after": "employment_details",
            "is_system_generated": 1,
            "options": "Job Applicant",
        },
        {
            "fieldname": "leave_approver",
            "label": "Leave Approver",
            "fieldtype": "Link",
            "insert_after": "expense_approver",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "payroll_cost_center",
            "label": "Payroll Cost Center",
            "fieldtype": "Link",
            "insert_after": "salary_cb",
            "fetch_from": "department.payroll_cost_center",
            "fetch_if_empty": 1,
            "is_system_generated": 1,
            "options": "Cost Center",
        },
        {
            "fieldname": "salary_cb",
            "fieldtype": "Column Break",
            "insert_after": "salary_mode",
            "is_system_generated": 1,
        },
        {
            "fieldname": "shift_request_approver",
            "label": "Shift Request Approver",
            "fieldtype": "Link",
            "insert_after": "column_break_45",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "national_id",
            "label": "National ID",
            "fieldtype": "Data",
            "insert_after": "attendance_device_id",
            "mask": 1,
            "no_copy": 1,
            "unique": 1,
        },
        {
            "fieldname": "tax_id",
            "label": "Tax ID",
            "fieldtype": "Data",
            "insert_after": "national_id",
            "mask": 1,
            "no_copy": 1,
            "unique": 1,
        },
    ],
}


def ensure_employee_mask_permission() -> None:
    """Grant HR Manager only the mask capability missing from standard Employee permissions."""
    setup_custom_perms(EMPLOYEE_DOCTYPE)
    permission_names = frappe.get_all(
        "Custom DocPerm",
        filters={
            "parent": EMPLOYEE_DOCTYPE,
            "role": HR_MANAGER_ROLE,
            "permlevel": 0,
            "if_owner": 0,
        },
        pluck="name",
    )
    if not permission_names:
        permission = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Custom DocPerm",
                    "parent": EMPLOYEE_DOCTYPE,
                    "role": HR_MANAGER_ROLE,
                    "permlevel": 0,
                    "if_owner": 0,
                    "select": 0,
                    "read": 0,
                    "write": 0,
                    "create": 0,
                    "delete": 0,
                    "submit": 0,
                    "cancel": 0,
                    "amend": 0,
                    "mask": 1,
                    "report": 0,
                    "export": 0,
                    "import": 0,
                    "share": 0,
                    "print": 0,
                    "email": 0,
                }
            ),
        )
        permission.insert(ignore_permissions=True)
        return

    for permission_name in permission_names:
        permission = cast(Document, frappe.get_doc("Custom DocPerm", permission_name))
        if permission.get("mask"):
            continue
        permission.set("mask", 1)
        permission.save(ignore_permissions=True)


# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Employee": [
        ("employee_number", "hidden", "1", "Check"),
        ("employee_number", "reqd", "0", "Check"),
        ("employment_type", "reqd", "1", "Check"),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "default", "YY-BE.MM.###", "Text"),
        ("naming_series", "options", "YY-BE.MM.###\nC.YY-BE.MM.###", "Text"),
        ("naming_series", "reqd", "1", "Check"),
    ],
}
