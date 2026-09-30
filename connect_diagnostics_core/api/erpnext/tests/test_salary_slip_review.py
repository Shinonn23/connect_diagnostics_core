# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import salary_slip
from connect_diagnostics_core.api.hrms import payroll_entry_workflow


class TestSalarySlipSubmissionGuard(UnitTestCase):
    """Salary Slip may only be submitted through Payroll Entry; no review workflow."""

    def setUp(self) -> None:
        super().setUp()
        self.slip = frappe._dict(name="_Test Salary Slip", payroll_entry="PAY-1")

    def test_rejects_direct_salary_slip_submit(self) -> None:
        with patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=False)):
            with self.assertRaises(frappe.ValidationError):
                salary_slip.validate_submission(cast(Document, self.slip))

    def test_accepts_slip_from_payroll_entry(self) -> None:
        with (
            patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=True)),
            patch.object(payroll_entry_workflow, "validate_downstream_operation") as validate,
        ):
            salary_slip.validate_submission(cast(Document, self.slip))
        validate.assert_called_once_with("PAY-1")

    def test_creation_rechecks_approved_payroll_entry(self) -> None:
        with patch.object(payroll_entry_workflow, "validate_downstream_operation") as validate:
            salary_slip.validate_creation(cast(Document, self.slip))
        validate.assert_called_once_with("PAY-1")

    def test_creation_without_payroll_entry_remains_native(self) -> None:
        self.slip.payroll_entry = None
        with patch.object(payroll_entry_workflow, "validate_downstream_operation") as validate:
            salary_slip.validate_creation(cast(Document, self.slip))
        validate.assert_not_called()
