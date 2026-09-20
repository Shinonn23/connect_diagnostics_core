# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.payment_approval import (
    CUSTOM_FIELDS,
    PAYMENT_ENTRY_DOCTYPE,
    assign_payment_approvers,
    ensure_configuration,
)

LEGACY_PAYMENT_ENTRY_STATES = (
    "Payment Draft",
    "Payment Submitted",
    "Pending Low-Value Payment Approval",
    "Pending Primary Payment Approval",
    "Escalated Low-Value Payment Approval",
    "Escalated Payment Approval",
    "Payment Approved",
    "Payment Rejected",
    "Payment Cancelled",
)


def execute() -> None:
    _delete_legacy_workflow_actions()
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    ensure_configuration()
    assign_payment_approvers()
    frappe.clear_cache()


def _delete_legacy_workflow_actions() -> None:
    workflow_action_names = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": PAYMENT_ENTRY_DOCTYPE,
            "workflow_state": ["in", LEGACY_PAYMENT_ENTRY_STATES],
        },
        pluck="name",
    )
    for workflow_action_name in workflow_action_names:
        if frappe.db.exists("Workflow Action", workflow_action_name):
            frappe.delete_doc(
                "Workflow Action",
                workflow_action_name,
                force=True,
                ignore_permissions=True,
            )
