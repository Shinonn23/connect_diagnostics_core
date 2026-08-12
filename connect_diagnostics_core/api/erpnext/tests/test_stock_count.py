# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_count


def _candidates() -> list[dict]:
    return [
        {
            "item_code": f"ITEM-{i}",
            "warehouse": "WH",
            "storage_location": None,
            "batch_no": None,
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

    def test_random_by_count_limits_to_sample_items(self) -> None:
        doc = SimpleNamespace(
            count_type=stock_count.MONTHLY, selection_method="Random by Count", sample_count=3
        )
        result = stock_count._apply_selection(doc, _candidates())
        self.assertEqual(len({line["item_code"] for line in result}), 3)

    def test_random_by_count_caps_at_available_items(self) -> None:
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
        # ceil(10 * 0.25) == 3 distinct items
        self.assertEqual(
            len({line["item_code"] for line in stock_count._apply_selection(doc, _candidates())}), 3
        )

    def test_random_by_zone_returns_all_prefiltered_candidates(self) -> None:
        doc = SimpleNamespace(count_type=stock_count.MONTHLY, selection_method="Random by Zone")
        self.assertEqual(len(stock_count._apply_selection(doc, _candidates())), 10)


class TestFetchItems(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = frappe.get_doc(
            {
                "doctype": "Stock Count",
                "count_type": stock_count.MONTHLY,
                "company": "_Test Company",
                "warehouse": "_Test Warehouse - _TC",
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
                "storage_location": None,
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
