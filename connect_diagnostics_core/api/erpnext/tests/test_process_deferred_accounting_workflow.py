# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.process_deferred_accounting_workflow import (
    ProcessDeferredAccountingWorkflowMixin,
)


class _NativeDeferred:
    def on_submit(self):
        return None


class _Deferred(ProcessDeferredAccountingWorkflowMixin, _NativeDeferred):
    doctype = "Process Deferred Accounting"
    name = "PDA-1"
    posting_date = "2026-01-01"


class TestProcessDeferredAccountingWorkflow(UnitTestCase):
    @patch("connect_diagnostics_core.api.erpnext.process_deferred_accounting_workflow.frappe")
    def test_source_is_locked_and_context_is_deterministic(self, frappe_mock: MagicMock) -> None:
        deferred = _Deferred()
        deferred.on_submit()
        frappe_mock.db.get_value.assert_called_once_with(
            "Process Deferred Accounting", "PDA-1", "name", for_update=True
        )
