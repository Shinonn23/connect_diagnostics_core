# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, see license.txt

"""Restore the retired Revise action masters for source rollback."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.remove_legacy_workflow_revise_actions import (
    WORKFLOW_ACTION_NAMES,
)


def execute() -> None:
    for action_name in WORKFLOW_ACTION_NAMES:
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc(
                {
                    "doctype": "Workflow Action Master",
                    "workflow_action_name": action_name,
                }
            ).insert(ignore_permissions=True)

    frappe.db.commit()
