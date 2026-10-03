# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_count


def _candidates() -> list[dict]:
    # 10 lines but only 5 distinct item codes: each item appears as two batches,
    # so a line-level sample must not collapse to item-level counting.
    return [
        {
            "item_code": f"ITEM-{i % 5}",
            "warehouse": "WH",
            "batch_no": f"BATCH-{i}",
            "serial_no": None,
            "system_qty": float(i + 1),
            "valuation_rate": 0.0,
        }
        for i in range(10)
    ]


class TestStockCountSelection(UnitTestCase):
    def test_yearly_returns_all_candidates(self) -> None:
        doc = SimpleNamespace(count_type=stock_count.YEARLY, selection_method="Manual")
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 10)

    def test_manual_returns_all_candidates(self) -> None:
        doc = SimpleNamespace(count_type=stock_count.MONTHLY, selection_method="Manual")
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 10)

    def test_random_by_count_limits_total_lines(self) -> None:
        doc = SimpleNamespace(
            count_type=stock_count.MONTHLY, selection_method="Random by Count", sample_count=3
        )
        result = stock_count._apply_selection(doc, _candidates())
        # 3 lines total (batch/serial counted separately), not 3 items' worth of lines.
        self.assertEqual(len(result), 3)

    def test_random_by_count_caps_at_available_lines(self) -> None:
        doc = SimpleNamespace(
            count_type=stock_count.MONTHLY, selection_method="Random by Count", sample_count=99
        )
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 10)

    def test_random_by_percentage_rounds_up(self) -> None:
        doc = SimpleNamespace(
            count_type=stock_count.MONTHLY,
            selection_method="Random by Percentage",
            sample_percentage=25,
        )
        # ceil(10 lines * 0.25) == 3 lines
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 3)

    def test_random_by_warehouse_returns_all_prefiltered_candidates(self) -> None:
        doc = SimpleNamespace(count_type=stock_count.MONTHLY, selection_method="Random by Warehouse")
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 10)


class TestFetchItems(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = frappe.get_doc(
            {
                "doctype": "Stock Count",
                "count_type": stock_count.MONTHLY,
                "company": "_Test Company",
                "warehouses": [{"warehouse": "_Test Warehouse - _TC"}],
                "posting_date": "2026-08-12",
                "posting_time": "10:00:00",
                "selection_method": "Manual",
                "items": [{"item_code": "_Test Item", "system_qty": 0}],
            }
        ).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.delete_doc("Stock Count", self.doc.name, force=True)

    def _fetched_rows(self) -> list[dict]:
        return [
            {
                "item_code": "_Test Item",
                "item_name": "_Test Item",
                "stock_uom": "_Test UOM",
                "warehouse": "_Test Warehouse - _TC",
                "batch_no": None,
                "serial_no": None,
                "system_qty": 12.0,
                "valuation_rate": 0.0,
            },
        ]

    def test_fetch_populates_lines_with_blank_count(self) -> None:
        with patch.object(stock_count, "_candidate_lines", return_value=self._fetched_rows()):
            result = stock_count.fetch_items(self.doc.name)

        self.assertEqual(result["data"]["count"], 1)
        self.doc.reload()
        self.assertEqual(self.doc.items[0].system_qty, 12.0)
        self.assertEqual(self.doc.items[0].count_qty, 0)

    def test_refetch_preserves_entered_counts(self) -> None:
        with patch.object(stock_count, "_candidate_lines", return_value=self._fetched_rows()):
            stock_count.fetch_items(self.doc.name)
        self.doc.reload()
        self.doc.items[0].count_qty = 9
        self.doc.save(ignore_permissions=True)

        with patch.object(stock_count, "_candidate_lines", return_value=self._fetched_rows()):
            stock_count.fetch_items(self.doc.name)
        self.doc.reload()
        self.assertEqual(self.doc.items[0].count_qty, 9)


class TestFetchItemsRandomByWarehouse(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = frappe.get_doc(
            {
                "doctype": "Stock Count",
                "count_type": stock_count.MONTHLY,
                "company": "_Test Company",
                "warehouses": [
                    {"warehouse": "_Test Warehouse - _TC"},
                    {"warehouse": "_Test Warehouse 1 - _TC"},
                ],
                "posting_date": "2026-08-12",
                "posting_time": "10:00:00",
                "selection_method": "Random by Warehouse",
                "items": [],
            }
        ).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.delete_doc("Stock Count", self.doc.name, force=True)

    def test_narrows_candidates_to_one_randomly_chosen_warehouse(self) -> None:
        captured: dict = {}

        def fake_candidate_lines(company, warehouses, cutoff):
            captured["warehouses"] = warehouses
            return []

        with (
            patch.object(stock_count.random, "choice", return_value="_Test Warehouse 1 - _TC"),
            patch.object(stock_count, "_candidate_lines", side_effect=fake_candidate_lines),
        ):
            result = stock_count.fetch_items(self.doc.name)

        self.assertEqual(captured["warehouses"], ["_Test Warehouse 1 - _TC"])
        self.assertIn("_Test Warehouse 1 - _TC", result["message"])
