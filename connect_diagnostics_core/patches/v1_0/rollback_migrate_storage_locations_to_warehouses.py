# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_storage_locations_to_warehouses — one-way.

The forward patch created Warehouse records from Storage Location rows. Once
created, a Warehouse can be referenced by stock transactions or by other
Warehouses as a parent, so deleting it back out is not safe to automate. No
reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_migrate_storage_locations_to_warehouses: no-op; created Warehouse "
        "records may already be referenced elsewhere and are not safe to delete automatically."
    )
