# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Definition-of-Done guardrails for the custom-workflow reset.

The app must own no Frappe Workflow and must not recreate one on migrate. These
tests fail loudly if workflow provisioning is reintroduced.
"""

from __future__ import annotations

import importlib

from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.setup import customer_onboarding, payroll, procure_to_pay, regulatory


class TestWorkflowReset(UnitTestCase):
    def test_hooks_declare_no_workflow_fixtures(self) -> None:
        fixture_doctypes = {
            entry["doctype"] if isinstance(entry, dict) else entry for entry in hooks.fixtures
        }
        for doctype in ("Workflow", "Workflow State", "Workflow Action Master"):
            self.assertNotIn(doctype, fixture_doctypes)

    def test_workflow_helper_module_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("connect_diagnostics_core.api.erpnext.workflow")

    def test_payment_approval_setup_module_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("connect_diagnostics_core.setup.payment_approval")

    def test_setup_modules_expose_no_workflow_provisioning(self) -> None:
        for module in (customer_onboarding, payroll, procure_to_pay, regulatory):
            for attr in ("ensure_workflow", "ensure_workflow_masters", "ensure_salary_slip_review_workflow"):
                self.assertFalse(
                    hasattr(module, attr),
                    msg=f"{module.__name__} still exposes {attr}",
                )
