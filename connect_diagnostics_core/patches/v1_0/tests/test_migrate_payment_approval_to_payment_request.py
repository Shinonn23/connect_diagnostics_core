# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    migrate_payment_approval_to_payment_request as patch_module,
)
from connect_diagnostics_core.setup import payment_approval


class TestMigratePaymentApprovalToPaymentRequest(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "assign_payment_approvers")
    @patch.object(patch_module, "ensure_configuration")
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "remove_legacy_payment_entry_configuration")
    @patch.object(patch_module, "_delete_legacy_workflow_actions")
    def test_execute_removes_legacy_configuration_before_installing_payment_request_workflow(
        self,
        mocked_delete_actions: MagicMock,
        mocked_remove_legacy: MagicMock,
        mocked_create_fields: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_assign_approvers: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_delete_actions, "delete_actions")
        manager.attach_mock(mocked_remove_legacy, "remove_legacy")
        manager.attach_mock(mocked_create_fields, "create_fields")
        manager.attach_mock(mocked_ensure_configuration, "ensure_configuration")
        manager.attach_mock(mocked_assign_approvers, "assign_approvers")
        manager.attach_mock(mocked_clear_cache, "clear_cache")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.delete_actions(),
                call.remove_legacy(),
                call.create_fields(payment_approval.CUSTOM_FIELDS, ignore_validate=True),
                call.ensure_configuration(),
                call.assign_approvers(),
                call.clear_cache(),
            ],
        )

    @patch.object(patch_module.frappe, "delete_doc")
    @patch.object(patch_module.frappe.db, "exists", return_value=True)
    @patch.object(patch_module.frappe, "get_all", return_value=["ACTION-1", "ACTION-2"])
    def test_migration_deletes_only_legacy_payment_entry_workflow_actions(
        self,
        mocked_get_all: MagicMock,
        _mocked_exists: MagicMock,
        mocked_delete_doc: MagicMock,
    ) -> None:
        patch_module._delete_legacy_workflow_actions()

        mocked_get_all.assert_called_once_with(
            "Workflow Action",
            filters={
                "reference_doctype": payment_approval.PAYMENT_ENTRY_DOCTYPE,
                "workflow_state": ["in", tuple(payment_approval.LEGACY_WORKFLOW_STATE_STYLES)],
            },
            pluck="name",
        )
        self.assertEqual(
            mocked_delete_doc.call_args_list,
            [
                call("Workflow Action", "ACTION-1", force=True, ignore_permissions=True),
                call("Workflow Action", "ACTION-2", force=True, ignore_permissions=True),
            ],
        )

    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "assign_payment_approvers")
    @patch.object(patch_module, "ensure_configuration")
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "remove_legacy_payment_entry_configuration")
    @patch.object(patch_module, "_delete_legacy_workflow_actions")
    def test_execute_is_safe_to_repeat(
        self,
        mocked_delete_actions: MagicMock,
        mocked_remove_legacy: MagicMock,
        mocked_create_fields: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_assign_approvers: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        patch_module.execute()
        patch_module.execute()

        for mocked_function in (
            mocked_delete_actions,
            mocked_remove_legacy,
            mocked_create_fields,
            mocked_ensure_configuration,
            mocked_assign_approvers,
            mocked_clear_cache,
        ):
            self.assertEqual(mocked_function.call_count, 2)

    @patch.object(payment_approval, "reset_perms")
    @patch.object(payment_approval, "_custom_permissions_match_standard", return_value=False)
    @patch.object(payment_approval.frappe, "delete_doc")
    @patch.object(payment_approval.frappe, "get_all", return_value=["MANAGED-PERM"])
    @patch.object(payment_approval.frappe.db, "exists")
    def test_legacy_permission_removal_preserves_site_specific_custom_permissions(
        self,
        mocked_exists: MagicMock,
        _mocked_get_all: MagicMock,
        mocked_delete_doc: MagicMock,
        _mocked_permissions_match: MagicMock,
        mocked_reset_perms: MagicMock,
    ) -> None:
        mocked_exists.side_effect = lambda _doctype, filters: (
            "COPY-MARKER"
            if isinstance(filters, dict) and filters == payment_approval.LEGACY_PERMISSION_COPY_MARKER
            else True
        )

        payment_approval._remove_managed_permissions(
            payment_approval.PAYMENT_ENTRY_DOCTYPE,
            tuple(payment_approval.PAYMENT_REQUEST_PERMISSIONS),
            payment_approval.LEGACY_PERMISSION_COPY_MARKER,
        )

        mocked_reset_perms.assert_not_called()
        self.assertCountEqual(
            [current_call.args[1] for current_call in mocked_delete_doc.call_args_list],
            ["MANAGED-PERM", "COPY-MARKER"],
        )

    @patch.object(payment_approval, "reset_perms")
    @patch.object(payment_approval, "_custom_permissions_match_standard", return_value=True)
    @patch.object(payment_approval.frappe, "delete_doc")
    @patch.object(payment_approval.frappe, "get_all", return_value=["MANAGED-PERM"])
    @patch.object(payment_approval.frappe.db, "exists", return_value=True)
    def test_legacy_permission_removal_resets_exact_standard_copy(
        self,
        _mocked_exists: MagicMock,
        _mocked_get_all: MagicMock,
        _mocked_delete_doc: MagicMock,
        _mocked_permissions_match: MagicMock,
        mocked_reset_perms: MagicMock,
    ) -> None:
        payment_approval._remove_managed_permissions(
            payment_approval.PAYMENT_ENTRY_DOCTYPE,
            tuple(payment_approval.PAYMENT_REQUEST_PERMISSIONS),
            payment_approval.LEGACY_PERMISSION_COPY_MARKER,
        )

        mocked_reset_perms.assert_called_once_with(payment_approval.PAYMENT_ENTRY_DOCTYPE)
