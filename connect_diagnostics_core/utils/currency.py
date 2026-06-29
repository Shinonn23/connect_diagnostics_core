from frappe.utils import fmt_money


def print_currency(amount, currency=None):
    """
    Convert a number to a formatted currency string.

    :param amount: The amount to be formatted.
    :param currency: The currency code (e.g., 'USD', 'THB'). If None, it will use the default currency.
    :return: A formatted currency string.
    """
    return fmt_money(amount, currency=currency)
