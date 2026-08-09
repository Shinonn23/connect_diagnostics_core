# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for strip_custom_prefix_from_field_names — one-way.

The forward patch created each stripped-name field, copied data across, then dropped the old
custom_-prefixed Custom Field and column. The data now lives under the stripped field names;
the old columns are gone. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_strip_custom_prefix_from_field_names: no-op; data lives under stripped field names, old columns dropped."
    )
