# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the native Workflow transition task used for exception execution provenance."""

from __future__ import annotations

import frappe

TASKS = {
    "Connect Emergency Stock Movement Approval": "Capture Freeze Exception Approval Scope",
    "Connect Emergency Stock Movement Execution": "Authorize Freeze Exception Execution",
}


def _ensure_task(name: str, task_name: str) -> None:
    expected = [(task_name, 1, 0)]
    if frappe.db.exists("Workflow Transition Tasks", name):
        doc = frappe.get_doc("Workflow Transition Tasks", name)
        actual = [(row.task, int(row.enabled), int(row.asynchronous)) for row in doc.tasks]
        if actual != expected:
            frappe.throw(
                f"Workflow Transition Tasks {name} conflicts with the approved native task configuration."
            )
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Transition Tasks",
            "name": name,
            "tasks": [{"task": task_name, "enabled": 1, "asynchronous": 0}],
        }
    ).insert(ignore_permissions=True)


def execute() -> None:
    for name, task_name in TASKS.items():
        _ensure_task(name, task_name)


def rollback() -> None:
    # Ownership cannot be inferred from a name after a previous migration run.
    # Leave both records intact rather than deleting a site-owned pre-existing record.
    return
