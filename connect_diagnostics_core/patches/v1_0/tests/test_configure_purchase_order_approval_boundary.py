# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import configure_purchase_order_approval_boundary as patch_module


class TestConfigurePurchaseOrderApprovalBoundary(UnitTestCase):
    def _execute_with_valid_runtime(self) -> tuple[MagicMock, MagicMock]:
        meta = MagicMock(queue_in_background=False)
        workflow = MagicMock()
        with (
            patch.object(patch_module, "_ensure_no_open_procurement_actions"),
            patch.object(patch_module, "_validate_tasks"),
            patch.object(patch_module.frappe, "get_meta", return_value=meta),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=["Purchase User", "Purchase Manager", "C-Level Approver"],
            ),
            patch.object(patch_module.frappe, "get_doc", return_value=workflow),
        ):
            patch_module.execute()
        return meta, workflow

    def test_target_fixture_matches_reviewed_fingerprint_and_tasks(self) -> None:
        fixture_path = Path(__file__).parents[3] / "fixtures" / "workflow.json"
        workflow = next(
            row
            for row in json.loads(fixture_path.read_text())
            if row["name"] == patch_module.PURCHASE_ORDER_WORKFLOW
        )
        self.assertEqual(
            patch_module._workflow_fingerprint(workflow),
            patch_module.TARGET_PO_FINGERPRINT,
        )
        actual = {
            (row["state"], row["action"], row["next_state"]): row.get("transition_tasks")
            for row in workflow["transitions"]
        }
        self.assertEqual(actual, patch_module.EXPECTED_TRANSITION_TASKS)

    @patch.object(patch_module.frappe, "get_all")
    def test_open_procurement_action_stops_before_configuration_writes(self, get_all: MagicMock) -> None:
        get_all.return_value = [
            {
                "name": "ACTION-1",
                "reference_doctype": "Purchase Order",
                "reference_name": "PO-1",
            }
        ]
        with self.assertRaises(frappe.ValidationError):
            patch_module._ensure_no_open_procurement_actions()

    @patch.object(patch_module, "_ensure_task")
    @patch.object(patch_module, "_workflow_exists", return_value=False)
    @patch.object(patch_module, "_ensure_no_open_procurement_actions")
    @patch.object(patch_module, "_validate_tasks")
    @patch.object(
        patch_module.frappe, "get_all", return_value=["Purchase User", "Purchase Manager", "C-Level Approver"]
    )
    @patch.object(patch_module.frappe, "get_meta")
    def test_fresh_install_is_supported_on_any_site(
        self,
        get_meta: MagicMock,
        _get_all: MagicMock,
        _validate_tasks: MagicMock,
        _ensure_no_open_procurement_actions: MagicMock,
        _workflow_exists: MagicMock,
        ensure_task: MagicMock,
    ) -> None:
        get_meta.return_value.queue_in_background = False
        with patch.object(patch_module.frappe.local, "site", "deverp.connectdiagnostics.net"):
            patch_module.execute()
        self.assertEqual(ensure_task.call_count, len(patch_module.TASKS))

    def test_populated_upgrade_captures_snapshot_and_preserves_history(self) -> None:
        with (
            patch.object(patch_module, "_workflow_exists", return_value=True),
            patch.object(
                patch_module,
                "_get_workflow_fingerprint",
                side_effect=[
                    patch_module.BASELINE_PO_FINGERPRINT,
                    patch_module.BASELINE_MR_FINGERPRINT,
                ],
            ),
            patch.object(patch_module, "_save_recovery_snapshot") as save_snapshot,
            patch.object(patch_module, "_ensure_task") as ensure_task,
            patch.object(patch_module.frappe, "delete_doc") as delete_doc,
        ):
            _meta, workflow = self._execute_with_valid_runtime()

        save_snapshot.assert_called_once_with()
        self.assertEqual(ensure_task.call_count, len(patch_module.TASKS))
        workflow.save.assert_called_once_with(ignore_permissions=True)
        delete_doc.assert_not_called()

    def test_target_route_without_legacy_material_request_is_idempotent(self) -> None:
        with (
            patch.object(patch_module, "_workflow_exists", side_effect=[True, False]),
            patch.object(
                patch_module,
                "_get_workflow_fingerprint",
                return_value=patch_module.TARGET_PO_FINGERPRINT,
            ),
            patch.object(patch_module, "_ensure_task") as ensure_task,
            patch.object(patch_module, "_save_recovery_snapshot") as save_snapshot,
        ):
            self._execute_with_valid_runtime()

        self.assertEqual(ensure_task.call_count, len(patch_module.TASKS))
        save_snapshot.assert_not_called()

    def test_unreviewed_collision_stops_before_writes(self) -> None:
        with (
            patch.object(patch_module, "_workflow_exists", return_value=True),
            patch.object(
                patch_module,
                "_get_workflow_fingerprint",
                side_effect=["unexpected", patch_module.BASELINE_MR_FINGERPRINT],
            ),
            patch.object(patch_module, "_save_recovery_snapshot") as save_snapshot,
            patch.object(patch_module, "_ensure_task") as ensure_task,
            self.assertRaises(frappe.ValidationError),
        ):
            self._execute_with_valid_runtime()

        save_snapshot.assert_not_called()
        ensure_task.assert_not_called()

    def test_task_collision_stops_before_recovery_snapshot_write(self) -> None:
        meta = MagicMock(queue_in_background=False)
        with (
            patch.object(patch_module, "_ensure_no_open_procurement_actions"),
            patch.object(patch_module.frappe, "get_meta", return_value=meta),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=["Purchase User", "Purchase Manager", "C-Level Approver"],
            ),
            patch.object(patch_module, "_validate_tasks", side_effect=frappe.ValidationError),
            patch.object(patch_module, "_save_recovery_snapshot") as save_snapshot,
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module.execute()

        save_snapshot.assert_not_called()

    def test_recovery_missing_snapshot_never_deletes_history(self) -> None:
        from connect_diagnostics_core.patches.v1_0 import (
            rollback_purchase_order_approval_boundary as rollback,
        )

        with (
            patch.object(rollback, "_ensure_no_open_procurement_actions"),
            patch.object(
                rollback,
                "_get_workflow_fingerprint",
                side_effect=[patch_module.TARGET_PO_FINGERPRINT, patch_module.INACTIVE_MR_FINGERPRINT],
            ),
            patch.object(rollback.frappe.db, "get_value", return_value=None),
            patch.object(rollback.frappe.db, "delete") as delete,
            self.assertRaises(frappe.ValidationError),
        ):
            rollback.execute()
        delete.assert_not_called()

    def test_recovery_rejects_snapshot_without_populated_baseline(self) -> None:
        from connect_diagnostics_core.patches.v1_0 import (
            rollback_purchase_order_approval_boundary as rollback,
        )

        snapshot_file = MagicMock()
        snapshot_file.get_content.return_value = json.dumps(
            {
                "schema_version": patch_module.RECOVERY_SCHEMA_VERSION,
                "site": "local.test",
                "workflows": {patch_module.PURCHASE_ORDER_WORKFLOW: {}},
                "transition_tasks": dict.fromkeys(patch_module.TASKS),
            }
        )
        with (
            patch.object(rollback.frappe.local, "site", "local.test"),
            patch.object(rollback.frappe.db, "get_value", return_value="FILE-1"),
            patch.object(rollback.frappe, "get_doc", return_value=snapshot_file),
            self.assertRaises(frappe.ValidationError),
        ):
            rollback._load_recovery_snapshot()

    def test_task_contract_is_synchronous_and_complete(self) -> None:
        referenced = {task for task in patch_module.EXPECTED_TRANSITION_TASKS.values() if task}
        self.assertEqual(referenced, set(patch_module.TASKS))
