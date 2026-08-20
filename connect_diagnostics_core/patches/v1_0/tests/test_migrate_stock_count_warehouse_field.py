# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_stock_count_warehouse_field as patch_module


class TestMigrateStockCountWarehouseField(UnitTestCase):
    def test_no_op_when_warehouse_column_missing(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=False) as mocked_has_column,
            patch.object(patch_module.frappe.db, "sql") as mocked_sql,
            patch.object(patch_module.frappe.db, "sql_ddl") as mocked_sql_ddl,
        ):
            patch_module.execute()

        mocked_has_column.assert_called_once_with("Stock Count", "warehouse")
        mocked_sql.assert_not_called()
        mocked_sql_ddl.assert_not_called()

    def test_backfills_child_row_then_drops_both_orphan_columns(self) -> None:
        row = frappe._dict({"name": "STK-CNT-2026-00001", "warehouse": "Main Store - CD"})
        mocked_child = MagicMock()
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe.db, "sql", return_value=[row]),
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe, "generate_hash", return_value="abc1234567"),
            patch.object(patch_module.frappe, "get_doc", return_value=mocked_child) as mocked_get_doc,
            patch.object(patch_module.frappe.db, "sql_ddl") as mocked_sql_ddl,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_get_doc.assert_called_once_with(
            {
                "doctype": "Stock Count Warehouse",
                "name": "abc1234567",
                "parent": "STK-CNT-2026-00001",
                "parenttype": "Stock Count",
                "parentfield": "warehouses",
                "idx": 1,
                "warehouse": "Main Store - CD",
            }
        )
        mocked_child.db_insert.assert_called_once_with()
        statements = [call.args[0] for call in mocked_sql_ddl.call_args_list]
        self.assertEqual(len(statements), 2)
        self.assertIn("DROP COLUMN IF EXISTS `warehouse`", statements[0])
        self.assertIn("DROP COLUMN IF EXISTS `storage_location`", statements[1])

    def test_skips_when_child_rows_already_exist(self) -> None:
        row = frappe._dict({"name": "STK-CNT-2026-00002", "warehouse": "Main Store - CD"})
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe.db, "sql", return_value=[row]),
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
            patch.object(patch_module.frappe.db, "sql_ddl"),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_get_doc.assert_not_called()
