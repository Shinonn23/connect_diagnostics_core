# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import salary_slip
from connect_diagnostics_core.api.hrms import payroll_entry_workflow, payroll_output_review


class TestSalarySlipSubmissionGuard(UnitTestCase):
    """Salary Slip may only be submitted through Payroll Entry; no review workflow."""

    def setUp(self) -> None:
        super().setUp()
        self.slip = frappe._dict(name="_Test Salary Slip", payroll_entry="PAY-1")

    def test_rejects_direct_salary_slip_submit(self) -> None:
        with patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=False)):
            with self.assertRaises(frappe.ValidationError):
                salary_slip.validate_submission(cast(Document, self.slip))

    def test_flag_alone_does_not_authorize_slip_submit(self) -> None:
        with (
            patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=True)),
            patch.object(payroll_entry_workflow, "validate_downstream_operation") as validate,
            self.assertRaises(frappe.PermissionError),
        ):
            salary_slip.validate_submission(cast(Document, self.slip))
        validate.assert_not_called()

    def test_accepts_actual_reviewed_native_payroll_submission(self) -> None:
        pe = frappe._dict(workflow_state=payroll_output_review.REVIEWED, output_review_digest="sealed")
        with (
            patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=True)),
            patch.object(
                payroll_entry_workflow, "validate_downstream_operation", return_value=pe
            ) as validate,
            patch.object(payroll_output_review, "require_output_review", return_value=[self.slip]),
            patch.object(payroll_output_review, "output_digest", return_value="sealed"),
            payroll_output_review.native_operation("PAY-1", "submit"),
        ):
            salary_slip.validate_submission(cast(Document, self.slip))
        validate.assert_called_once_with("PAY-1", require_current_digest=False)

    def test_creation_rechecks_approved_payroll_entry(self) -> None:
        pe = frappe._dict(workflow_state=payroll_output_review.SUBMITTED)
        with (
            patch.object(
                payroll_entry_workflow, "validate_downstream_operation", return_value=pe
            ) as validate,
            payroll_output_review.native_operation("PAY-1", "create"),
        ):
            salary_slip.validate_creation(cast(Document, self.slip))
        validate.assert_called_once_with("PAY-1")

    def test_direct_linked_creation_without_native_operation_is_denied(self) -> None:
        pe = frappe._dict(workflow_state=payroll_output_review.SUBMITTED)
        with (
            patch.object(payroll_entry_workflow, "validate_downstream_operation", return_value=pe),
            self.assertRaises(frappe.PermissionError),
        ):
            salary_slip.validate_creation(cast(Document, self.slip))

    def test_creation_without_payroll_entry_remains_native(self) -> None:
        self.slip.payroll_entry = None
        with patch.object(payroll_entry_workflow, "validate_downstream_operation") as validate:
            salary_slip.validate_creation(cast(Document, self.slip))
        validate.assert_not_called()
