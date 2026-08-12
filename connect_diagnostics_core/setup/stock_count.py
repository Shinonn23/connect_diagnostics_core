# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Idempotent Stock Count approval workflow.

Monthly cycle counts never touch valuation (they only relocate mismatched stock
into a holding warehouse), so they only need Stock Manager approval. Yearly
counts post a quantity/valuation correction to the General Ledger, so they route
through an extra Accounts Manager approval step first. The same
"Pending Stock Manager Approval" -> "Approve" action branches to either the
final state or the accounts step, based on `count_type`, via two transition
rows whose `condition` is mutually exclusive.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count.stock_count import (
    MONTHLY,
    YEARLY,
)
from connect_diagnostics_core.setup.customer_onboarding import ensure_workflow

DOCTYPE = "Stock Count"
WORKFLOW_NAME = "Stock Count Approval"
WORKFLOW_STATE_FIELD = "count_state"

DRAFT = "Stock Count Draft"
PENDING_STOCK_APPROVAL = "Pending Stock Manager Approval"
PENDING_ACCOUNTS_APPROVAL = "Pending Accounts Approval"
APPROVED = "Stock Count Approved"
REJECTED = "Stock Count Rejected"
CANCELLED = "Stock Count Cancelled"

WORKFLOW_STATE_STYLES = {
    DRAFT: "Info",
    PENDING_STOCK_APPROVAL: "Warning",
    PENDING_ACCOUNTS_APPROVAL: "Warning",
    APPROVED: "Success",
    REJECTED: "Danger",
    CANCELLED: "Danger",
}
WORKFLOW_ACTIONS = ("Submit for Approval", "Approve", "Reject", "Reopen")

WORKFLOW_STATES = (
    {"state": DRAFT, "doc_status": "0", "allow_edit": "Stock User"},
    {"state": PENDING_STOCK_APPROVAL, "doc_status": "0", "allow_edit": "Stock Manager"},
    {"state": PENDING_ACCOUNTS_APPROVAL, "doc_status": "0", "allow_edit": "Accounts Manager"},
    {"state": APPROVED, "doc_status": "1", "allow_edit": "Stock Manager"},
    {"state": REJECTED, "doc_status": "0", "allow_edit": "Stock Manager"},
    {"state": CANCELLED, "doc_status": "2", "allow_edit": "Stock Manager"},
)
WORKFLOW_TRANSITIONS = (
    {
        "state": DRAFT,
        "action": "Submit for Approval",
        "next_state": PENDING_STOCK_APPROVAL,
        "allowed": "Stock User",
    },
    {
        # Monthly: never touches accounting, so Stock Manager approval is final.
        "state": PENDING_STOCK_APPROVAL,
        "action": "Approve",
        "next_state": APPROVED,
        "allowed": "Stock Manager",
        "condition": f"doc.count_type != '{YEARLY}'",
    },
    {
        # Yearly: posts a GL-impacting correction, so it must also clear Accounts.
        "state": PENDING_STOCK_APPROVAL,
        "action": "Approve",
        "next_state": PENDING_ACCOUNTS_APPROVAL,
        "allowed": "Stock Manager",
        "condition": f"doc.count_type == '{YEARLY}'",
    },
    {
        "state": PENDING_ACCOUNTS_APPROVAL,
        "action": "Approve",
        "next_state": APPROVED,
        "allowed": "Accounts Manager",
    },
    {
        "state": PENDING_STOCK_APPROVAL,
        "action": "Reject",
        "next_state": REJECTED,
        "allowed": "Stock Manager",
    },
    {
        "state": PENDING_ACCOUNTS_APPROVAL,
        "action": "Reject",
        "next_state": REJECTED,
        "allowed": "Accounts Manager",
    },
    {
        "state": REJECTED,
        "action": "Reopen",
        "next_state": DRAFT,
        "allowed": "Stock User",
    },
)

# Re-exported so callers only need this module for the two count-type labels.
__all__ = ("MONTHLY", "YEARLY", "ensure_configuration")


def ensure_configuration() -> None:
    ensure_workflow_masters()
    ensure_workflow(
        workflow_name=WORKFLOW_NAME,
        document_type=DOCTYPE,
        workflow_state_field=WORKFLOW_STATE_FIELD,
        states=WORKFLOW_STATES,
        transitions=WORKFLOW_TRANSITIONS,
        send_email_alert=0,
        is_active=1,
    )


def ensure_workflow_masters() -> None:
    for state_name, style in WORKFLOW_STATE_STYLES.items():
        if frappe.db.exists("Workflow State", state_name):
            state = frappe.get_doc("Workflow State", state_name)
            if state.get("style") != style:
                state.set("style", style)
                state.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {"doctype": "Workflow State", "workflow_state_name": state_name, "style": style}
        ).insert(ignore_permissions=True)

    for action_name in WORKFLOW_ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action_name}).insert(
                ignore_permissions=True
            )
