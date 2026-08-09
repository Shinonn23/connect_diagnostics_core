# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for set_app_logo — clear the forced navbar logo.

set_app_logo wrote the Connect Diagnostics logo into ``Navbar Settings.app_logo``.
Clearing it returns logo resolution to the ``app_logo_url`` hook / Frappe default.
The prior value is not restored because the patch overwrote it unconditionally.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.db.set_single_value("Navbar Settings", "app_logo", None)
    frappe.clear_cache()
