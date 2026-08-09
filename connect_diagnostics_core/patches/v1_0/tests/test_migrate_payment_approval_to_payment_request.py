# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_payment_approval_to_payment_request as patch_module


class TestMigratePaymentApprovalToPaymentRequest(UnitTestCase):
    @patch.object(patch_module, "assign_payment_approvers")
    @patch.object(patch_module, "ensure_configuration")
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "_delete_legacy_workflow_actions")
    def test_migration_keeps_only_active_setup(
        self,
        delete_actions: MagicMock,
        create_fields: MagicMock,
        ensure_configuration: MagicMock,
        assign_approvers: MagicMock,
    ) -> None:
        patch_module.execute()

        delete_actions.assert_called_once_with()
        create_fields.assert_called_once_with(patch_module.CUSTOM_FIELDS, ignore_validate=True)
        ensure_configuration.assert_called_once_with()
        assign_approvers.assert_called_once_with()
