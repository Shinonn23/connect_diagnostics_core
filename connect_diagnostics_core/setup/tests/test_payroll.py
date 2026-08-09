# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from itertools import pairwise
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import payroll

# Mirror the subset of the HRMS component-formula globals the formulas rely on.
FORMULA_GLOBALS = {"min": min, "max": max}


class TestPayrollComponents(UnitTestCase):
    def test_component_names_are_unique(self) -> None:
        names = [name for name, _type, _flags in payroll.SALARY_COMPONENTS]

        self.assertEqual(len(names), len(set(names)))

    def test_component_types_are_valid(self) -> None:
        for name, component_type, _flags in payroll.SALARY_COMPONENTS:
            with self.subTest(component=name):
                self.assertIn(component_type, ("Earning", "Deduction"))

    def test_withholding_tax_is_variable_based_on_taxable_salary(self) -> None:
        flags = self._flags("Withholding Tax")

        self.assertEqual(flags.get("variable_based_on_taxable_salary"), 1)
        self.assertNotIn("formula", flags)

    def _flags(self, component: str) -> dict:
        return next(f for name, _type, f in payroll.SALARY_COMPONENTS if name == component)


class TestSocialSecurityFormula(UnitTestCase):
    def _sso(self, base: float) -> float:
        return eval(payroll.SSO_FORMULA, FORMULA_GLOBALS, {"base": base})

    def test_below_ceiling_is_five_percent_of_base(self) -> None:
        self.assertEqual(self._sso(10000), 500)

    def test_at_or_above_ceiling_is_capped(self) -> None:
        self.assertEqual(self._sso(17500), 875)
        self.assertEqual(self._sso(40000), 875)

    def test_ceiling_helper_matches_max_contribution(self) -> None:
        self.assertEqual(payroll.sso_ceiling_amount(), 875)


class TestProvidentFundFormula(UnitTestCase):
    def _pf(self, base: float, rate: float | None) -> float:
        return eval(
            payroll.PROVIDENT_FUND_FORMULA,
            FORMULA_GLOBALS,
            {"base": base, "provident_fund_rate": rate},
        )

    def test_rate_is_applied_per_employee(self) -> None:
        self.assertEqual(self._pf(10000, 3), 300)
        self.assertEqual(self._pf(10000, 7.5), 750)

    def test_missing_rate_yields_zero(self) -> None:
        self.assertEqual(self._pf(10000, None), 0)
        self.assertEqual(self._pf(10000, 0), 0)


class TestIncomeTaxSlab(UnitTestCase):
    def test_standard_exemption_folds_personal_and_expense(self) -> None:
        self.assertEqual(payroll.STANDARD_TAX_EXEMPTION_AMOUNT, 160000)

    def test_slabs_start_at_zero_and_are_contiguous(self) -> None:
        self.assertEqual(payroll.INCOME_TAX_SLABS[0][0], 0)
        for (_prev_from, prev_to, _p), (next_from, _next_to, _np) in pairwise(payroll.INCOME_TAX_SLABS):
            self.assertEqual(prev_to, next_from)

    def test_percentages_are_non_decreasing(self) -> None:
        percents = [percent for _from, _to, percent in payroll.INCOME_TAX_SLABS]

        self.assertEqual(percents, sorted(percents))
        self.assertEqual(percents[0], 0)
        self.assertEqual(percents[-1], 35)


class TestSalaryStructureWiring(UnitTestCase):
    def test_structure_components_are_defined_components(self) -> None:
        defined = {name for name, _type, _flags in payroll.SALARY_COMPONENTS}

        for component in (*payroll.STRUCTURE_EARNINGS, *payroll.STRUCTURE_DEDUCTIONS):
            with self.subTest(component=component):
                self.assertIn(component, defined)

    def test_structure_row_carries_formula_flag(self) -> None:
        row = payroll._structure_row("Social Security")

        self.assertEqual(row["salary_component"], "Social Security")
        self.assertEqual(row["amount_based_on_formula"], 1)
        self.assertEqual(row["formula"], payroll.SSO_FORMULA)

    def test_structure_row_carries_variable_tax_flag(self) -> None:
        row = payroll._structure_row("Withholding Tax")

        self.assertEqual(row["variable_based_on_taxable_salary"], 1)


class TestEnsurePayrollPeriod(UnitTestCase):
    # `today` is stubbed so the real timezone lookup (which caches System Settings
    # via frappe.get_doc) is not reached while frappe.get_doc is patched.
    @patch.object(payroll, "today", return_value=date(2026, 1, 15))
    @patch.object(payroll.frappe, "get_doc")
    @patch.object(payroll.frappe, "get_all")
    def test_skips_creation_when_an_overlapping_period_exists(
        self, get_all: MagicMock, get_doc: MagicMock, _today: MagicMock
    ) -> None:
        get_all.return_value = [{"name": "งวดเงินเดือน 2569 (สำหรับทดสอบ)"}]

        payroll.ensure_payroll_period("_Test Company")

        get_doc.assert_not_called()

    @patch.object(payroll, "today", return_value=date(2026, 1, 15))
    @patch.object(payroll.frappe, "get_doc")
    @patch.object(payroll.frappe, "get_all")
    def test_creates_period_when_none_overlaps(
        self, get_all: MagicMock, get_doc: MagicMock, _today: MagicMock
    ) -> None:
        get_all.return_value = []

        payroll.ensure_payroll_period("_Test Company")

        get_doc.assert_called_once()
