# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_customer_onboarding as patch_module
from connect_diagnostics_core.patches.v1_0 import rollback_migrate_customer_onboarding as rollback_module
from connect_diagnostics_core.setup import customer, customer_onboarding


class TestMigrateCustomerOnboarding(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(customer_onboarding, "ensure_configuration")
    @patch.object(patch_module, "_backfill_customers")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_creates_customer_fields_before_backfill_and_workflow_setup(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_backfill_customers: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_create_custom_fields, "create_custom_fields")
        manager.attach_mock(mocked_backfill_customers, "backfill_customers")
        manager.attach_mock(mocked_ensure_configuration, "ensure_configuration")
        manager.attach_mock(mocked_clear_cache, "clear_cache")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True),
                call.backfill_customers(),
                call.ensure_configuration(),
                call.clear_cache(),
            ],
        )

    def test_rollback_restores_configuration_without_deleting_master_data(self) -> None:
        with (
            patch.object(rollback_module, "_deactivate_workflows") as mocked_deactivate_workflows,
            patch.object(rollback_module, "_remove_open_workflow_actions") as mocked_remove_actions,
            patch.object(rollback_module.frappe, "clear_cache") as mocked_clear_cache,
        ):
            manager = MagicMock()
            manager.attach_mock(mocked_deactivate_workflows, "deactivate_workflows")
            manager.attach_mock(mocked_remove_actions, "remove_open_workflow_actions")
            manager.attach_mock(mocked_clear_cache, "clear_cache")

            rollback_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.deactivate_workflows(),
                call.remove_open_workflow_actions(),
                call.clear_cache(doctype="Customer"),
                call.clear_cache(doctype="Customer Credit Request"),
            ],
        )
