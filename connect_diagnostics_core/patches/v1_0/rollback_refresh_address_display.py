# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for refresh_address_display — one-way (idempotent recompute).

The forward patch recomputes Address display snapshots from the current Address Template.
The snapshots are derived data with no prior version to restore; re-run the forward patch to
recompute. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_refresh_address_display: no-op; address display is derived (re-run the forward patch to recompute)."
    )
