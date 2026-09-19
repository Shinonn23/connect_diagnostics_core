# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Converge the DEV Stock Entry workflows to the single native route."""

from __future__ import annotations

import frappe

CANONICAL_WORKFLOW = "Connect Stock Transfer Approval"
LEGACY_WORKFLOW = "Connect Emergency Stock Movement Blueprint"


def execute() -> None:
    """Activate the canonical workflow and retire only the known collision."""
    if frappe.db.exists("Workflow", CANONICAL_WORKFLOW):
        frappe.db.set_value("Workflow", CANONICAL_WORKFLOW, "is_active", 1, update_modified=False)
    if frappe.db.exists("Workflow", LEGACY_WORKFLOW):
        frappe.db.set_value("Workflow", LEGACY_WORKFLOW, "is_active", 0, update_modified=False)
    frappe.db.commit()


def rollback() -> None:
    """Restore the collision only while the expected consolidated state is intact."""
    if not (
        frappe.db.exists("Workflow", CANONICAL_WORKFLOW) and frappe.db.exists("Workflow", LEGACY_WORKFLOW)
    ):
        return

    canonical_active = frappe.db.get_value("Workflow", CANONICAL_WORKFLOW, "is_active")
    legacy_active = frappe.db.get_value("Workflow", LEGACY_WORKFLOW, "is_active")
    if canonical_active == 1 and legacy_active == 0:
        frappe.db.set_value("Workflow", CANONICAL_WORKFLOW, "is_active", 0, update_modified=False)
        frappe.db.set_value("Workflow", LEGACY_WORKFLOW, "is_active", 1, update_modified=False)
        frappe.db.commit()
