# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.goods_receipt_report import (
    goods_receipt_report,
)


class TestFillExpiryDates(UnitTestCase):
    @patch.object(goods_receipt_report.frappe, "get_all", return_value=[("_Test GRR Batch", "2027-01-01")])
    def test_fills_expiry_only_for_rows_with_a_batch(self, mocked_get_all) -> None:
        rows = [
            frappe._dict({"batch_no": "_Test GRR Batch", "expiry_date": None}),
            frappe._dict({"batch_no": None, "expiry_date": None}),
        ]

        goods_receipt_report._fill_expiry_dates(rows)

        mocked_get_all.assert_called_once_with(
            "Batch",
            filters={"name": ("in", ["_Test GRR Batch"])},
            fields=["name", "expiry_date"],
            as_list=True,
        )
        self.assertEqual(rows[0].expiry_date, "2027-01-01")
        self.assertIsNone(rows[1].expiry_date)


class TestGoodsReceiptReportValidation(IntegrationTestCase):
    def test_company_is_required(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "Company is required"):
            goods_receipt_report.execute({})

    def test_date_range_validation(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "From Date cannot be greater than To Date"):
            goods_receipt_report.execute(
                {"company": "_Test Company", "from_date": "2026-08-10", "to_date": "2026-08-01"}
            )

    def test_report_metadata_has_no_total_and_expected_access(self) -> None:
        metadata = cast(
            dict[str, Any],
            json.loads(Path(__file__).with_name("goods_receipt_report.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(metadata["add_total_row"], 0)
        self.assertEqual(metadata["ref_doctype"], "Purchase Receipt")
        self.assertEqual(metadata["module"], "Connect Diagnostics Stock")
        self.assertEqual(
            {role["role"] for role in metadata["roles"]},
            {"Stock User", "Stock Manager"},
        )
