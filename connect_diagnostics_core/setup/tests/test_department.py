# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import department


class TestDepartmentCustomFields(UnitTestCase):
    def _field(self, fieldname: str) -> dict[str, str | int]:
        return next(
            field for field in department.CUSTOM_FIELDS["Department"] if field["fieldname"] == fieldname
        )

    def test_accounting_department_links_to_accounting_department_doctype(self) -> None:
        field = self._field("accounting_department")
        self.assertEqual(field["fieldtype"], "Link")
        self.assertEqual(field["options"], "Accounting Department")

    def test_accounting_department_follows_payroll_cost_center(self) -> None:
        field = self._field("accounting_department")
        self.assertEqual(field["insert_after"], "payroll_cost_center")

    def test_fieldnames_are_unique(self) -> None:
        fieldnames = [field["fieldname"] for field in department.CUSTOM_FIELDS["Department"]]
        self.assertEqual(len(fieldnames), len(set(fieldnames)))
