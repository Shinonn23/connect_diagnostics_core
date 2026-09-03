# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback hook for :mod:`add_quotation_print_signatures`.

The forward patch fills legacy blank values, but those rows are indistinguishable
from a Sales Representative value that a user subsequently entered. Clearing
every matching value would therefore erase legitimate business data. As with
the other data backfills in this app, rollback is a deliberate no-op; restore
from a database backup if a full migration reversal is required.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    """Do not destructively clear values that may have been edited later."""
    frappe.logger(__name__).info(
        "rollback_add_quotation_print_signatures: no-op; fallback values are not "
        "automatically reversible (restore from a database backup if required)."
    )
