# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the shared synchronous task for protected approval snapshots."""

from __future__ import annotations

import frappe
from frappe import _

NAME = "Connect Signed Approval Snapshot"
EXPECTED = [("Capture Print Action: Authorized", 1, 0)]


def execute() -> None:
    if frappe.db.exists("Workflow Transition Tasks", NAME):
        doc = frappe.get_doc("Workflow Transition Tasks", NAME)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != EXPECTED:
            frappe.throw(_("Workflow Transition Tasks {0} conflicts with the approved configuration.").format(NAME))
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Transition Tasks",
            "name": NAME,
            "tasks": [{"task": EXPECTED[0][0], "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def rollback() -> None:
    return
