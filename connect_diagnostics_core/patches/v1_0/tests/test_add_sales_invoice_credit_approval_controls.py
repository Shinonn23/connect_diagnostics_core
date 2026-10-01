# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_sales_invoice_credit_approval_controls as patch_module
from connect_diagnostics_core.patches.v1_0 import (
    rollback_add_sales_invoice_credit_approval_controls as rollback_module,
)


class TestSalesInvoiceCreditMigration(UnitTestCase):
    roles: ClassVar[list[str]] = [
        "Sales User",
        "Accounts User",
        "Sales Manager",
        "Accounts Manager",
        "C-Level Approver",
    ]

    @patch.object(patch_module.frappe, "get_all", return_value=["Other Workflow"])
    def test_foreign_active_workflow_stops_before_any_write(self, get_all: Mock) -> None:
        with (
            patch.object(patch_module, "_validate_tasks") as validate_tasks,
            patch.object(patch_module, "_ensure_tasks") as ensure_tasks,
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module.execute()
        self.assertEqual(
            get_all.call_args_list[0],
            call(
                "Workflow",
                filters={"document_type": patch_module.DOCTYPE, "is_active": 1},
                pluck="name",
            ),
        )
        validate_tasks.assert_not_called()
        ensure_tasks.assert_not_called()

    @patch.object(patch_module, "_ensure_tasks")
    @patch.object(patch_module, "_validate_tasks")
    @patch.object(patch_module, "_ensure_no_live_route_usage")
    @patch.object(patch_module.frappe, "get_meta", return_value=SimpleNamespace(queue_in_background=0))
    @patch.object(patch_module.frappe, "get_all")
    @patch.object(patch_module.frappe.db, "exists", return_value=None)
    def test_missing_fixture_allows_fixture_sync_after_full_preflight(
        self,
        exists: Mock,
        get_all: Mock,
        get_meta: Mock,
        ensure_no_live_route_usage: Mock,
        validate_tasks: Mock,
        ensure_tasks: Mock,
    ) -> None:
        get_all.side_effect = [[], self.roles]
        patch_module.execute()
        validate_tasks.assert_called_once_with()
        ensure_no_live_route_usage.assert_called_once_with()
        ensure_tasks.assert_called_once_with()

    @patch.object(patch_module, "_fingerprint", return_value=(("foreign",), ()))
    @patch.object(patch_module, "_validate_tasks")
    @patch.object(patch_module.frappe, "get_doc")
    @patch.object(patch_module.frappe, "get_meta", return_value=SimpleNamespace(queue_in_background=0))
    @patch.object(patch_module.frappe, "get_all")
    @patch.object(patch_module.frappe.db, "exists", return_value=True)
    def test_unreviewed_workflow_fingerprint_stops(
        self,
        exists: Mock,
        get_all: Mock,
        get_meta: Mock,
        get_doc: Mock,
        validate_tasks: Mock,
        fingerprint: Mock,
    ) -> None:
        get_all.side_effect = [[patch_module.WORKFLOW], self.roles]
        with self.assertRaises(frappe.ValidationError):
            patch_module.execute()

    @patch.object(patch_module, "_ensure_tasks")
    @patch.object(patch_module, "_save_snapshot")
    @patch.object(patch_module, "_ensure_no_live_route_usage")
    @patch.object(
        patch_module,
        "_fingerprint",
        return_value=(patch_module.DESIRED_STATES, patch_module.DESIRED_TRANSITIONS),
    )
    @patch.object(patch_module, "_validate_tasks")
    @patch.object(patch_module.frappe, "get_doc", return_value=Mock())
    @patch.object(patch_module.frappe, "get_meta", return_value=SimpleNamespace(queue_in_background=0))
    @patch.object(patch_module.frappe, "get_all")
    @patch.object(patch_module.frappe.db, "exists", return_value=True)
    def test_exact_desired_rerun_repairs_tasks_without_touching_live_usage(
        self,
        exists: Mock,
        get_all: Mock,
        get_meta: Mock,
        get_doc: Mock,
        validate_tasks: Mock,
        fingerprint: Mock,
        ensure_no_live_route_usage: Mock,
        save_snapshot: Mock,
        ensure_tasks: Mock,
    ) -> None:
        get_all.side_effect = [[patch_module.WORKFLOW], self.roles]
        patch_module.execute()
        ensure_tasks.assert_called_once_with()
        ensure_no_live_route_usage.assert_not_called()
        save_snapshot.assert_not_called()

    @patch.object(patch_module, "_ensure_tasks")
    @patch.object(patch_module, "_save_snapshot")
    @patch.object(patch_module, "_ensure_no_live_route_usage")
    @patch.object(
        patch_module,
        "_fingerprint",
        return_value=(patch_module.LEGACY_STATES, patch_module.LEGACY_TRANSITIONS),
    )
    @patch.object(patch_module, "_validate_tasks")
    @patch.object(patch_module.frappe, "get_doc")
    @patch.object(patch_module.frappe, "get_meta", return_value=SimpleNamespace(queue_in_background=0))
    @patch.object(patch_module.frappe, "get_all")
    @patch.object(patch_module.frappe.db, "exists", return_value=True)
    def test_exact_legacy_route_is_snapshotted_only_after_live_usage_check(
        self,
        exists: Mock,
        get_all: Mock,
        get_meta: Mock,
        get_doc: Mock,
        validate_tasks: Mock,
        fingerprint: Mock,
        ensure_no_live_route_usage: Mock,
        save_snapshot: Mock,
        ensure_tasks: Mock,
    ) -> None:
        get_all.side_effect = [[patch_module.WORKFLOW], self.roles]
        workflow = get_doc.return_value
        manager = Mock()
        manager.attach_mock(ensure_no_live_route_usage, "live")
        manager.attach_mock(save_snapshot, "snapshot")
        patch_module.execute()
        self.assertEqual(manager.mock_calls, [call.live(), call.snapshot(workflow)])
        ensure_tasks.assert_called_once_with()

    def test_live_route_usage_checks_open_actions_and_pending_credit_notes(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=[True]),
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module._ensure_no_live_route_usage()

    def test_rollback_blocks_native_credit_note_history_in_any_state(self) -> None:
        with (
            patch.object(rollback_module.frappe.db, "exists", side_effect=[False, True]) as exists,
            self.assertRaises(frappe.ValidationError),
        ):
            rollback_module.execute()

        self.assertEqual(
            exists.call_args_list[1],
            call(
                "Sales Invoice",
                {"is_return": 1, "return_against": ["is", "set"]},
            ),
        )
        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=[False, True]),
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module._ensure_no_live_route_usage()

    def test_existing_exact_legacy_snapshot_is_reusable(self) -> None:
        workflow = Mock()
        prior = {
            "doctype": "Workflow",
            "name": patch_module.WORKFLOW,
        }
        snapshot = {"schema": 1, "site": "local.test", "workflow": prior}
        with (
            patch.object(patch_module, "_load_snapshot", return_value=snapshot),
            patch.object(patch_module.frappe, "get_doc", return_value=Mock()) as get_doc,
            patch.object(
                patch_module,
                "_fingerprint",
                return_value=(patch_module.LEGACY_STATES, patch_module.LEGACY_TRANSITIONS),
            ),
            patch.object(patch_module.frappe.local, "site", "local.test"),
        ):
            patch_module._save_snapshot(workflow)
        get_doc.assert_called_once_with(prior)

    def test_desired_fingerprint_covers_roles_conditions_tasks_and_native_cancel(self) -> None:
        transitions = patch_module.DESIRED_TRANSITIONS
        self.assertIn(
            (
                "Sales Invoice Credit Reviewed",
                "Approve Sales Invoice Credit",
                "Sales Invoice Credit Approved",
                "C-Level Approver",
                0,
                patch_module.CREDIT_CONDITION,
                "Connect Sales Invoice Credit Approve",
            ),
            transitions,
        )
        self.assertIn(
            (
                "Sales Invoice Submitted",
                "Cancel Sales Invoice Credit",
                "Sales Invoice Cancelled",
                "Sales Manager",
                0,
                patch_module.CREDIT_CONDITION,
                "Connect Sales Invoice Credit Cancel",
            ),
            transitions,
        )
        send_roles = {
            transition[3]
            for transition in transitions
            if transition[1] == "Send Sales Invoice Credit for Review"
        }
        self.assertEqual(send_roles, {"Sales User"})
