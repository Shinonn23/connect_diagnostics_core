# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback marker for clear_legacy_tds_values.

The forward patch intentionally removes unposted legacy TDS values and draft
Tax Withholding Entry rows.  Those values are not recoverable by a code rollback;
restore them from the database backup taken before migration.  This module is
kept as an explicit one-way rollback marker for the repository patch convention.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).warning(
        "clear_legacy_tds_values is one-way; restore cleared values from the pre-migration database backup."
    )
