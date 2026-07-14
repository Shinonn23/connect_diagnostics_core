from __future__ import annotations

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
