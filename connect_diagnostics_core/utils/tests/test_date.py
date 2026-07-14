from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest import TestCase

from connect_diagnostics_core.utils.date import format_date


class TestFormatDate(TestCase):
    def test_formats_date_as_dd_mm_yyyy(self) -> None:
        self.assertEqual(format_date(date(2026, 7, 3)), "03-07-2026")

    def test_pads_single_digit_day_and_month(self) -> None:
        self.assertEqual(format_date(date(2026, 1, 5)), "05-01-2026")

    def test_accepts_string_input(self) -> None:
        self.assertEqual(format_date("2026-07-03"), "03-07-2026")

    def test_accepts_datetime_input(self) -> None:
        self.assertEqual(format_date(datetime(2026, 7, 3, 14, 30, 0)), "03-07-2026")

    def test_returns_empty_string_for_none(self) -> None:
        self.assertEqual(format_date(None), "")

    def test_returns_empty_string_for_empty_string(self) -> None:
        self.assertEqual(format_date(""), "")


class TestCdPrintFormatsUseFormatDate(TestCase):
    """Guard: every print format renders dates through the shared format_date
    Jinja method — never a per-format macro or an inline era/format conversion.
    """

    FORBIDDEN = ("be_date", "thai_date", "frappe.format_date", "+ 543", "thmonths")

    def _assert_uses_format_date(self, print_format: Path) -> None:
        html = json.loads(print_format.read_text())["html"]
        self.assertIn("format_date(", html)
        for token in self.FORBIDDEN:
            self.assertNotIn(token, html)

    def test_module_print_formats_use_format_date(self) -> None:
        root = Path(__file__).resolve().parents[2] / "connect_diagnostics_core" / "print_format"
        print_formats = sorted(root.glob("*/*.json"))

        self.assertEqual(len(print_formats), 8)

        for print_format in print_formats:
            with self.subTest(print_format=print_format.name):
                self._assert_uses_format_date(print_format)
