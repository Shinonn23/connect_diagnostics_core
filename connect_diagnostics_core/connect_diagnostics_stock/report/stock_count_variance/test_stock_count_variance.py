# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.stock_count_variance import (
    stock_count_variance,
)

TEST_COMPANY = "_Test Company"
TEST_WAREHOUSE = "_Test Warehouse - _TC"


class TestStockCountVariance(IntegrationTestCase):
    matched: Any
    monthly_variance: Any
    yearly_variance: Any

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.matched = cls._make_stock_count(
            "_Test SCV Matched",
            "Cycle Count (Monthly)",
            [{"item_code": "_Test Item", "system_qty": 10, "count_qty": 10, "valuation_rate": 5}],
        )
        cls.monthly_variance = cls._make_stock_count(
            "_Test SCV Monthly Variance",
            "Cycle Count (Monthly)",
            [{"item_code": "_Test Item", "system_qty": 10, "count_qty": 8, "valuation_rate": 5}],
        )
        cls.yearly_variance = cls._make_stock_count(
            "_Test SCV Yearly Variance",
            "Yearly Count",
            [{"item_code": "_Test Item 2", "system_qty": 5, "count_qty": 7, "valuation_rate": 3}],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        for doc in (cls.matched, cls.monthly_variance, cls.yearly_variance):
            frappe.delete_doc("Stock Count", doc.name, force=True, ignore_permissions=True)
        super().tearDownClass()

    @classmethod
    def _make_stock_count(cls, name: str, count_type: str, items: list[dict[str, Any]]) -> Any:
        for item in items:
            item.setdefault("warehouse", TEST_WAREHOUSE)
        return frappe.get_doc(
            {
                "doctype": "Stock Count",
                "name": name,
                "count_type": count_type,
                "company": TEST_COMPANY,
                "warehouse": TEST_WAREHOUSE,
                "posting_date": "2026-08-12",
                "posting_time": "10:00:00",
                "items": items,
            }
        ).insert(ignore_permissions=True)

    def _run_report(self, **filters: Any) -> list[stock_count_variance.ReportRow]:
        report_filters = {"company": TEST_COMPANY, **filters}
        return stock_count_variance.execute(report_filters)[1]

    def test_matched_lines_are_excluded(self) -> None:
        self.assertEqual(self._run_report(stock_count=self.matched.name), [])

    def test_variance_lines_report_values(self) -> None:
        rows = self._run_report(stock_count=self.monthly_variance.name)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.item_code, "_Test Item")
        self.assertEqual(row.system_qty, 10)
        self.assertEqual(row.count_qty, 8)
        self.assertEqual(row.variance_qty, -2)
        self.assertEqual(row.valuation_rate, 5)
        self.assertAlmostEqual(cast(float, row.variance_value), -10)

    def test_count_type_filter(self) -> None:
        rows = self._run_report(count_type="Yearly Count")
        self.assertEqual([row.stock_count for row in rows], [self.yearly_variance.name])

    def test_company_is_required(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "Company is required"):
            stock_count_variance.execute({})

    def test_report_metadata_has_no_total_and_expected_access(self) -> None:
        metadata = cast(
            dict[str, Any],
            json.loads(Path(__file__).with_name("stock_count_variance.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(metadata["add_total_row"], 0)
        self.assertEqual(metadata["ref_doctype"], "Stock Count")
        self.assertEqual(metadata["module"], "Connect Diagnostics Stock")
        self.assertEqual(
            {role["role"] for role in metadata["roles"]},
            {"Stock User", "Stock Manager", "Accounts Manager"},
        )
