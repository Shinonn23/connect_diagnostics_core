# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.short_expiry_report import (
    short_expiry_report,
)


def _row(**overrides: Any) -> Any:
    data = {"expiry_date": "2026-08-20", "min_remaining_shelf_life": 30}
    data.update(overrides)
    return SimpleNamespace(**data)


class TestShortExpiryThreshold(UnitTestCase):
    def test_uses_item_threshold_when_no_override_given(self) -> None:
        row = _row(min_remaining_shelf_life=30)
        self.assertTrue(short_expiry_report._is_within_threshold(row, "2026-08-01", None))

    def test_item_without_threshold_and_no_override_is_skipped(self) -> None:
        row = _row(min_remaining_shelf_life=0)
        self.assertFalse(short_expiry_report._is_within_threshold(row, "2026-08-01", None))

    def test_override_takes_precedence_over_item_threshold(self) -> None:
        row = _row(min_remaining_shelf_life=5)
        # Item threshold (5 days) would exclude this row 19 days out; the override includes it.
        self.assertTrue(short_expiry_report._is_within_threshold(row, "2026-08-01", 30))

    def test_already_expired_rows_are_included(self) -> None:
        row = _row(expiry_date="2026-07-01", min_remaining_shelf_life=30)
        self.assertTrue(short_expiry_report._is_within_threshold(row, "2026-08-01", None))
        self.assertLess(row.days_remaining, 0)

    def test_row_outside_threshold_is_excluded(self) -> None:
        row = _row(expiry_date="2026-12-01", min_remaining_shelf_life=30)
        self.assertFalse(short_expiry_report._is_within_threshold(row, "2026-08-01", None))


class TestShortExpiryReportValidation(IntegrationTestCase):
    def test_company_is_required(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "Company is required"):
            short_expiry_report.execute({})

    def test_report_metadata_has_no_total_and_expected_access(self) -> None:
        metadata = cast(
            dict[str, Any],
            json.loads(Path(__file__).with_name("short_expiry_report.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(metadata["add_total_row"], 0)
        self.assertEqual(metadata["ref_doctype"], "Item")
        self.assertEqual(metadata["module"], "Connect Diagnostics Stock")
        self.assertEqual(
            {role["role"] for role in metadata["roles"]},
            {"Stock User", "Stock Manager"},
        )
