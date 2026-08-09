# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for drop_custom_item_name_th_column — one-way.

The forward patch dropped the orphan custom_item_name_th column from tabItem after its
values were migrated into Item Alternative Name (label Thai). The raw column data is gone;
recover the Thai names from Item Alternative Name instead. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_drop_custom_item_name_th_column: no-op; dropped column data lives in Item Alternative Name (label 'Thai')."
    )
