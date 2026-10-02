# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.erpnext import (
    repost_item_valuation_reservation,
    stock_count_session_workflow,
    stock_reconciliation_freeze,
    stock_reconciliation_workflow,
)


def _doc(**fields: object) -> Document:
    return Document({"doctype": "Stock Entry", **fields})


class TestStockReconciliationFreeze(UnitTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # The SQL-specific tests below mock db.sql; load native DocType metadata first.
        for doctype in ("Stock Reconciliation", "Stock Entry", "Sales Invoice", "Journal Entry"):
            frappe.get_meta(doctype)

    def test_historical_workflow_callbacks_use_signed_adapter(self) -> None:
        for name in (
            "capture_maker",
            "capture_review",
            "capture_approval",
            "clear_approval",
            "authorize_submit_execution",
            "authorize_cancel_execution",
            "validate_before_submit",
            "validate_before_cancel",
        ):
            self.assertIs(
                getattr(stock_reconciliation_freeze, name), getattr(stock_reconciliation_workflow, name)
            )

    def test_direct_submit_fails_closed_and_clears_marker(self) -> None:
        doc = Document(
            {
                "doctype": "Stock Reconciliation",
                "name": "SR-1",
                "workflow_state": stock_reconciliation_workflow.SUBMITTED_STATE,
            }
        )
        setattr(stock_reconciliation_freeze.frappe.flags, stock_reconciliation_freeze._EXECUTION_FLAG, None)
        with self.assertRaises(Exception):
            stock_reconciliation_freeze.validate_before_submit(doc)
        self.assertIsNone(
            getattr(
                stock_reconciliation_freeze.frappe.flags,
                stock_reconciliation_freeze._EXECUTION_FLAG,
                None,
            )
        )

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
        doc = Document({"doctype": "Journal Entry", "items": []})
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
            patch.object(stock_reconciliation_freeze, "lock_warehouses"),
            patch.object(stock_count_session_workflow, "enforce_count_freeze"),
            patch.object(repost_item_valuation_reservation, "check_foreground_repost"),
            patch.object(stock_reconciliation_freeze, "_check_item_level", return_value=[]) as item_check,
            patch.object(
                stock_reconciliation_freeze, "_check_warehouse_level", return_value=[]
            ) as warehouse_check,
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
            messages = stock_reconciliation_freeze._check_warehouse_level({"WH-1"}, exclude_name="SR-CURRENT")
        self.assertIn("SR-OTHER", messages[0])
        self.assertEqual(sql.call_args_list[0].args[1]["exclude_name"], "SR-CURRENT")

    def test_non_stock_update_invoice_is_skipped(self) -> None:
        with (
            patch.object(stock_reconciliation_freeze, "_check_item_level") as item_check,
            patch.object(stock_reconciliation_freeze, "_check_warehouse_level") as warehouse_check,
        ):
            stock_reconciliation_freeze.validate_transaction(
                Document({"doctype": "Sales Invoice", "update_stock": 0})
            )
        item_check.assert_not_called()
        warehouse_check.assert_not_called()

    def test_native_physical_source_grains_include_outgoing_packed_and_raw_rows(self) -> None:
        cases = (
            (
                "Purchase Receipt",
                {
                    "items": [{"item_code": "A", "warehouse": "NEW", "from_warehouse": "OLD"}],
                    "is_old_subcontracting_flow": 1,
                    "supplier_warehouse": "SUP",
                    "supplied_items": [{"rm_item_code": "RAW"}],
                },
                {("A", "NEW"), ("A", "OLD"), ("RAW", "SUP")},
            ),
            (
                "Purchase Invoice",
                {
                    "update_stock": 1,
                    "is_old_subcontracting_flow": 1,
                    "items": [{"item_code": "A", "warehouse": "NEW", "from_warehouse": "OLD"}],
                    "supplier_warehouse": "SUP",
                    "supplied_items": [{"rm_item_code": "RAW"}],
                },
                {("A", "NEW"), ("A", "OLD"), ("RAW", "SUP")},
            ),
            (
                "Delivery Note",
                {
                    "items": [{"item_code": "P", "warehouse": "PARENT"}],
                    "packed_items": [{"item_code": "C", "warehouse": "CHILD", "target_warehouse": "TARGET"}],
                },
                {("P", "PARENT"), ("C", "CHILD"), ("C", "TARGET")},
            ),
            (
                "Sales Invoice",
                {
                    "update_stock": 1,
                    "items": [{"item_code": "P", "warehouse": "PARENT"}],
                    "packed_items": [{"item_code": "C", "warehouse": "CHILD", "target_warehouse": "TARGET"}],
                },
                {("P", "PARENT"), ("C", "CHILD"), ("C", "TARGET")},
            ),
            (
                "Subcontracting Receipt",
                {
                    "items": [{"item_code": "FG", "warehouse": "FG-WH", "rejected_warehouse": "BAD-WH"}],
                    "supplier_warehouse": "SUP",
                    "supplied_items": [{"rm_item_code": "RAW"}],
                },
                {("FG", "FG-WH"), ("FG", "BAD-WH"), ("RAW", "SUP")},
            ),
            (
                "Asset Capitalization",
                {"stock_items": [{"item_code": "A", "warehouse": "ASSET-WH"}]},
                {("A", "ASSET-WH")},
            ),
        )
        for doctype, values, expected in cases:
            with self.subTest(doctype=doctype):
                pairs, warehouses = stock_reconciliation_freeze._rows_to_check(
                    Document({"doctype": doctype, **values})
                )
                self.assertEqual(pairs, expected)
                self.assertEqual(warehouses, {warehouse for _item, warehouse in expected})

    def test_non_old_purchase_raw_rows_do_not_freeze_supplier_warehouse(self) -> None:
        for doctype in ("Purchase Receipt", "Purchase Invoice"):
            for flag in (None, 0):
                with self.subTest(doctype=doctype, flag=flag):
                    values = {
                        "doctype": doctype,
                        "update_stock": 1,
                        "items": [{"item_code": "A", "warehouse": "NEW", "from_warehouse": "OLD"}],
                        "supplier_warehouse": "SUP",
                        "supplied_items": [{"rm_item_code": "RAW"}],
                    }
                    if flag is not None:
                        values["is_old_subcontracting_flow"] = flag
                    pairs, warehouses = stock_reconciliation_freeze._rows_to_check(Document(values))
                    self.assertEqual(pairs, {("A", "NEW"), ("A", "OLD")})
                    self.assertEqual(warehouses, {"NEW", "OLD"})

    def test_landed_cost_reads_all_receipt_scopes_without_emergency_bypass(self) -> None:
        sources = {
            "PR": Document(
                {"doctype": "Purchase Receipt", "items": [{"item_code": "A", "warehouse": "A-WH"}]}
            ),
            "PI": Document(
                {
                    "doctype": "Purchase Invoice",
                    "update_stock": 1,
                    "items": [{"item_code": "B", "warehouse": "B-WH"}],
                }
            ),
            "SE": Document(
                {
                    "doctype": "Stock Entry",
                    "workflow_state": "Emergency Stock Movement Submitted",
                    "items": [{"item_code": "C", "s_warehouse": "C-WH"}],
                }
            ),
            "SCR": Document(
                {"doctype": "Subcontracting Receipt", "items": [{"item_code": "D", "warehouse": "D-WH"}]}
            ),
        }
        voucher = Document(
            {
                "doctype": "Landed Cost Voucher",
                "purchase_receipts": [
                    {"receipt_document_type": source.doctype, "receipt_document": name}
                    for name, source in sources.items()
                ],
            }
        )
        with (
            patch.object(
                stock_reconciliation_freeze,
                "locked_document",
                side_effect=lambda _type, name: sources[name],
            ) as get_doc,
            patch.object(stock_reconciliation_freeze, "lock_warehouses"),
            patch.object(repost_item_valuation_reservation, "check_foreground_repost"),
            patch.object(stock_reconciliation_freeze, "_check_item_level", return_value=[]) as check_items,
            patch.object(
                stock_reconciliation_freeze, "_check_warehouse_level", return_value=[]
            ) as check_warehouses,
            patch(
                "connect_diagnostics_core.api.erpnext.stock_entry_workflow.is_authorized_freeze_exception"
            ) as emergency,
        ):
            stock_reconciliation_freeze.validate_transaction(voucher)
        self.assertEqual(get_doc.call_count, 4)
        check_items.assert_called_once_with(
            {("A", "A-WH"), ("B", "B-WH"), ("C", "C-WH"), ("D", "D-WH")}, exclude_name=None
        )
        check_warehouses.assert_called_once_with({"A-WH", "B-WH", "C-WH", "D-WH"}, exclude_name=None)
        emergency.assert_not_called()

    def test_physical_repost_blocks_approved_emergency_before_exception(self) -> None:
        movement = _doc(
            workflow_state="Emergency Stock Movement Submitted",
            items=[{"item_code": "ITEM-A", "s_warehouse": "WH-1"}],
        )
        with (
            patch.object(stock_reconciliation_freeze, "lock_warehouses"),
            patch.object(
                repost_item_valuation_reservation,
                "check_foreground_repost",
                side_effect=frappe.ValidationError("repost in progress"),
            ) as repost_guard,
            patch(
                "connect_diagnostics_core.api.erpnext.stock_entry_workflow.is_authorized_freeze_exception"
            ) as emergency,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_reconciliation_freeze.validate_transaction(movement)
        repost_guard.assert_called_once_with({"WH-1"})
        emergency.assert_not_called()

    def test_landed_cost_missing_or_unsupported_receipt_fails_closed(self) -> None:
        for row in (
            {"receipt_document_type": "Stock Entry"},
            {"receipt_document_type": "Journal Entry", "receipt_document": "JE-1"},
        ):
            with (
                self.subTest(row=row),
                patch.object(stock_reconciliation_freeze.frappe, "get_doc") as get_doc,
            ):
                with self.assertRaises(frappe.ValidationError):
                    stock_reconciliation_freeze.validate_transaction(
                        Document({"doctype": "Landed Cost Voucher", "purchase_receipts": [row]})
                    )
                get_doc.assert_not_called()

    def test_physical_hook_coverage_preserves_existing_callback_order(self) -> None:
        guard = "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction"
        for doctype in (
            "Stock Entry",
            "Purchase Receipt",
            "Delivery Note",
            "Sales Invoice",
            "Purchase Invoice",
            "Stock Reconciliation",
            "Subcontracting Receipt",
            "Asset Capitalization",
            "Landed Cost Voucher",
        ):
            with self.subTest(doctype=doctype):
                events = hooks.doc_events[doctype]
                for event in ("before_submit", "before_cancel"):
                    handlers = events[event]
                    self.assertIn(guard, handlers if isinstance(handlers, list) else [handlers])
        self.assertNotIn("before_cancel", hooks.doc_events["Pick List"])
        self.assertEqual(hooks.doc_events["Stock Entry"]["before_cancel"][-1], guard)
        self.assertEqual(hooks.doc_events["Purchase Invoice"]["before_cancel"][-1], guard)
        self.assertEqual(hooks.doc_events["Stock Reconciliation"]["before_cancel"][-1], guard)
