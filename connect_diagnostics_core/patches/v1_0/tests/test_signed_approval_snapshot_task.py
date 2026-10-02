# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    add_signed_approval_snapshot_task,
    rollback_signed_approval_snapshot_task,
)


class TestSignedApprovalSnapshotTask(UnitTestCase):
    @patch.object(add_signed_approval_snapshot_task.frappe.db, "exists", return_value=True)
    @patch.object(add_signed_approval_snapshot_task.frappe, "get_doc")
    def test_existing_exact_task_is_reused(self, get_doc: MagicMock, _exists: MagicMock) -> None:
        get_doc.return_value.tasks = [
            MagicMock(task="Capture Print Action: Authorized", enabled=1, asynchronous=0)
        ]
        add_signed_approval_snapshot_task.execute()
        get_doc.return_value.insert.assert_not_called()

    @patch.object(add_signed_approval_snapshot_task.frappe.db, "exists", return_value=True)
    @patch.object(add_signed_approval_snapshot_task.frappe, "get_doc")
    def test_conflicting_task_stops(self, get_doc: MagicMock, _exists: MagicMock) -> None:
        get_doc.return_value.tasks = [MagicMock(task="Other", enabled=1, asynchronous=0)]
        with self.assertRaises(Exception):
            add_signed_approval_snapshot_task.execute()

    @patch.object(rollback_signed_approval_snapshot_task.frappe.db, "exists", return_value=True)
    @patch.object(rollback_signed_approval_snapshot_task.frappe, "delete_doc")
    @patch.object(rollback_signed_approval_snapshot_task.frappe, "get_doc")
    @patch.object(rollback_signed_approval_snapshot_task.frappe, "get_all", return_value=[])
    def test_recovery_deletes_exact_unreferenced_task(
        self, _get_all: MagicMock, get_doc: MagicMock, delete_doc: MagicMock, _exists: MagicMock
    ) -> None:
        get_doc.return_value.tasks = [
            MagicMock(task="Capture Print Action: Authorized", enabled=1, asynchronous=0)
        ]
        rollback_signed_approval_snapshot_task.execute()
        delete_doc.assert_called_once_with(
            "Workflow Transition Tasks", "Connect Signed Approval Snapshot", ignore_permissions=True
        )
