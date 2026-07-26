# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_customer_onboarding as patch_module
from connect_diagnostics_core.patches.v1_0 import rollback_migrate_customer_onboarding as rollback_module
from connect_diagnostics_core.config.dksh import DKSH_COMPANY
from connect_diagnostics_core.setup import customer, customer_onboarding, item


class TestMigrateCustomerOnboarding(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(customer_onboarding, "ensure_configuration")
    @patch.object(patch_module.partner_item_mapping, "on_doctype_update")
    @patch.object(patch_module, "_backfill_items_and_partner_mappings")
    @patch.object(patch_module, "_backfill_customers")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_creates_fields_before_backfill_and_workflow_setup(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_backfill_customers: MagicMock,
        mocked_backfill_items: MagicMock,
        mocked_ensure_partner_item_mapping_constraint: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_create_custom_fields, "create_custom_fields")
        manager.attach_mock(mocked_backfill_customers, "backfill_customers")
        manager.attach_mock(mocked_backfill_items, "backfill_items")
        manager.attach_mock(
            mocked_ensure_partner_item_mapping_constraint, "ensure_partner_item_mapping_constraint"
        )
        manager.attach_mock(mocked_ensure_configuration, "ensure_configuration")
        manager.attach_mock(mocked_clear_cache, "clear_cache")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True),
                call.create_custom_fields(item.CUSTOM_FIELDS, ignore_validate=True),
                call.backfill_customers(),
                call.backfill_items(),
                call.ensure_partner_item_mapping_constraint(),
                call.ensure_configuration(),
                call.clear_cache(),
            ],
        )

    def test_customer_channel_conversion_preserves_legacy_dksh_split(self) -> None:
        self.assertEqual(
            patch_module._customer_channel_from_legacy(
                {"has_dksh_code": 1, "customer_code_is_dksh_code": 0, "dksh_customer_code": "SAP-1"}
            ),
            ("CD and DKSH", "SAP-1"),
        )
        self.assertEqual(
            patch_module._customer_channel_from_legacy(
                {"has_dksh_code": 1, "customer_code_is_dksh_code": 1, "dksh_customer_code": "SAP-2"}
            ),
            ("DKSH", None),
        )

    def test_item_channel_conversion_uses_dksh_item_code_for_both_channel(self) -> None:
        self.assertEqual(
            patch_module._item_channel_from_legacy(
                {
                    "name": "CD-ITEM-1",
                    "item_code": "CD-ITEM-1",
                    "has_dksh_code": 1,
                    "item_code_is_dksh_code": 0,
                    "dksh_item_code": "DKSH-ITEM-1",
                }
            ),
            ("CD and DKSH", "DKSH-ITEM-1"),
        )

    def test_legacy_mapping_migration_uses_the_fixed_dksh_company(self) -> None:
        self.assertEqual(patch_module._legacy_dksh_company(), DKSH_COMPANY)

    def test_rollback_restores_configuration_without_deleting_master_data(self) -> None:
        with (
            patch.object(rollback_module, "_deactivate_workflows") as mocked_deactivate_workflows,
            patch.object(rollback_module, "_remove_open_workflow_actions") as mocked_remove_actions,
            patch.object(rollback_module, "_restore_legacy_custom_fields") as mocked_restore_fields,
            patch.object(rollback_module, "_restore_legacy_customer_naming") as mocked_restore_naming,
            patch.object(rollback_module.frappe, "clear_cache") as mocked_clear_cache,
            patch.object(rollback_module.frappe.db, "commit") as mocked_commit,
        ):
            manager = MagicMock()
            manager.attach_mock(mocked_deactivate_workflows, "deactivate_workflows")
            manager.attach_mock(mocked_remove_actions, "remove_open_workflow_actions")
            manager.attach_mock(mocked_restore_fields, "restore_legacy_custom_fields")
            manager.attach_mock(mocked_restore_naming, "restore_legacy_customer_naming")
            manager.attach_mock(mocked_clear_cache, "clear_cache")
            manager.attach_mock(mocked_commit, "commit")

            rollback_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.deactivate_workflows(),
                call.remove_open_workflow_actions(),
                call.restore_legacy_custom_fields(),
                call.restore_legacy_customer_naming(),
                call.clear_cache(doctype="Customer"),
                call.clear_cache(doctype="Item"),
                call.clear_cache(doctype="Customer Credit Request"),
                call.commit(),
            ],
        )

    @patch.object(rollback_module.frappe.db, "bulk_update")
    @patch.object(rollback_module.frappe, "get_all")
    def test_rollback_updates_only_managed_custom_fields(
        self,
        mocked_get_all: MagicMock,
        mocked_bulk_update: MagicMock,
    ) -> None:
        mocked_get_all.return_value = [
            {"name": "Customer-customer_code", "dt": "Customer", "fieldname": "customer_code"},
            {"name": "Item-item_channel", "dt": "Item", "fieldname": "item_channel"},
            {"name": "Customer-unmanaged", "dt": "Customer", "fieldname": "unmanaged"},
        ]

        rollback_module._restore_legacy_custom_fields()

        mocked_bulk_update.assert_called_once_with(
            "Custom Field",
            {
                "Customer-customer_code": {"hidden": 1, "reqd": 0},
                "Item-item_channel": {"hidden": 1, "reqd": 0},
            },
            update_modified=False,
        )
