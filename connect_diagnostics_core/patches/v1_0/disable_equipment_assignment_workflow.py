# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Disable the retired Equipment Assignment route without rewriting history."""

from __future__ import annotations

import frappe

WORKFLOW_NAME = "Connect Equipment Assignment Blueprint"


def execute() -> None:
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0, update_modified=False)
    frappe.db.commit()
