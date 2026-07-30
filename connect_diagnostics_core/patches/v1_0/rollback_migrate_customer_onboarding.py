# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback helper for the CD-only Customer onboarding workflows.

Run manually before reverting the matching source revision. The helper disables
the managed workflows and removes their open actions without deleting Customer
or Customer Credit Request history.
"""

from __future__ import annotations

from typing import cast

import frappe

_WORKFLOW_NAMES = (
    "Customer Onboarding",
    "Customer Credit Request Approval",
)
_WORKFLOW_ACTION_DOCTYPES = (
    "Customer",
    "Customer Credit Request",
)


def execute() -> None:
    _deactivate_workflows()
    _remove_open_workflow_actions()
    frappe.clear_cache(doctype="Customer")
    frappe.clear_cache(doctype="Customer Credit Request")


def _deactivate_workflows() -> None:
    frappe.db.set_value(
        "Workflow",
        {"name": ["in", _WORKFLOW_NAMES]},
        "is_active",
        0,
        update_modified=False,
    )


def _remove_open_workflow_actions() -> None:
    action_names = cast(
        list[str],
        frappe.get_all(
            "Workflow Action",
            filters={
                "reference_doctype": ["in", _WORKFLOW_ACTION_DOCTYPES],
                "status": "Open",
            },
            pluck="name",
            order_by="name asc",
        ),
    )
    for action_name in action_names:
        frappe.delete_doc("Workflow Action", action_name, force=True, ignore_permissions=True)
