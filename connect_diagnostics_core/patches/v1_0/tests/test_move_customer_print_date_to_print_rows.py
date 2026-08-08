# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import move_customer_print_date_to_print_rows as patch_module


class TestMoveCustomerPrintDateToPrintRows(UnitTestCase):
    def test_no_op_when_the_column_is_already_gone(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe, "get_all") as mocked_get_all,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_get_all.assert_not_called()
        mocked_drop.assert_not_called()

    def test_only_customers_that_hid_the_date_get_a_row_then_the_column_is_dropped(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=[{"name": "CD-0001"}, {"name": "CD-0002"}],
            ),
            patch.object(patch_module, "_ensure_hidden_date_row") as mocked_ensure,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        self.assertEqual(
            [call.args for call in mocked_ensure.call_args_list],
            [("CD-0001",), ("CD-0002",)],
        )
        mocked_drop.assert_called_once_with("Customer", "print_date")

    def test_an_existing_sales_order_row_is_not_duplicated(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value="pdc-1"),
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
        ):
            patch_module._ensure_hidden_date_row("CD-0001")

        mocked_get_doc.assert_not_called()
