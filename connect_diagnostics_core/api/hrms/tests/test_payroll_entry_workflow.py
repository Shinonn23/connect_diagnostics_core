# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.hrms.payroll_entry_workflow import PayrollEntryWorkflowMixin


class _NativePayroll:
    def make_journal_entry(self, *args, **kwargs):
        return kwargs


class _Payroll(PayrollEntryWorkflowMixin, _NativePayroll):
    pass


class TestPayrollEntryWorkflow(UnitTestCase):
    def test_accrual_generation_is_kept_as_draft(self) -> None:
        result = _Payroll().make_journal_entry(submit_journal_entry=True)
        self.assertFalse(result["submit_journal_entry"])
