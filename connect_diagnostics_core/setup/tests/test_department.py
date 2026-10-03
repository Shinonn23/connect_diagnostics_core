# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import department


class TestDepartmentCustomFields(UnitTestCase):
    def test_has_no_retired_accounting_department_link(self) -> None:
        self.assertEqual(department.CUSTOM_FIELDS, {})

    def test_fieldnames_are_unique(self) -> None:
        self.assertEqual(department.CUSTOM_FIELDS, {})
