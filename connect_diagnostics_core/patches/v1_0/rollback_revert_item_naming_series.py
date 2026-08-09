# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for revert_item_naming_series — one-way.

The forward patch removed the Item naming-by-series property setters and the supplier-abbr
machinery, switching Stock Settings back to manual Item Code. Existing Item names were left
untouched. Reinstating the retired naming machinery is out of scope. No automatic reversal
is performed; re-enable naming-by-series manually if ever required."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_revert_item_naming_series: no-op; naming-by-series machinery is not automatically reinstated."
    )
