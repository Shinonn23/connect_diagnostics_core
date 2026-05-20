# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import frappe
from frappe.tests.utils import FrappeTestCase

from ..employee import CustomEmployee


class TestCustomEmployeeAutonameUnit(FrappeTestCase):
    def _doc(self, series: str, joining: date | None) -> CustomEmployee:
        return cast(CustomEmployee, SimpleNamespace(naming_series=series, date_of_joining=joining))

    def test_throws_when_date_of_joining_is_missing(self):
        doc = self._doc("YY.MM.###", None)
        with self.assertRaises(frappe.ValidationError):
            CustomEmployee.autoname(doc)

    def test_replaces_YY_with_two_digit_year(self):
        doc = self._doc("YY.MM.###", date(2025, 3, 7))
        CustomEmployee.autoname(doc)
        self.assertIn("25", doc.naming_series)

    def test_replaces_MM_with_zero_padded_month(self):
        doc = self._doc("YY.MM.###", date(2025, 3, 7))
        CustomEmployee.autoname(doc)
        self.assertIn("03", doc.naming_series)

    def test_replaces_all_tokens_in_one_pass(self):
        doc = self._doc("YY.MM.###", date(2025, 3, 7))
        CustomEmployee.autoname(doc)
        self.assertEqual(doc.naming_series, "25.03.###")

    def test_replaces_YYYY_with_four_digit_year(self):
        doc = self._doc("YYYY.MM.###", date(2025, 3, 7))
        CustomEmployee.autoname(doc)
        self.assertTrue(doc.naming_series.startswith("2025."))

    def test_YYYY_replaced_before_YY_prevents_double_substitution(self):
        # If YY were replaced first, "YYYY" → "2525"; correct order gives "2025"
        doc = self._doc("YYYY.MM.###", date(2025, 3, 7))
        CustomEmployee.autoname(doc)
        self.assertIn("2025", doc.naming_series)
        self.assertNotIn("2525", doc.naming_series)


class TestCustomEmployeeNamingE2E(FrappeTestCase):
    """
    Verifies that Employee IDs reflect date_of_joining, not the current date.
    Series format (from property setter): "YY.MM.###" and "C.YY.MM.###".
    After token replacement for date(2025, 3, 7), Frappe collapses the
    `.` separators when generating the final name:
      "YY.MM.###"   → "25.03.###"   → Frappe generates  "2503001" …
      "C.YY.MM.###" → "C.25.03.###" → Frappe generates  "C2503001" …
    """

    def setUp(self):
        self._to_delete: list[tuple[str, str]] = []

    def tearDown(self):
        for doctype, name in self._to_delete:
            frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
        frappe.db.commit()

    def _insert_employee(self, **kwargs) -> frappe.Document:
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "_Test Naming",
                "status": "Active",
                "naming_series": "YY.MM.###",
                "date_of_joining": date(2025, 3, 7),
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        # pyrefly: ignore [bad-argument-type]
        self._to_delete.append(("Employee", doc.name))
        return doc

    def test_employee_id_reflects_joining_year_and_month(self):
        # date_of_joining = 2025-03 → name must start with "2503" (dots collapsed)
        doc = self._insert_employee(date_of_joining=date(2025, 3, 7))
        self.assertTrue(
            # pyrefly: ignore [missing-attribute]
            doc.name.startswith("2503"),
            f"Expected name to start with '2503' but got '{doc.name}'",
        )

    def test_contract_series_prefix_included_in_name(self):
        doc = self._insert_employee(
            naming_series="C.YY.MM.###",
            date_of_joining=date(2025, 3, 7),
        )
        self.assertTrue(
            # pyrefly: ignore [missing-attribute]
            doc.name.startswith("C2503"),
            f"Expected name to start with 'C2503' but got '{doc.name}'",
        )

    def test_different_joining_date_produces_different_prefix(self):
        doc_mar = self._insert_employee(date_of_joining=date(2025, 3, 1))
        doc_sep = self._insert_employee(date_of_joining=date(2025, 9, 1))
        # pyrefly: ignore [missing-attribute]
        self.assertTrue(doc_mar.name.startswith("2503"))
        # pyrefly: ignore [missing-attribute]
        self.assertTrue(doc_sep.name.startswith("2509"))
        # The joining-date prefix distinguishes IDs even within the same year
        # pyrefly: ignore [unsupported-operation]
        self.assertNotEqual(doc_mar.name[:4], doc_sep.name[:4])

    def test_missing_date_of_joining_raises_validation_error(self):
        # Our autoname calls frappe.throw when date_of_joining is absent
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "_Test Naming No Date",
                "status": "Active",
                "naming_series": "YY.MM.###",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_mandatory=True)
