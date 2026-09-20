# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for retire_storage_location_inventory_dimension — one-way.

Recreating the exact same Inventory Dimension (and repositioning its
generated fields next to each warehouse field) required setup/storage_location.py,
which this change deletes. Restore that module from git history and call its
ensure_configuration() manually if the dimension must come back; no automatic
reversal is performed here."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_retire_storage_location_inventory_dimension: no-op; restore "
        "setup/storage_location.py from git history and re-run ensure_configuration() "
        "manually to recreate the dimension."
    )
