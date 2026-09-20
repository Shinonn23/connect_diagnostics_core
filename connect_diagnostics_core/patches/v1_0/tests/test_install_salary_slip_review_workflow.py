# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import install_salary_slip_review_workflow
from connect_diagnostics_core.setup import payroll


class TestInstallSalarySlipReviewWorkflow(UnitTestCase):
    @patch.object(install_salary_slip_review_workflow, "ensure_salary_slip_review_workflow")
    @patch.object(install_salary_slip_review_workflow, "create_custom_fields")
    @patch.object(install_salary_slip_review_workflow.frappe.db, "sql")
    def test_installs_schema_workflow_and_backfills_existing_slips(
        self,
        sql: MagicMock,
        create_fields: MagicMock,
        ensure_workflow: MagicMock,
    ) -> None:
        install_salary_slip_review_workflow.execute()

        create_fields.assert_called_once_with(payroll.CUSTOM_FIELDS, ignore_validate=True)
        ensure_workflow.assert_called_once_with()
        self.assertEqual(
            sql.call_args_list,
            [
                call(
                    install_salary_slip_review_workflow._BACKFILL_QUERY,
                    (payroll.SALARY_SLIP_DRAFT_STATE, 0),
                ),
                call(
                    install_salary_slip_review_workflow._BACKFILL_QUERY,
                    (payroll.SALARY_SLIP_SUBMITTED_STATE, 1),
                ),
                call(
                    install_salary_slip_review_workflow._BACKFILL_QUERY,
                    (payroll.SALARY_SLIP_CANCELLED_STATE, 2),
                ),
            ],
        )
