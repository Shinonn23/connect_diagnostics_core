# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

from frappe.tests import UnitTestCase
from frappe.utils import flt
from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS, _safe_eval

from connect_diagnostics_core.setup import payroll


class TestPayrollConfiguration(UnitTestCase):
    def _evaluate(self, **overrides: Any) -> dict[str, float]:
        values: dict[str, Any] = {
            "base": 3000,
            "RETRO": 0,
            payroll.PROVIDENT_FUND_RATE_FIELD: 7.5,
            payroll.SOCIAL_SECURITY_MEMBER_FIELD: 1,
            payroll.SOCIAL_SECURITY_WAGE_CEILING_FIELD: 17500,
            payroll.SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD: 5,
            payroll.SOCIAL_SECURITY_EMPLOYER_RATE_FIELD: 5,
        }
        values.update(overrides)
        evaluated: dict[str, float] = {}

        for abbreviation in ("BS", "PVD_BASE", "SSO_BASE", "PVD_EE", "SSO_EE", "PVD_ER", "SSO_ER"):
            policy = payroll.SALARY_COMPONENT_POLICIES[abbreviation]
            condition = cast(str, policy["condition"])
            if condition and not _safe_eval(condition, COMPONENT_EVAL_GLOBALS.copy(), values):
                continue
            amount = flt(
                _safe_eval(
                    cast(str, policy["formula"]),
                    COMPONENT_EVAL_GLOBALS.copy(),
                    values,
                ),
                2,
            )
            values[abbreviation] = amount
            evaluated[abbreviation] = amount

        return evaluated

    def test_pvd_and_social_security_formula_breakdown(self) -> None:
        evaluated = self._evaluate()

        self.assertEqual(evaluated["BS"], 3000)
        self.assertEqual(evaluated["PVD_BASE"], 3000)
        self.assertEqual(evaluated["PVD_EE"], 225)
        self.assertEqual(evaluated["PVD_ER"], 225)
        self.assertEqual(evaluated["SSO_BASE"], 3000)
        self.assertEqual(evaluated["SSO_EE"], 150)
        self.assertEqual(evaluated["SSO_ER"], 150)

    def test_social_security_ceiling_is_applied(self) -> None:
        evaluated = self._evaluate(base=20000, provident_fund_rate=0)

        self.assertEqual(evaluated["SSO_BASE"], 17500)
        self.assertEqual(evaluated["SSO_EE"], 875)
        self.assertEqual(evaluated["SSO_ER"], 875)
        self.assertNotIn("PVD_BASE", evaluated)
        self.assertNotIn("PVD_EE", evaluated)
        self.assertNotIn("PVD_ER", evaluated)

    def test_retro_is_included_in_contribution_bases(self) -> None:
        evaluated = self._evaluate(RETRO=500, provident_fund_rate=3)

        self.assertEqual(evaluated["PVD_BASE"], 3500)
        self.assertEqual(evaluated["PVD_EE"], 105)
        self.assertEqual(evaluated["SSO_BASE"], 3500)
        self.assertEqual(evaluated["SSO_EE"], 175)

    def test_non_social_security_member_has_no_social_components(self) -> None:
        evaluated = self._evaluate(social_security_member=0)

        self.assertNotIn("SSO_BASE", evaluated)
        self.assertNotIn("SSO_EE", evaluated)
        self.assertNotIn("SSO_ER", evaluated)

    def test_assignment_fields_fetch_company_defaults_as_snapshots(self) -> None:
        fields = {field["fieldname"]: field for field in payroll.CUSTOM_FIELDS[payroll.ASSIGNMENT_DOCTYPE]}

        for fieldname in (
            payroll.SOCIAL_SECURITY_WAGE_CEILING_FIELD,
            payroll.SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD,
            payroll.SOCIAL_SECURITY_EMPLOYER_RATE_FIELD,
        ):
            with self.subTest(fieldname=fieldname):
                self.assertEqual(fields[fieldname]["fetch_from"], f"company.{fieldname}")
                self.assertEqual(fields[fieldname]["fetch_if_empty"], 1)
                self.assertEqual(fields[fieldname]["no_copy"], 1)

    def test_formula_configuration_is_not_an_automatic_migration_side_effect(self) -> None:
        from connect_diagnostics_core.setup import apply_all

        self.assertNotIn("configure_salary_components", apply_all.__code__.co_names)
