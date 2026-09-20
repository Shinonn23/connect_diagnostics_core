# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count.stock_count import (
    MONTHLY,
    StockCount,
)


def _draft(**overrides: object) -> StockCount:
    """Build an unsaved Stock Count for direct controller-method testing."""
    data: dict[str, object] = {
        "doctype": "Stock Count",
        "count_type": MONTHLY,
        "company": "_Test Company",
        "warehouse": "_Test Warehouse - _TC",
        "posting_date": "2026-08-12",
        "posting_time": "10:00:00",
    }
    data.update(overrides)
    return frappe.get_doc(data)


class TestStockCount(IntegrationTestCase):
    def test_update_variance_rolls_up_totals(self) -> None:
        doc = _draft(
            items=[
                {"item_code": "_Test Item", "system_qty": 10, "count_qty": 8},
                {"item_code": "_Test Item 2", "system_qty": 5, "count_qty": 7},
            ]
        )
        doc.update_variance()
        self.assertEqual(doc.items[0].variance_qty, -2)
        self.assertEqual(doc.items[1].variance_qty, 2)
        self.assertEqual(doc.total_variance_qty, 0)

    def test_rejects_duplicate_count_lines(self) -> None:
        doc = _draft(
            items=[
                {"item_code": "_Test Item", "warehouse": "_Test Warehouse - _TC"},
                {"item_code": "_Test Item", "warehouse": "_Test Warehouse - _TC"},
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            doc.validate_duplicate_lines()

    def test_allows_same_item_in_different_locations(self) -> None:
        doc = _draft(
            items=[
                {"item_code": "_Test Item", "storage_location": "_Test Storage A"},
                {"item_code": "_Test Item", "storage_location": "_Test Storage B"},
            ]
        )
        doc.validate_duplicate_lines()

    def test_random_by_count_requires_positive_sample(self) -> None:
        doc = _draft(selection_method="Random by Count", sample_count=0)
        with self.assertRaises(frappe.ValidationError):
            doc.validate_scope()

    def test_random_by_zone_requires_storage_location(self) -> None:
        doc = _draft(selection_method="Random by Zone")
        with self.assertRaises(frappe.ValidationError):
            doc.validate_scope()

    def test_before_submit_requires_lines(self) -> None:
        doc = _draft()
        with self.assertRaises(frappe.ValidationError):
            doc.before_submit()
