# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import frappe
from frappe import _dict
from frappe.model.naming import parse_naming_series
from frappe.tests.utils import FrappeTestCase, patch_hooks

from ..employee import parse_buddhist_era_naming_series_variable


class TestEmployeeBuddhistEraNamingSeriesUnit(FrappeTestCase):
    def test_replaces_YY_BE_with_two_digit_buddhist_year(self):
        doc = _dict(date_of_joining=date(2025, 3, 7))
        self.assertEqual(parse_buddhist_era_naming_series_variable(doc, "YY-BE"), "68")

    def test_replaces_YYYY_BE_with_four_digit_buddhist_year(self):
        doc = _dict(date_of_joining=date(2025, 3, 7))
        self.assertEqual(parse_buddhist_era_naming_series_variable(doc, "YYYY-BE"), "2568")

    def test_accepts_date_string_from_form_payloads(self):
        doc = SimpleNamespace(date_of_joining="2026-05-04")
        self.assertEqual(parse_buddhist_era_naming_series_variable(doc, "YY-BE"), "69")


class TestCustomEmployeeNamingE2E(FrappeTestCase):
    """
    Verifies that Employee IDs use the standard naming_series engine with
    Buddhist Era year variables instead of a custom Employee.autoname override.
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
                "naming_series": "YY-BE.MM.###",
                "date_of_joining": date(2025, 3, 7),
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        # pyrefly: ignore [bad-argument-type]
        self._to_delete.append(("Employee", doc.name))
        return doc

    def test_employee_id_reflects_joining_buddhist_year(self):
        doc = self._insert_employee(date_of_joining=date(2025, 3, 7))
        self.assertTrue(
            # pyrefly: ignore [missing-attribute]
            doc.name.startswith("68"),
            f"Expected name to start with '68' but got '{doc.name}'",
        )

    def test_contract_series_prefix_included_in_name(self):
        doc = self._insert_employee(
            naming_series="C.YY-BE.MM.###",
            date_of_joining=date(2025, 3, 7),
        )
        self.assertTrue(
            # pyrefly: ignore [missing-attribute]
            doc.name.startswith("C68"),
            f"Expected name to start with 'C68' but got '{doc.name}'",
        )

    def test_different_joining_year_produces_different_prefix(self):
        doc_2025 = self._insert_employee(date_of_joining=date(2025, 3, 1))
        doc_2026 = self._insert_employee(date_of_joining=date(2026, 9, 1))
        # pyrefly: ignore [missing-attribute]
        self.assertTrue(doc_2025.name.startswith("68"))
        # pyrefly: ignore [missing-attribute]
        self.assertTrue(doc_2026.name.startswith("69"))
        # pyrefly: ignore [unsupported-operation]
        self.assertNotEqual(doc_2025.name[:2], doc_2026.name[:2])

    def test_standard_naming_series_parser_uses_be_variables(self):
        doc = _dict(date_of_joining=date(2025, 3, 7))

        def generate_number(_prefix, _digits):
            return "001"

        with patch_hooks(
            {
                "naming_series_variables": {
                    "YY-BE": [
                        "connect_diagnostics_core.api.erpnext.employee.parse_buddhist_era_naming_series_variable"
                    ],
                },
            }
        ):
            self.assertEqual(
                # pyrefly: ignore [bad-argument-type]
                parse_naming_series("YY-BE.###", doc=doc, number_generator=generate_number),
                "68001",
            )
