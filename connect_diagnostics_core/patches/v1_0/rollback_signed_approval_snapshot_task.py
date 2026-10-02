# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Safely remove the shared signed-approval transition task."""

from __future__ import annotations

import frappe
from frappe import _

NAME = "Connect Signed Approval Snapshot"
EXPECTED = [("Capture Print Action: Authorized", 1, 0)]


def execute() -> None:
    if not frappe.db.exists("Workflow Transition Tasks", NAME):
        return
    refs = frappe.get_all("Workflow", fields=["name"])
    for workflow in refs:
        doc = frappe.get_doc("Workflow", workflow.name)
        if any(row.transition_tasks == NAME for row in doc.transitions):
            frappe.throw(_("Cannot remove {0} while an active Workflow references it.").format(NAME))
    doc = frappe.get_doc("Workflow Transition Tasks", NAME)
    actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
    if actual != EXPECTED:
        frappe.throw(
            _("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(NAME)
        )
    frappe.delete_doc("Workflow Transition Tasks", NAME, ignore_permissions=True)
