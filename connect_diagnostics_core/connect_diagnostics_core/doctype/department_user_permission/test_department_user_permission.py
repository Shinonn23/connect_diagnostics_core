# Copyright (c) 2026, Siwat Sroisuwan and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.connect_diagnostics_core.doctype.department_user_permission.department_user_permission import (
    apply_permissions,
    get_employees_in_department,
    remove_permissions,
)


class TestDepartmentUserPermission(FrappeTestCase):
    def setUp(self):
        # Create test user
        if not frappe.db.exists("User", "test_user_perm@example.com"):
            user = frappe.new_doc("User")
            user.email = "test_user_perm@example.com"
            user.first_name = "Test User Perm"
            user.send_welcome_email = 0
            user.insert(ignore_permissions=True)

        # Create test department
        dept_name = "Test Dept Permissions"
        existing_dept = frappe.db.get_value("Department", {"department_name": dept_name}, "name")
        if not existing_dept:
            dept = frappe.new_doc("Department")
            dept.department_name = dept_name
            dept.insert(ignore_permissions=True)
            self.dept_name = dept.name
        else:
            self.dept_name = existing_dept

        # Check if Employee with user_id already exists
        existing_emp = frappe.db.get_value("Employee", {"user_id": "test_user_perm@example.com"}, "name")
        if not existing_emp:
            emp = frappe.new_doc("Employee")
            emp.first_name = "Test Employee"
            emp.user_id = "test_user_perm@example.com"
            emp.department = self.dept_name
            emp.status = "Active"

            # Mandatory fields for this installation
            emp.gender = "Female"
            emp.date_of_birth = "1980-01-01"
            emp.employment_type = "Full-Time"
            emp.custom_first_name_th = "ทดสอบ"

            from frappe.utils import getdate

            emp.date_of_joining = getdate("2026-06-10")
            emp.naming_series = "EMP-"
            emp.insert(ignore_permissions=True)
            self.emp_name = emp.name
        else:
            self.emp_name = existing_emp

    def test_get_employees_in_department(self):
        employees = get_employees_in_department(self.dept_name)
        self.assertEqual(len(employees), 1)
        self.assertEqual(employees[0]["user_id"], "test_user_perm@example.com")

    def test_apply_and_remove_permissions(self):
        # Create a Department User Permission document
        doc = frappe.new_doc("Department User Permission")
        doc.department = self.dept_name
        doc.allow = "Company"
        doc.for_value = "DKSH"
        doc.is_default = 1
        doc.apply_to_all_doctypes = 1

        # Append a user to the child table using the dynamically resolved employee name
        doc.append(
            "users",
            {
                "user": "test_user_perm@example.com",
                "employee": self.emp_name,
                "employee_name": "Test Employee",
                "apply": 1,
            },
        )

        doc.insert(ignore_permissions=True)

        # Apply permissions
        res = apply_permissions(doc.name)
        self.assertEqual(res["applied"], 1)
        self.assertEqual(res["updated"], 0)

        # Verify the User Permission record exists
        user_perm_exists = frappe.db.exists(
            "User Permission",
            {"user": "test_user_perm@example.com", "allow": "Company", "for_value": "DKSH", "is_default": 1},
        )
        self.assertTrue(user_perm_exists)

        # Remove permissions
        rem_res = remove_permissions(doc.name)
        self.assertEqual(rem_res["removed"], 1)

        # Verify the User Permission record has been deleted
        user_perm_deleted = not frappe.db.exists(
            "User Permission", {"user": "test_user_perm@example.com", "allow": "Company", "for_value": "DKSH"}
        )
        self.assertTrue(user_perm_deleted)
