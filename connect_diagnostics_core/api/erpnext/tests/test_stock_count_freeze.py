# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_reconciliation_freeze


def _doc(**fields: object) -> Document:
    return frappe.get_doc({"doctype": "Stock Entry", **fields})


class TestStockReconciliationFreeze(UnitTestCase):
    def test_extracts_item_warehouse_pairs(self) -> None:
        pairs, warehouses = stock_reconciliation_freeze._rows_to_check(
            _doc(
                items=[
                    {"item_code": "ITEM-A", "s_warehouse": "WH-1", "t_warehouse": ""},
                    {"item_code": "ITEM-B", "s_warehouse": "", "t_warehouse": "WH-2"},
                ]
            )
        )
        self.assertEqual(pairs, {("ITEM-A", "WH-1"), ("ITEM-B", "WH-2")})
        self.assertEqual(warehouses, {"WH-1", "WH-2"})

    def test_unmapped_doctype_yields_nothing(self) -> None:
        doc = frappe.get_doc({"doctype": "Journal Entry", "items": []})
        self.assertEqual(stock_reconciliation_freeze._rows_to_check(doc), (set(), set()))

    def test_native_reconciliation_scope_blocks_matching_item_and_warehouse(self) -> None:
        rows = [frappe._dict(item_code="ITEM-A", warehouse="WH-1", reconciliation="SR-1")]
        with patch.object(stock_reconciliation_freeze.frappe.db, "sql", return_value=rows):
            messages = stock_reconciliation_freeze._check_item_level({("ITEM-A", "WH-1")})
        self.assertIn("SR-1", messages[0])

    def test_native_reconciliation_scope_does_not_block_unmatched_item(self) -> None:
        rows = [frappe._dict(item_code="ITEM-A", warehouse="WH-1", reconciliation="SR-1")]
        with patch.object(stock_reconciliation_freeze.frappe.db, "sql", return_value=rows):
            messages = stock_reconciliation_freeze._check_item_level({("ITEM-B", "WH-1")})
        self.assertEqual(messages, [])

    def test_native_reconciliation_scope_blocks_warehouse_level_match(self) -> None:
        rows = [frappe._dict(warehouse="WH-1", reconciliation="SR-1")]
        with patch.object(stock_reconciliation_freeze.frappe.db, "sql", return_value=rows):
            messages = stock_reconciliation_freeze._check_warehouse_level({"WH-1"})
        self.assertIn("SR-1", messages[0])

    def test_stock_reconciliation_validation_excludes_current_reconciliation(self) -> None:
        doc = Document(
            {
                "doctype": "Stock Reconciliation",
                "name": "SR-CURRENT",
                "items": [{"item_code": "ITEM-A", "warehouse": "WH-1"}],
            }
        )
        with (
            patch.object(stock_reconciliation_freeze, "_check_item_level", return_value=[]) as item_check,
            patch.object(stock_reconciliation_freeze, "_check_warehouse_level", return_value=[]) as warehouse_check,
        ):
            stock_reconciliation_freeze.validate_transaction(doc)
        item_check.assert_called_once_with({("ITEM-A", "WH-1")}, exclude_name="SR-CURRENT")
        warehouse_check.assert_called_once_with({"WH-1"}, exclude_name="SR-CURRENT")

    def test_different_active_reconciliation_still_blocks(self) -> None:
        rows = [frappe._dict(item_code="ITEM-A", warehouse="WH-1", reconciliation="SR-OTHER")]
        with patch.object(stock_reconciliation_freeze.frappe.db, "sql", return_value=rows) as sql:
            messages = stock_reconciliation_freeze._check_item_level(
                {("ITEM-A", "WH-1")}, exclude_name="SR-CURRENT"
            )
        self.assertIn("SR-OTHER", messages[0])
        self.assertEqual(sql.call_args_list[0].args[1]["exclude_name"], "SR-CURRENT")

    def test_different_active_reconciliation_still_blocks_at_warehouse_level(self) -> None:
        rows = [frappe._dict(warehouse="WH-1", reconciliation="SR-OTHER")]
        with patch.object(stock_reconciliation_freeze.frappe.db, "sql", return_value=rows) as sql:
            messages = stock_reconciliation_freeze._check_warehouse_level(
                {"WH-1"}, exclude_name="SR-CURRENT"
            )
        self.assertIn("SR-OTHER", messages[0])
        self.assertEqual(sql.call_args_list[0].args[1]["exclude_name"], "SR-CURRENT")

    def test_non_stock_update_invoice_is_skipped(self) -> None:
        stock_reconciliation_freeze.validate_transaction(
            frappe.get_doc({"doctype": "Sales Invoice", "update_stock": 0})
        )

    def test_execution_marker_is_cleared_after_exception_path(self) -> None:
        doc = _doc(workflow_state="Emergency Stock Movement Submitted")
        with (
            patch.dict(
                stock_reconciliation_freeze.frappe.flags,
                {"freeze_exception_execution": {"name": doc.name}},
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.stock_entry_workflow.is_authorized_freeze_exception",
                return_value=True,
            ),
        ):
            stock_reconciliation_freeze.validate_transaction(doc)
        self.assertIsNone(
            getattr(stock_reconciliation_freeze.frappe.flags, "freeze_exception_execution", None)
        )
