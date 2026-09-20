# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payroll_entry, salary_slip
from connect_diagnostics_core.setup import payroll


class TestSalarySlipSubmissionGuard(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.slip = frappe._dict(
            name="_Test Salary Slip", salary_slip_review_state=payroll.SALARY_SLIP_REVIEWED_STATE
        )

    def test_rejects_direct_salary_slip_submit(self) -> None:
        with patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=False)):
            with self.assertRaises(frappe.ValidationError):
                salary_slip.validate_submission(cast(Document, self.slip))

    def test_accepts_reviewed_slip_from_payroll_entry(self) -> None:
        with patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=True)):
            salary_slip.validate_submission(cast(Document, self.slip))

    def test_rejects_unreviewed_slip_from_payroll_entry(self) -> None:
        self.slip.salary_slip_review_state = payroll.SALARY_SLIP_DRAFT_STATE

        with patch.object(salary_slip.frappe, "flags", frappe._dict(via_payroll_entry=True)):
            with self.assertRaises(frappe.ValidationError):
                salary_slip.validate_submission(cast(Document, self.slip))


class TestPayrollEntryReviewGate(UnitTestCase):
    @patch.object(payroll_entry.frappe, "get_desk_link", side_effect=lambda _doctype, name: name)
    @patch.object(payroll_entry.frappe.qb, "from_")
    def test_rejects_batch_with_unreviewed_salary_slips(
        self, from_: MagicMock, _get_desk_link: MagicMock
    ) -> None:
        from_.return_value.select.return_value.where.return_value.orderby.return_value.run.return_value = [
            "SS-0001",
            "SS-0002",
        ]

        with self.assertRaises(frappe.ValidationError):
            payroll_entry.validate_salary_slip_reviews("PE-0001")

    @patch.object(payroll_entry.frappe.qb, "from_")
    def test_accepts_batch_when_every_salary_slip_is_reviewed(self, from_: MagicMock) -> None:
        from_.return_value.select.return_value.where.return_value.orderby.return_value.run.return_value = []

        payroll_entry.validate_salary_slip_reviews("PE-0001")

    @patch.object(payroll_entry, "submit_hrms_salary_slips_for_employees")
    @patch.object(payroll_entry, "validate_salary_slip_reviews")
    def test_worker_rechecks_reviews_before_hrms_submission(
        self, validate_reviews: MagicMock, submit_hrms: MagicMock
    ) -> None:
        entry = MagicMock()
        entry.name = "PE-0001"
        slips = [("SS-0001", "_Test Structure")]

        payroll_entry.submit_reviewed_salary_slips_for_employees(entry, slips, publish_progress=False)

        validate_reviews.assert_called_once_with("PE-0001")
        submit_hrms.assert_called_once_with(entry, slips, publish_progress=False)

    @patch.object(payroll_entry, "submit_reviewed_salary_slips_for_employees")
    @patch.object(payroll_entry, "validate_salary_slip_reviews")
    @patch.object(payroll_entry, "frappe")
    def test_sync_submit_preflights_before_submitting(
        self,
        mocked_frappe: MagicMock,
        validate_reviews: MagicMock,
        submit_reviewed: MagicMock,
    ) -> None:
        mocked_frappe.flags.enqueue_payroll_entry = False
        entry = MagicMock()
        entry.name = "PE-0001"
        slips = [("SS-0001", "_Test Structure")]
        entry.get_sal_slip_list.return_value = slips

        payroll_entry.PayrollEntryReviewMixin.submit_salary_slips(cast(payroll_entry.PayrollEntry, entry))

        entry.check_permission.assert_called_once_with("write")
        validate_reviews.assert_called_once_with("PE-0001")
        submit_reviewed.assert_called_once_with(entry, slips, publish_progress=False)


class TestSalarySlipWorkflowDefinition(UnitTestCase):
    def test_workflow_has_no_user_submit_transition(self) -> None:
        submitted_transitions = [
            transition
            for transition in payroll.SALARY_SLIP_WORKFLOW_TRANSITIONS
            if transition["next_state"] == payroll.SALARY_SLIP_SUBMITTED_STATE
        ]

        self.assertEqual(submitted_transitions, [])

    def test_workflow_has_review_and_return_transitions(self) -> None:
        transitions = {
            (transition["state"], transition["next_state"])
            for transition in payroll.SALARY_SLIP_WORKFLOW_TRANSITIONS
        }

        self.assertIn((payroll.SALARY_SLIP_DRAFT_STATE, payroll.SALARY_SLIP_REVIEWED_STATE), transitions)
        self.assertIn((payroll.SALARY_SLIP_REVIEWED_STATE, payroll.SALARY_SLIP_DRAFT_STATE), transitions)
