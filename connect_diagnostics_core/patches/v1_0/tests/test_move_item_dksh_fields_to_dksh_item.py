# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import move_item_dksh_fields_to_dksh_item as patch_module


class TestMoveItemDKSHFieldsToDKSHItem(UnitTestCase):
    def test_no_op_when_no_dksh_columns_remain(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe, "reload_doc") as mocked_reload,
            patch.object(patch_module, "_items_with_dksh_values") as mocked_read,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_read.assert_not_called()
        mocked_drop.assert_not_called()
        mocked_reload.assert_not_called()

    def test_item_with_a_code_is_moved_then_every_column_is_dropped(self) -> None:
        row = {
            "name": "CD-ITEM-001",
            "dksh_item_code": "EXT-001",
            "supplier_product_code": "SUP-1",
            "mat_group_code": "",
            "mat_group4_code": "",
            "material_type_code": "",
        }

        def read_items(present: list[str]) -> list[dict[str, str]]:
            mocked_reload.assert_called_once_with(
                patch_module.DKSH_MODULE, "doctype", "dksh_item", force=True
            )
            self.assertEqual(present, list(patch_module.DKSH_FIELDS))
            return [row]

        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe, "reload_doc") as mocked_reload,
            patch.object(patch_module, "_items_with_dksh_values", side_effect=read_items),
            patch.object(patch_module, "_upsert_dksh_item") as mocked_upsert,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_upsert.assert_called_once_with("CD-ITEM-001", "EXT-001", row)
        self.assertEqual(
            [call.args for call in mocked_drop.call_args_list],
            [("Item", field) for field in patch_module.DKSH_FIELDS],
        )

    def test_reference_values_without_a_code_are_skipped_and_logged(self) -> None:
        row = {
            "name": "CD-ITEM-002",
            "dksh_item_code": "",
            "supplier_product_code": "SUP-2",
            "mat_group_code": "",
            "mat_group4_code": "",
            "material_type_code": "",
        }
        logger = MagicMock()
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe, "reload_doc"),
            patch.object(patch_module, "_items_with_dksh_values", return_value=[row]),
            patch.object(patch_module, "_upsert_dksh_item") as mocked_upsert,
            patch.object(patch_module, "_drop_old"),
            patch.object(patch_module.frappe, "logger", return_value=logger),
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_upsert.assert_not_called()
        logger.warning.assert_called_once()
