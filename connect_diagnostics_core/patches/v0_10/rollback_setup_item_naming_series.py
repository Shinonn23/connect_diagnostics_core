# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for setup_item_naming_series — one-way (idempotent seed).

The forward patch only seeds Customer/Supplier Series counters to match existing data so
auto-numbering continues correctly. Lowering a live counter would risk duplicate names, so
there is no safe reversal. Re-run the forward patch instead if counters drift."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_setup_item_naming_series: no-op; series counters must not be lowered (re-run the forward patch to reseed)."
    )
