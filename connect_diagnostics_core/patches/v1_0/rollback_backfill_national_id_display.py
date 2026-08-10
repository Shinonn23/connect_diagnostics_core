# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Undo :mod:`backfill_national_id_display`.

Clears ``national_id_display`` back to blank for every Employee. Safe: the field is
fully recomputed from ``national_id`` by ``normalize_national_id`` on the next save,
so nothing is lost. Idempotent: a second run with nothing left to clear is a no-op.
"""

from __future__ import annotations

import frappe

EMPLOYEE = "Employee"


def execute() -> None:
    if not frappe.db.has_column(EMPLOYEE, "national_id_display"):
        return

    frappe.db.sql(
        """
        UPDATE `tabEmployee`
        SET national_id_display = ''
        WHERE COALESCE(national_id_display, '') != ''
        """
    )
