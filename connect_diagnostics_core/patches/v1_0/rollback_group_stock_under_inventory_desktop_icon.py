# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for the Inventory Desk folder — run this before reverting the feature.

There is no forward patch: `setup.workspace.ensure_desktop_icons` reconciles the
ERPNext-owned Stock Desktop Icon on every `after_install` / `after_migrate`, the same
way the rest of `setup/workspace.py` maintains navigation.

A plain revert is not self-healing, which is why this utility exists. Once
`desktop_icon/inventory.json` is gone, `frappe.model.sync.remove_orphan_entities`
deletes the Inventory icon, but ERPNext's unchanged `desktop_icon/stock.json` is not
re-imported, so `Desktop Icon "Stock"` keeps `parent_icon = "Inventory"`.
`frappe.desk.doctype.desktop_icon.desktop_icon.get_desktop_icons` drops any icon whose
parent is not a permitted top-level icon, so Stock would vanish from the Desk home.

Deleting the folder first and then re-running `ensure_desktop_icons` lets its existing
fallback put Stock back under the ERPNext icon.

Not registered in patches.txt (manual rollback utility only), matching the existing
rollback_remove_financial_reports_th.py convention."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.setup.workspace import (
    INVENTORY_DESKTOP_ICON,
    STOCK_COUNT_WORKSPACE,
    ensure_desktop_icons,
)


def execute() -> None:
    logger = frappe.logger(__name__)
    for label in (STOCK_COUNT_WORKSPACE, INVENTORY_DESKTOP_ICON):
        if frappe.db.exists("Desktop Icon", label):
            frappe.delete_doc("Desktop Icon", label, force=True, ignore_permissions=True)
            logger.info(f"rollback_group_stock_under_inventory_desktop_icon: deleted Desktop Icon {label}.")
    ensure_desktop_icons()
