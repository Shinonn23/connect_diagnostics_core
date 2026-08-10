# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.payroll_entry import PayrollEntryAccountingDimensionMixin


class _PayrollEntryDouble:
    """Stands in for a Payroll Entry document, exposing only field-value lookups.

    The mixin delegates to HRMS's real ``PayrollEntry.update_accounting_dimensions``,
    which reads dimension values via ``self.get`` — the only method it needs here.
    """

    def __init__(self, **values: Any) -> None:
        self._values = values

    def get(self, key: str) -> Any:
        return self._values.get(key)


class _ExtendedPayrollEntry(PayrollEntryAccountingDimensionMixin, _PayrollEntryDouble):
    pass


class TestPayrollEntryAccountingDimensionMixin(UnitTestCase):
    def test_department_dimension_is_blanked_not_taken_from_hr_department(self) -> None:
        entry = cast(Any, _ExtendedPayrollEntry(department="_Test HR Dept - _TC"))
        row = entry.update_accounting_dimensions({}, ["department"])
        self.assertIsNone(row["department"])

    def test_other_dimensions_pass_through_unchanged(self) -> None:
        entry = cast(Any, _ExtendedPayrollEntry(cost_center="_Test Cost Center - _TC"))
        row = entry.update_accounting_dimensions({}, ["cost_center"])
        self.assertEqual(row["cost_center"], "_Test Cost Center - _TC")

    def test_department_is_blanked_while_siblings_are_preserved(self) -> None:
        entry = cast(
            Any,
            _ExtendedPayrollEntry(department="_Test HR Dept - _TC", cost_center="_Test Cost Center - _TC"),
        )
        row = entry.update_accounting_dimensions({}, ["cost_center", "department"])
        self.assertEqual(row["cost_center"], "_Test Cost Center - _TC")
        self.assertIsNone(row["department"])
