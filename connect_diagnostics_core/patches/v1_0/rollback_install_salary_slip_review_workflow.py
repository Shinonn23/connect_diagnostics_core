# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Deactivate the managed Salary Slip workflow without altering Salary Slips."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from connect_diagnostics_core.setup.payroll import SALARY_SLIP_REVIEW_WORKFLOW


def execute() -> None:
    if not frappe.db.exists("Workflow", SALARY_SLIP_REVIEW_WORKFLOW):
        return
    workflow = frappe.get_doc("Workflow", SALARY_SLIP_REVIEW_WORKFLOW)
    if not isinstance(workflow, Document) or not workflow.get("is_active"):
        return
    workflow.set("is_active", 0)
    workflow.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Salary Slip")
