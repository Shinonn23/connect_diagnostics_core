# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import retire_storage_location_inventory_dimension as patch_module


class TestRetireStorageLocationInventoryDimension(UnitTestCase):
    def test_no_op_when_dimension_missing(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False) as mocked_exists,
            patch.object(patch_module.frappe, "get_all") as mocked_get_all,
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete,
        ):
            patch_module.execute()

        mocked_exists.assert_called_once_with("Inventory Dimension", "Storage Location")
        mocked_get_all.assert_not_called()
        mocked_delete.assert_not_called()

    def test_deletes_dimension_and_drops_captured_columns(self) -> None:
        affected = [
            frappe._dict({"dt": "Stock Entry Detail", "fieldname": "storage_location"}),
            frappe._dict({"dt": "Stock Ledger Entry", "fieldname": "storage_location"}),
            frappe._dict({"dt": "Stock Entry Detail", "fieldname": "to_storage_location"}),
        ]
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_all", return_value=affected) as mocked_get_all,
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete,
            patch.object(patch_module.frappe.db, "sql_ddl") as mocked_sql_ddl,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_get_all.assert_called_once_with(
            "Custom Field",
            filters={
                "fieldname": ("in", patch_module._GENERATED_FIELDNAMES),
                "options": "Storage Location",
            },
            fields=["dt", "fieldname"],
        )
        mocked_delete.assert_called_once_with(
            "Inventory Dimension", "Storage Location", force=True, ignore_permissions=True
        )
        self.assertEqual(mocked_sql_ddl.call_count, 3)
        statements = [call.args[0] for call in mocked_sql_ddl.call_args_list]
        self.assertIn("`tabStock Entry Detail` DROP COLUMN IF EXISTS `storage_location`", statements[0])
        self.assertIn("`tabStock Ledger Entry` DROP COLUMN IF EXISTS `storage_location`", statements[1])
        self.assertIn("`tabStock Entry Detail` DROP COLUMN IF EXISTS `to_storage_location`", statements[2])
