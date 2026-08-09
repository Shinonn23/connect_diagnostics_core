# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.utils import flt, fmt_money


def format_money(amount: float | int | str | None, blank_zero: bool = False) -> str:
    """Format an amount with a thousands separator and two decimal places."""
    value = flt(amount)
    if blank_zero and value == 0:
        return ""

    return f"{value:,.2f}"


def print_currency(amount: float | int | str | None, currency: str | None = None) -> str:
    """
    Convert a number to a formatted currency string.

    :param amount: The amount to be formatted.
    :param currency: The currency code (e.g., 'USD', 'THB'). If None, it will use the default currency.
    :return: A formatted currency string.
    """
    return fmt_money(amount, currency=currency)
