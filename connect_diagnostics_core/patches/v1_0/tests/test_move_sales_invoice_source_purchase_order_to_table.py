# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    move_sales_invoice_source_purchase_order_to_table as patch_module,
)


class TestMoveSalesInvoiceSourcePurchaseOrderToTable(UnitTestCase):
    def test_no_op_when_neither_column_remains(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe, "get_all") as mocked_get_all,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_get_all.assert_not_called()
        mocked_drop.assert_not_called()

    def test_only_invoices_with_a_value_get_a_row_then_columns_are_dropped(self) -> None:
        invoices = [
            {"name": "SINV-1", "customer": "CUST-1", "source_purchase_order": "PO-1", "source_purchase_order_file": ""},
            {"name": "SINV-2", "customer": "CUST-1", "source_purchase_order": "", "source_purchase_order_file": ""},
        ]
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe, "get_all", return_value=invoices),
            patch.object(patch_module, "_ensure_row") as mocked_ensure,
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        mocked_ensure.assert_called_once_with("SINV-1", "CUST-1", "PO-1", "")
        self.assertEqual(
            [call.args for call in mocked_drop.call_args_list],
            [("Sales Invoice", "source_purchase_order"), ("Sales Invoice", "source_purchase_order_file")],
        )

    def test_an_existing_row_is_not_duplicated(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value="row-1"),
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
        ):
            patch_module._ensure_row("SINV-1", "CUST-1", "PO-1", "")

        mocked_get_doc.assert_not_called()

    def test_copy_count_comes_from_the_customer_and_defaults_to_one(self) -> None:
        with patch.object(patch_module.frappe.db, "get_value", return_value=3):
            self.assertEqual(patch_module._customer_copy_count("CUST-1"), 3)
        with patch.object(patch_module.frappe.db, "get_value", return_value=0):
            self.assertEqual(patch_module._customer_copy_count("CUST-1"), 1)
        self.assertEqual(patch_module._customer_copy_count(""), 1)
