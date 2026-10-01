# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe


class AssetValueAdjustmentWorkflowMixin:
    """Create the native revaluation JE as a pending draft only."""

    def on_submit(self: Any) -> None:
        from connect_diagnostics_core.api.erpnext.journal_entry_generators import (
            _find_existing_draft,
        )

        existing = _find_existing_draft("Asset Value Adjustment", self.name)
        if existing:
            self.db_set("journal_entry", existing.name)
            return
        frappe.flags.journal_entry_draft_context = {
            "source_doctype": self.doctype,
            "source_name": self.name,
            "source_action": "asset_value_adjustment",
        }
        try:
            self.make_asset_revaluation_entry()
        finally:
            frappe.flags.pop("journal_entry_draft_context", None)

    def on_cancel(self: Any) -> None:
        if getattr(frappe.flags, "journal_entry_asset_value_adjustment_cancel", None) == self.name:
            from erpnext.assets.doctype.asset_activity.asset_activity import add_asset_activity

            self.update_asset()
            add_asset_activity(
                self.asset,
                frappe._("Asset's value adjustment cancelled with its Journal Entry Workflow."),
            )
            return
        return super().on_cancel()
