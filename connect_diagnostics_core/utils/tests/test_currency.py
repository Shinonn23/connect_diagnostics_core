from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from connect_diagnostics_core.utils.currency import print_currency


class TestPrintCurrency(TestCase):
    @patch("connect_diagnostics_core.utils.currency.fmt_money")
    def test_passes_currency_as_keyword_argument(self, fmt_money) -> None:
        print_currency(1234.5, "USD")

        fmt_money.assert_called_once_with(1234.5, currency="USD")

    @patch("connect_diagnostics_core.utils.currency.fmt_money")
    def test_supports_default_currency(self, fmt_money) -> None:
        print_currency(1234.5)

        fmt_money.assert_called_once_with(1234.5, currency=None)


class TestCdPrintFormats(TestCase):
    def test_currency_values_use_print_currency(self) -> None:
        print_format_root = Path(__file__).resolve().parents[2] / "connect_diagnostics_core" / "print_format"
        print_formats = sorted(print_format_root.glob("*/*.json"))

        self.assertEqual(len(print_formats), 8)

        for print_format in print_formats:
            with self.subTest(print_format=print_format.name):
                html = json.loads(print_format.read_text())["html"]

                self.assertNotIn("frappe.utils.fmt_money", html)
                self.assertNotIn('"{:,.2f}".format', html)
                self.assertIn("print_currency", html)
