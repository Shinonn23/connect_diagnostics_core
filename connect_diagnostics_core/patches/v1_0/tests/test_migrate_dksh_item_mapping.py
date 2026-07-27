# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_dksh_item_mapping as patch_module
from connect_diagnostics_core.setup import dksh_item_mapping as mapping_setup
from connect_diagnostics_core.setup import sales_order_item


class TestMigrateDKSHItemMapping(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "_reset_sales_order_item_grid_settings")
    @patch.object(patch_module, "_backfill_draft_dksh_sales_orders")
    @patch.object(patch_module, "_migrate_active_partner_item_mappings")
    @patch.object(mapping_setup, "ensure_configuration")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_creates_the_sales_order_field_before_backfill(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_migrate_mappings: MagicMock,
        mocked_backfill_orders: MagicMock,
        mocked_reset_grid: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_create_custom_fields, "create_custom_fields")
        manager.attach_mock(mocked_ensure_configuration, "ensure_configuration")
        manager.attach_mock(mocked_migrate_mappings, "migrate_mappings")
        manager.attach_mock(mocked_backfill_orders, "backfill_orders")
        manager.attach_mock(mocked_reset_grid, "reset_grid")
        manager.attach_mock(mocked_clear_cache, "clear_cache")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.create_custom_fields(sales_order_item.CUSTOM_FIELDS, ignore_validate=True),
                call.ensure_configuration(),
                call.migrate_mappings(),
                call.backfill_orders(),
                call.reset_grid(),
                call.clear_cache(doctype=patch_module.MAPPING_DOCTYPE),
                call.clear_cache(doctype="Sales Order"),
                call.clear_cache(doctype="Item"),
            ],
        )

    @patch.object(patch_module.frappe.cache, "hset")
    @patch.object(patch_module.frappe.db, "sql")
    def test_reset_grid_settings_preserves_all_other_user_preferences(
        self, mocked_sql: MagicMock, mocked_hset: MagicMock
    ) -> None:
        mocked_sql.return_value = [
            {
                "user": "sales@example.com",
                "data": json.dumps(
                    {
                        "GridView": {
                            "Sales Order Item": [{"fieldname": "delivery_date"}],
                            "Other Child": [{"fieldname": "value"}],
                        },
                        "List": {"page_length": 20},
                    }
                ),
            }
        ]

        patch_module._reset_sales_order_item_grid_settings()

        update_call = mocked_sql.call_args_list[1]
        update_data = json.loads(update_call.args[1]["data"])
        self.assertNotIn("Sales Order Item", update_data["GridView"])
        self.assertEqual(update_data["GridView"]["Other Child"], [{"fieldname": "value"}])
        self.assertEqual(update_data["List"], {"page_length": 20})
        mocked_hset.assert_called_once_with("_user_settings", "Sales Order::sales@example.com", None)

    def test_parse_user_settings_rejects_corrupt_json_without_losing_the_migration(self) -> None:
        self.assertEqual(patch_module._parse_user_settings("not-json"), {})
