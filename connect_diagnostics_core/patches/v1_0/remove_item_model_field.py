# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the ``model`` Custom Field from Item.

Model numbers move to ERPNext's standard ``Item Manufacturer`` (which drives the core
``default_manufacturer_part_no`` / ``default_item_manufacturer`` fields) via a separate
data import; the free-text values in ``model`` are not migrated by this patch. Idempotent.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old


def execute() -> None:
    _drop_old("Item", "model")
    frappe.db.commit()
