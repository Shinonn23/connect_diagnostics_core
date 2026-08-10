# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext.employee import (
    format_national_id_display,
    has_valid_national_id_checksum,
)

TEST_FIRST_NAME = "_Test National ID Employee"


class TestFormatNationalIdDisplay(UnitTestCase):
    def test_formats_13_digits_with_dashes(self) -> None:
        self.assertEqual(format_national_id_display("3100400828611"), "3-1004-00828-61-1")


class TestHasValidNationalIdChecksum(UnitTestCase):
    def test_accepts_correct_check_digit(self) -> None:
        self.assertTrue(has_valid_national_id_checksum("3100400828611"))
        self.assertTrue(has_valid_national_id_checksum("1002003004007"))

    def test_rejects_incorrect_check_digit(self) -> None:
        self.assertFalse(has_valid_national_id_checksum("1234567890123"))


class TestNormalizeNationalId(IntegrationTestCase):
    """Exercises the ``Employee.validate`` hook against a real, saved Employee.

    Deliberately avoids ``erpnext.setup.doctype.employee.test_employee.make_employee``:
    importing it triggers ERPNext's generic test-fixture bootstrap (``BootStrapTestData``),
    which assumes a synthetic "All Departments" root that a real, already-populated site
    doesn't have. Reusing whatever Company/Department/Employment Type already exist keeps
    this test portable across a fresh CI site and a real dev site alike.
    """

    def setUp(self) -> None:
        super().setUp()

        # Look up a Department first and take its Company from the same row, rather than
        # picking a Company and a Department independently — an arbitrary Company may have
        # no Department of its own (e.g. a stray fixture left over from another test run).
        department_row = frappe.db.get_value("Department", {}, ["name", "company"], as_dict=True)
        employment_type = cast(str | None, frappe.db.get_value("Employment Type", {}, "name"))
        if not (department_row and employment_type):
            self.skipTest("No Department/Employment Type exists on this site to attach a test Employee to")
        company = cast(str, department_row.company)
        department = cast(str, department_row.name)

        # Avoid Redis-dependent frappe.delete_doc: no dynamic links to clean up here.
        frappe.db.delete("Employee", {"first_name": TEST_FIRST_NAME})

        self.employee = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": TEST_FIRST_NAME,
                    "company": company,
                    "department": department,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active",
                    "employment_type": employment_type,
                }
            ),
        )
        self.employee.insert()
        self.addCleanup(lambda: frappe.db.delete("Employee", {"name": self.employee.name}))

    def test_strips_dashes_and_computes_formatted_display(self) -> None:
        self.employee.set("national_id", "3-1004-00828-61-1")
        self.employee.save()

        self.assertEqual(self.employee.get("national_id"), "3100400828611")
        self.assertEqual(self.employee.get("national_id_display"), "3-1004-00828-61-1")

    def test_throws_when_not_13_digits(self) -> None:
        self.employee.set("national_id", "12345")

        self.assertRaises(frappe.ValidationError, self.employee.save)

    def test_throws_when_checksum_invalid(self) -> None:
        self.employee.set("national_id", "1234567890123")

        self.assertRaises(frappe.ValidationError, self.employee.save)

    def test_clears_display_when_national_id_emptied(self) -> None:
        self.employee.set("national_id", "1002003004007")
        self.employee.save()
        self.assertTrue(self.employee.get("national_id_display"))

        self.employee.set("national_id", "")
        self.employee.save()

        self.assertEqual(self.employee.get("national_id_display"), "")
