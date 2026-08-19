from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from frappe.tests import UnitTestCase

from connect_diagnostics_core.utils.date import format_date


class TestFormatDate(UnitTestCase):
    def test_formats_date_as_dd_mm_yyyy_in_buddhist_era(self) -> None:
        self.assertEqual(format_date(date(2026, 7, 3)), "03-07-2569")

    def test_pads_single_digit_day_and_month(self) -> None:
        self.assertEqual(format_date(date(2026, 1, 5)), "05-01-2569")

    def test_accepts_string_input(self) -> None:
        self.assertEqual(format_date("2026-07-03"), "03-07-2569")

    def test_accepts_datetime_input(self) -> None:
        self.assertEqual(format_date(datetime(2026, 7, 3, 14, 30, 0)), "03-07-2569")

    def test_returns_empty_string_for_none(self) -> None:
        self.assertEqual(format_date(None), "")

    def test_returns_empty_string_for_empty_string(self) -> None:
        self.assertEqual(format_date(""), "")


class TestCdPrintFormatsUseFormatDate(UnitTestCase):
    """Guard: dated print formats use the shared format_date Jinja method,
    never a per-format macro or an inline era/format conversion.
    """

    DATE_FIELD_PATTERN = re.compile(r"""(?:\b[a-z_]+\.[a-z_]*date\b|["'][a-z_]*date["'])""")
    FORBIDDEN = ("be_date", "thai_date", "frappe.format_date", "+ 543", "thmonths")

    def _assert_uses_format_date(self, print_format: Path) -> None:
        html = json.loads(print_format.read_text())["html"]
        if self.DATE_FIELD_PATTERN.search(html):
            self.assertIn("format_date(", html)
        for token in self.FORBIDDEN:
            self.assertNotIn(token, html)

    def test_module_print_formats_use_format_date(self) -> None:
        root = Path(__file__).resolve().parents[2] / "connect_diagnostics_print" / "print_format"
        print_formats = sorted(root.glob("*/*.json"))

        self.assertEqual(len(print_formats), 12)

        for print_format in print_formats:
            with self.subTest(print_format=print_format.name):
                self._assert_uses_format_date(print_format)
