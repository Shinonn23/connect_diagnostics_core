# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

MANAGED_DOCUMENT_TYPES = (
    "Payment Request",
    "Supplier",
    "Supplier Bank Change Request",
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Customer Credit Request",
)

WORKFLOW_STATE_FIELDS = {
    "Payment Request": ("payment_approval_state", "Payment Request Draft"),
    "Supplier": ("supplier_onboarding_state", "Supplier Draft"),
    "Supplier Bank Change Request": ("bank_change_request_state", "Supplier Bank Change Draft"),
    "Material Request": ("p2p_workflow_state", "Material Request Draft"),
    "Purchase Order": ("p2p_workflow_state", "Purchase Order Draft"),
    "Purchase Receipt": ("p2p_workflow_state", "Purchase Receipt Draft"),
    "Purchase Invoice": ("p2p_workflow_state", "Purchase Invoice Draft"),
    "Customer Credit Request": ("credit_request_state", "Customer Credit Request Draft"),
}

PENDING_STATES = {
    "Payment Request": ("Pending Payment Request AP Review", "Pending Executive Payment Request Approval"),
    "Supplier": ("Pending Supplier Verification", "Pending Supplier Activation"),
    "Supplier Bank Change Request": ("Pending Supplier Bank Verification", "Pending Supplier Bank Approval"),
    "Material Request": ("Pending Material Request Approval",),
    "Purchase Order": ("Pending Purchase Order Finance Review", "Pending Purchase Order Exception Approval"),
    "Purchase Receipt": ("Pending Goods Inspection",),
    "Purchase Invoice": (
        "Pending Purchase Invoice Verification",
        "Pending Purchase Invoice Exception Approval",
    ),
    "Customer Credit Request": ("Pending Customer Credit Approval",),
}


def execute() -> None:
    """Normalize inactive-workflow drafts without destroying approval history."""
    for document_type in MANAGED_DOCUMENT_TYPES:
        active_workflow = frappe.db.get_value(
            "Workflow",
            {"document_type": document_type, "is_active": 1},
            "name",
        )
        if active_workflow:
            continue
        inactive_workflow = frappe.db.get_value(
            "Workflow",
            {"document_type": document_type, "is_active": 0},
            "name",
        )
        if not inactive_workflow:
            continue
        _normalize_pending_drafts(document_type)
        # Workflow Actions are intentionally retained as audit history.  The
        # runtime has no active Workflow to consume them, so they cannot resume
        # approval or block submission.  Retaining them also makes this patch
        # safely reversible.

    frappe.clear_cache()


def _normalize_pending_drafts(document_type: str) -> None:
    state_field, draft_state = WORKFLOW_STATE_FIELDS[document_type]
    pending_states = PENDING_STATES[document_type]
    frappe.db.set_value(
        document_type,
        {"docstatus": 0, state_field: ["in", pending_states]},
        state_field,
        draft_state,
        update_modified=False,
    )
