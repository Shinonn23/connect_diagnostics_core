# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_stock_count_warehouse_field — one-way.

The forward patch inserted Stock Count Warehouse rows from the old single
warehouse Link. Once a Stock Count has more than one selected warehouse (added
manually after migration), collapsing the child table back to a single Link
value is an arbitrary choice, not a safe reversal. No reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_migrate_stock_count_warehouse_field: no-op; Stock Count Warehouse rows "
        "may already include manually-added warehouses that cannot be safely collapsed back."
    )
