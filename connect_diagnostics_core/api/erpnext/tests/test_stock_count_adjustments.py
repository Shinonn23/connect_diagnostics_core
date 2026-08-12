# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import stock_count
from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count.stock_count import (
    StockCount,
)
from connect_diagnostics_core.setup.stock_count import APPROVED

HOLDING_WAREHOUSE = "_Test Stock Count Holding - _TC"


def _ensure_holding_warehouse() -> str:
    if not frappe.db.exists("Warehouse", HOLDING_WAREHOUSE):
        frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "_Test Stock Count Holding",
                "company": "_Test Company",
            }
        ).insert(ignore_permissions=True)
    return HOLDING_WAREHOUSE


def _approved_stock_count(**overrides: object) -> StockCount:
    data: dict[str, object] = {
        "doctype": "Stock Count",
        "count_type": stock_count.MONTHLY,
        "company": "_Test Company",
        "warehouse": "_Test Warehouse - _TC",
        "posting_date": "2026-08-12",
        "posting_time": "10:00:00",
        "selection_method": "Manual",
        "holding_warehouse": _ensure_holding_warehouse(),
        "items": [
            {
                "item_code": "_Test Item",
                "warehouse": "_Test Warehouse - _TC",
                "stock_uom": "_Test UOM",
                "system_qty": 10,
                "count_qty": 8,
            }
        ],
    }
    data.update(overrides)
    doc = cast(StockCount, frappe.get_doc(data)).insert(ignore_permissions=True)
    doc.db_set("docstatus", 1, update_modified=False)
    doc.db_set("count_state", APPROVED, update_modified=False)
    doc.reload()
    return cast(StockCount, doc)


class TestGenerateHoldingTransfer(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = _approved_stock_count()

    def tearDown(self) -> None:
        frappe.delete_doc("Stock Count", self.doc.name, force=True, ignore_permissions=True)

    def test_creates_submitted_material_transfer(self) -> None:
        result = stock_count.generate_holding_transfer(self.doc.name)

        entry_name = result["data"]["stock_entry"]
        entry = cast(StockEntry, frappe.get_doc("Stock Entry", entry_name))
        self.assertEqual(entry.docstatus, 1)
        self.assertEqual(entry.purpose, "Material Transfer")
        self.assertEqual(entry.from_warehouse, "_Test Warehouse - _TC")
        self.assertEqual(entry.to_warehouse, HOLDING_WAREHOUSE)
        self.assertEqual(entry.items[0].qty, 2)
        self.assertEqual(entry.get("stock_count"), self.doc.name)

        self.doc.reload()
        self.assertEqual(len(self.doc.adjustments), 1)
        self.assertEqual(self.doc.adjustments[0].entry_type, "Material Transfer")

    def test_rejects_second_generation(self) -> None:
        stock_count.generate_holding_transfer(self.doc.name)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_holding_transfer(self.doc.name)

    def test_rejects_yearly_count(self) -> None:
        yearly = _approved_stock_count(count_type=stock_count.YEARLY)
        try:
            with self.assertRaises(frappe.ValidationError):
                stock_count.generate_holding_transfer(yearly.name)
        finally:
            frappe.delete_doc("Stock Count", yearly.name, force=True, ignore_permissions=True)

    def test_no_op_when_no_variance(self) -> None:
        matched = _approved_stock_count(
            items=[
                {
                    "item_code": "_Test Item",
                    "warehouse": "_Test Warehouse - _TC",
                    "stock_uom": "_Test UOM",
                    "system_qty": 10,
                    "count_qty": 10,
                }
            ]
        )
        try:
            result = stock_count.generate_holding_transfer(matched.name)
            self.assertIsNone(result["data"])
        finally:
            frappe.delete_doc("Stock Count", matched.name, force=True, ignore_permissions=True)


class TestGenerateStockAdjustment(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = _approved_stock_count(
            count_type=stock_count.YEARLY,
            items=[
                {
                    "item_code": "_Test Item",
                    "warehouse": "_Test Warehouse - _TC",
                    "stock_uom": "_Test UOM",
                    "system_qty": 10,
                    "count_qty": 8,
                },
                {
                    "item_code": "_Test Item 2",
                    "warehouse": "_Test Warehouse - _TC",
                    "stock_uom": "_Test UOM",
                    "system_qty": 5,
                    "count_qty": 7,
                },
            ],
        )

    def tearDown(self) -> None:
        frappe.delete_doc("Stock Count", self.doc.name, force=True, ignore_permissions=True)

    def test_posts_receipt_for_surplus_and_issue_for_shortage(self) -> None:
        result = stock_count.generate_stock_adjustment(self.doc.name)

        receipt = cast(StockEntry, frappe.get_doc("Stock Entry", result["data"]["receipt_entry"]))
        self.assertEqual(receipt.purpose, "Material Receipt")
        self.assertEqual(receipt.items[0].qty, 2)
        self.assertEqual(receipt.items[0].t_warehouse, "_Test Warehouse - _TC")

        issue = cast(StockEntry, frappe.get_doc("Stock Entry", result["data"]["issue_entry"]))
        self.assertEqual(issue.purpose, "Material Issue")
        self.assertEqual(issue.items[0].qty, 2)
        self.assertEqual(issue.items[0].s_warehouse, "_Test Warehouse - _TC")

        self.doc.reload()
        entry_types = {row.entry_type for row in self.doc.adjustments}
        self.assertEqual(entry_types, {"Material Receipt", "Material Issue"})

    def test_rejects_second_generation(self) -> None:
        stock_count.generate_stock_adjustment(self.doc.name)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_stock_adjustment(self.doc.name)

    def test_rejects_monthly_count(self) -> None:
        monthly = _approved_stock_count()
        try:
            with self.assertRaises(frappe.ValidationError):
                stock_count.generate_stock_adjustment(monthly.name)
        finally:
            frappe.delete_doc("Stock Count", monthly.name, force=True, ignore_permissions=True)

    def test_rejects_when_not_approved(self) -> None:
        draft = frappe.get_doc(
            {
                "doctype": "Stock Count",
                "count_type": stock_count.YEARLY,
                "company": "_Test Company",
                "warehouse": "_Test Warehouse - _TC",
                "posting_date": "2026-08-12",
                "posting_time": "10:00:00",
                "items": [
                    {
                        "item_code": "_Test Item",
                        "warehouse": "_Test Warehouse - _TC",
                        "system_qty": 10,
                        "count_qty": 8,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        try:
            with self.assertRaises(frappe.ValidationError):
                stock_count.generate_stock_adjustment(draft.name)
        finally:
            frappe.delete_doc("Stock Count", draft.name, force=True, ignore_permissions=True)
