# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Restore the previous Equipment Assignment active flag for source rollback."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.disable_equipment_assignment_workflow import WORKFLOW_NAME


def execute() -> None:
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 1, update_modified=False)
    frappe.db.commit()
