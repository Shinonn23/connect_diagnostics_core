# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import journal_entry_workflow


class TestJournalEntryWorkflowSetup(UnitTestCase):
    def test_exact_role_matrix_is_applied(self) -> None:
        with (
            patch.object(journal_entry_workflow, "setup_custom_perms") as setup_permissions,
            patch.object(journal_entry_workflow.frappe.db, "get_value", return_value=None),
            patch.object(journal_entry_workflow.frappe, "get_doc") as get_doc,
        ):
            permission = MagicMock()
            get_doc.return_value = permission
            journal_entry_workflow.ensure_configuration()

        setup_permissions.assert_called_once_with("Journal Entry")
        payloads = [call.args[0] for call in get_doc.call_args_list]
        self.assertEqual(
            [payload["role"] for payload in payloads], list(journal_entry_workflow.ROLE_PERMISSIONS)
        )
        for payload in payloads:
            self.assertEqual(
                {right: payload[right] for right in journal_entry_workflow.ROLE_PERMISSIONS[payload["role"]]},
                journal_entry_workflow.ROLE_PERMISSIONS[payload["role"]],
            )
