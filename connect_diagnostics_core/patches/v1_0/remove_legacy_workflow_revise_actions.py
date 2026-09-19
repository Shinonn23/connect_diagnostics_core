# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the retired Revise actions from existing sites.

The approval workflows now terminate at Rejected. Fixture sync removes the
transitions, but it does not delete Workflow Action Master rows omitted from a
fixture, so remove only the three app-owned action masters here.
"""

from __future__ import annotations

import frappe

WORKFLOW_ACTION_NAMES = (
    "Revise Stock Transfer",
    "Revise Asset Movement",
    "Revise Payment Entry",
)


def execute() -> None:
    for action_name in WORKFLOW_ACTION_NAMES:
        frappe.db.delete("Workflow Action Master", {"name": action_name})

    frappe.db.commit()
