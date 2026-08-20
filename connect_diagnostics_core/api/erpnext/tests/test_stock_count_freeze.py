# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_count, stock_count_freeze

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
OTHER_WAREHOUSE = "_Test Warehouse 1 - _TC"


def _draft_stock_count(**overrides: object) -> Document:
    data: dict[str, object] = {
        "doctype": "Stock Count",
        "count_type": stock_count.MONTHLY,
        "company": COMPANY,
        "warehouses": [{"warehouse": WAREHOUSE}],
        "posting_date": "2026-08-12",
        "posting_time": "10:00:00",
        "selection_method": "Manual",
        "items": [{"item_code": "_Test Item", "warehouse": WAREHOUSE, "system_qty": 0}],
    }
    data.update(overrides)
    return frappe.get_doc(data).insert(ignore_permissions=True)


def _receipt_entry(item_code: str, warehouse: str) -> StockEntry:
    entry = cast(StockEntry, frappe.new_doc("Stock Entry"))
    entry.stock_entry_type = "Material Receipt"
    entry.company = COMPANY
    entry.posting_date = "2026-08-12"
    entry.posting_time = "11:00:00"
    entry.set_posting_time = 1
    entry.append(
        "items",
        {
            "item_code": item_code,
            "qty": 1,
            "uom": "_Test UOM",
            "stock_uom": "_Test UOM",
            "conversion_factor": 1,
            "basic_rate": 10,
            "t_warehouse": warehouse,
        },
    )
    return entry.insert(ignore_permissions=True)


def _dict_doc(**fields: Any) -> Any:
    return frappe._dict(fields)


class TestRowsToCheck(UnitTestCase):
    def test_extracts_item_warehouse_pairs_for_stock_entry(self) -> None:
        doc = _dict_doc(
            doctype="Stock Entry",
            items=[
                _dict_doc(item_code="ITEM-A", s_warehouse="WH-1", t_warehouse=""),
                _dict_doc(item_code="ITEM-B", s_warehouse="", t_warehouse="WH-2"),
            ],
        )
        pairs, warehouses = stock_count_freeze._rows_to_check(doc)
        self.assertEqual(pairs, {("ITEM-A", "WH-1"), ("ITEM-B", "WH-2")})
        self.assertEqual(warehouses, {"WH-1", "WH-2"})

    def test_unmapped_doctype_yields_nothing(self) -> None:
        doc = _dict_doc(doctype="Journal Entry", items=[])
        pairs, warehouses = stock_count_freeze._rows_to_check(doc)
        self.assertEqual(pairs, set())
        self.assertEqual(warehouses, set())


class TestValidateTransactionSkipsWhenNotMovingStock(UnitTestCase):
    def test_sales_invoice_without_update_stock_is_skipped(self) -> None:
        doc = _dict_doc(doctype="Sales Invoice", update_stock=0)
        # Should return immediately without touching the database.
        stock_count_freeze.validate_transaction(doc)


class TestStockCountFreezeIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

    def test_monthly_freeze_blocks_matching_item_and_warehouse(self) -> None:
        count = _draft_stock_count()
        with self.assertRaises(frappe.ValidationError):
            _receipt_entry("_Test Item", WAREHOUSE).submit()
        frappe.delete_doc("Stock Count", count.name, force=True, ignore_permissions=True)

    def test_monthly_freeze_does_not_block_a_different_item(self) -> None:
        count = _draft_stock_count()
        entry = _receipt_entry("_Test Item 2", WAREHOUSE)
        entry.submit()
        self.assertEqual(entry.docstatus, 1)
        frappe.delete_doc("Stock Count", count.name, force=True, ignore_permissions=True)

    def test_monthly_freeze_does_not_block_a_different_warehouse(self) -> None:
        count = _draft_stock_count()
        entry = _receipt_entry("_Test Item", OTHER_WAREHOUSE)
        entry.submit()
        self.assertEqual(entry.docstatus, 1)
        frappe.delete_doc("Stock Count", count.name, force=True, ignore_permissions=True)

    def test_draft_with_no_fetched_items_does_not_block(self) -> None:
        count = _draft_stock_count(items=[])
        entry = _receipt_entry("_Test Item", WAREHOUSE)
        entry.submit()
        self.assertEqual(entry.docstatus, 1)
        frappe.delete_doc("Stock Count", count.name, force=True, ignore_permissions=True)

    def test_freeze_releases_once_stock_count_is_submitted(self) -> None:
        count = _draft_stock_count()
        count.db_set("docstatus", 1, update_modified=False)
        entry = _receipt_entry("_Test Item", WAREHOUSE)
        entry.submit()
        self.assertEqual(entry.docstatus, 1)
        # Submitted (docstatus=1) Stock Counts are left in place -- IntegrationTestCase
        # rolls back the whole class's DB changes, matching test_stock_count_adjustments.py.

    def test_yearly_freeze_blocks_any_item_in_the_selected_warehouse(self) -> None:
        count = _draft_stock_count(
            count_type=stock_count.YEARLY,
            warehouses=[{"warehouse": WAREHOUSE}],
            items=[{"item_code": "_Test Item", "warehouse": WAREHOUSE, "system_qty": 0}],
        )
        with self.assertRaises(frappe.ValidationError):
            _receipt_entry("_Test Item 2", WAREHOUSE).submit()
        frappe.delete_doc("Stock Count", count.name, force=True, ignore_permissions=True)
