# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_storage_location_doctype — one-way.

The forward patch deleted the Storage Location DocType after its rows were
migrated into Warehouse. The DocType and its records are gone; migrated
locations live on as Warehouse records. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_remove_storage_location_doctype: no-op; deleted DocType and rows "
        "are not recoverable (migrated to Warehouse)."
    )
