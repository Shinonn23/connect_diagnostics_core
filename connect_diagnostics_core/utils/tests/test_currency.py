# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.utils.currency import format_money, print_currency


class TestFormatMoney(UnitTestCase):
    def test_formats_none_as_zero(self) -> None:
        self.assertEqual(format_money(None), "0.00")

    def test_formats_zero(self) -> None:
        self.assertEqual(format_money(0), "0.00")

    def test_formats_thousands(self) -> None:
        self.assertEqual(format_money(1234), "1,234.00")

    def test_formats_decimal_amount(self) -> None:
        self.assertEqual(format_money(1234.5), "1,234.50")

    def test_formats_negative_amount(self) -> None:
        self.assertEqual(format_money(-1234.5), "-1,234.50")

    def test_blanks_zero_when_requested(self) -> None:
        self.assertEqual(format_money(0, blank_zero=True), "")

    def test_does_not_blank_nonzero_when_requested(self) -> None:
        self.assertEqual(format_money(0.01, blank_zero=True), "0.01")


class TestPrintCurrency(UnitTestCase):
    @patch("connect_diagnostics_core.utils.currency.fmt_money")
    def test_passes_currency_as_keyword_argument(self, fmt_money) -> None:
        print_currency(1234.5, "USD")

        fmt_money.assert_called_once_with(1234.5, currency="USD")

    @patch("connect_diagnostics_core.utils.currency.fmt_money")
    def test_supports_default_currency(self, fmt_money) -> None:
        print_currency(1234.5)

        fmt_money.assert_called_once_with(1234.5, currency=None)
