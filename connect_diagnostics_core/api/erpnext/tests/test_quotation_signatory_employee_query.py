# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import quotation
from connect_diagnostics_core.setup import quotation as quotation_setup

TEST_FIRST_NAME_SALES = "_Test Signatory Sales"
TEST_FIRST_NAME_OTHER = "_Test Signatory Other"
TEST_SALES_USER_EMAIL = "_test_signatory_sales@example.com"
TEST_OTHER_USER_EMAIL = "_test_signatory_other@example.com"


class TestSignatoryEmployeeQuery(IntegrationTestCase):
    """Exercises signatory_employee_query against real Employee/User/Has Role rows.

    Deliberately avoids ERPNext's generic Employee test fixtures -- same
    rationale as test_employee.py's TestNormalizeNationalId: reuse whatever
    Company/Department/Employment Type already exist, so this test is portable
    across a fresh CI site and a real dev site alike.
    """

    def setUp(self) -> None:
        super().setUp()
        department_row = frappe.db.get_value("Department", {}, ["name", "company"], as_dict=True)
        employment_type = cast(str | None, frappe.db.get_value("Employment Type", {}, "name"))
        if not (department_row and employment_type):
            self.skipTest("No Department/Employment Type exists on this site to attach a test Employee to")
        company = cast(str, department_row.company)
        department = cast(str, department_row.name)

        sales_user = self._make_user(TEST_SALES_USER_EMAIL, ("Sales User",))
        other_user = self._make_user(TEST_OTHER_USER_EMAIL, ())

        self.sales_employee = self._make_employee(
            TEST_FIRST_NAME_SALES, company, department, employment_type, sales_user
        )
        self.other_employee = self._make_employee(
            TEST_FIRST_NAME_OTHER, company, department, employment_type, other_user
        )

    def _make_user(self, email: str, roles: tuple[str, ...]) -> str:
        frappe.db.delete("Has Role", {"parent": email})
        frappe.db.delete("User", {"name": email})
        user = cast(
            Document,
            frappe.get_doc({"doctype": "User", "email": email, "first_name": email, "send_welcome_email": 0}),
        )
        user.insert(ignore_permissions=True)
        if roles:
            for role in roles:
                user.append("roles", {"role": role})
            user.save(ignore_permissions=True)
        self.addCleanup(lambda: frappe.db.delete("Has Role", {"parent": email}))
        self.addCleanup(lambda: frappe.db.delete("User", {"name": email}))
        return email

    def _make_employee(
        self, first_name: str, company: str, department: str, employment_type: str, user_id: str
    ) -> str:
        frappe.db.delete("Employee", {"first_name": first_name})
        employee = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": first_name,
                    "company": company,
                    "department": department,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active",
                    "employment_type": employment_type,
                    "user_id": user_id,
                }
            ),
        )
        employee.insert()
        self.addCleanup(lambda: frappe.db.delete("Employee", {"name": employee.name}))
        return cast(str, employee.name)

    def test_sales_representative_type_includes_the_sales_user_employee(self) -> None:
        results = quotation.signatory_employee_query(
            "Employee",
            "",
            "name",
            0,
            20,
            {"quotation_signatory_type": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE},
        )

        names = [row[0] for row in results]
        self.assertIn(self.sales_employee, names)
        self.assertNotIn(self.other_employee, names)

    def test_managing_director_type_excludes_the_sales_user_only_employee(self) -> None:
        results = quotation.signatory_employee_query(
            "Employee",
            "",
            "name",
            0,
            20,
            {"quotation_signatory_type": quotation_setup.SIGNATORY_MANAGING_DIRECTOR},
        )

        names = [row[0] for row in results]
        self.assertNotIn(self.sales_employee, names)
        self.assertNotIn(self.other_employee, names)

    def test_unknown_signatory_type_returns_no_results(self) -> None:
        results = quotation.signatory_employee_query(
            "Employee", "", "name", 0, 20, {"quotation_signatory_type": ""}
        )

        self.assertEqual(results, [])
