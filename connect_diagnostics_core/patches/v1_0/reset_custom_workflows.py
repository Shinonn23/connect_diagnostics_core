"""Delete every Workflow this app used to own.

Phase 3 of the custom-workflow reset. The app no longer provisions any Workflow
(see the Phase 2 change), so the Workflow, Workflow State, and Workflow Action
Master records it created on existing sites are removed here by exact name.

Deterministic and idempotent: each record is deleted only when present. Deleting
a Workflow cascades its child ``states``/``transitions`` rows. The shared
Workflow State and Workflow Action Master masters are removed only when no
surviving Workflow still references them, so a standard or user-created Workflow
that reuses a generic name (for example "Approve") is never disturbed.
"""

import frappe

WORKFLOW_NAMES = (
    "Payment Request Approval",
    "Supplier Onboarding",
    "Supplier Bank Change Approval",
    "Material Request Approval",
    "Purchase Order Approval",
    "Purchase Receipt Inspection",
    "Purchase Invoice Verification",
    "Customer Credit Request Approval",
    "Salary Slip Review",
    "Stock Count Approval",
    "Medical Device Product Registration Approval",
)

WORKFLOW_STATE_NAMES = (
    # Payment Request
    "Payment Request Draft",
    "Payment Request Submitted",
    "Pending Payment Request AP Review",
    "Pending Executive Payment Request Approval",
    "Payment Request Approved",
    "Payment Request Rejected",
    "Payment Request Cancelled",
    # Supplier onboarding / bank change
    "Supplier Draft",
    "Pending Supplier Verification",
    "Pending Supplier Activation",
    "Supplier Active",
    "Supplier Active (Legacy)",
    "Supplier Bank Change Draft",
    "Pending Supplier Bank Verification",
    "Pending Supplier Bank Approval",
    "Supplier Bank Verified",
    "Supplier Bank Change Rejected",
    # Procure to pay
    "Material Request Draft",
    "Pending Material Request Approval",
    "Material Request Approved",
    "Material Request Rejected",
    "Purchase Order Draft",
    "Pending Purchase Order Finance Review",
    "Pending Purchase Order Exception Approval",
    "Purchase Order Approved",
    "Purchase Order Rejected",
    "Purchase Receipt Draft",
    "Pending Goods Inspection",
    "Purchase Receipt Accepted",
    "Purchase Invoice Draft",
    "Pending Purchase Invoice Verification",
    "Pending Purchase Invoice Exception Approval",
    "Purchase Invoice Verified",
    "Purchase Invoice Rejected",
    # Customer credit request
    "Customer Credit Request Draft",
    "Pending Customer Credit Approval",
    "Customer Credit Request Approved",
    "Customer Credit Request Rejected",
    # Salary slip review
    "Salary Slip Draft",
    "Salary Slip Reviewed",
    "Salary Slip Submitted",
    "Salary Slip Cancelled",
    # Stock count
    "Stock Count Draft",
    "Pending Stock Manager Approval",
    "Pending Accounts Approval",
    "Stock Count Approved",
    "Stock Count Rejected",
    "Stock Count Cancelled",
    # Regulatory product registration
    "Registration Draft",
    "Registration Data Verification",
    "Registration Active",
    "Registration Superseded",
    "Registration Cancelled",
)

WORKFLOW_ACTION_NAMES = (
    # Payment Request
    "Request Payment Approval",
    "Complete Payment Request AP Review",
    "Approve Payment Request",
    "Reject Payment Request",
    "Revise Payment Request",
    "Submit Payment Request",
    # Supplier onboarding / bank change
    "Request supplier verification",
    "Verify supplier",
    "Activate supplier",
    "Return supplier",
    "Request bank verification",
    "Verify bank details",
    "Approve bank change",
    "Return bank change",
    "Reject bank change",
    # Procure to pay
    "Request approval",
    "Approve material request",
    "Reject material request",
    "Revise material request",
    "Request finance review",
    "Request exception approval",
    "Approve purchase order",
    "Approve purchase order exception",
    "Reject purchase order",
    "Revise purchase order",
    "Request goods inspection",
    "Accept goods",
    "Return receipt",
    "Request AP verification",
    "Request invoice exception approval",
    "Verify purchase invoice",
    "Approve purchase invoice exception",
    "Reject purchase invoice",
    "Revise purchase invoice",
    # Customer credit request
    "Request credit approval",
    "Approve credit request",
    "Reject credit request",
    # Salary slip review
    "Mark salary slip reviewed",
    "Return salary slip for correction",
    # Stock count
    "Submit for Approval",
    "Approve",
    "Reject",
    "Reopen",
    # Regulatory product registration
    "Submit for verification",
    "Activate registration",
    "Supersede registration",
    "Cancel registration",
)


def execute():
    for workflow_name in WORKFLOW_NAMES:
        if not frappe.db.exists("Workflow", workflow_name):
            continue
        # Deactivate first so the delete is never blocked by an active workflow.
        frappe.db.set_value("Workflow", workflow_name, "is_active", 0)
        frappe.delete_doc("Workflow", workflow_name, force=True, ignore_permissions=True)

    for state_name in WORKFLOW_STATE_NAMES:
        if frappe.db.exists("Workflow State", state_name) and not _state_in_use(state_name):
            frappe.delete_doc("Workflow State", state_name, force=True, ignore_permissions=True)

    for action_name in WORKFLOW_ACTION_NAMES:
        if frappe.db.exists("Workflow Action Master", action_name) and not _action_in_use(action_name):
            frappe.delete_doc("Workflow Action Master", action_name, force=True, ignore_permissions=True)

    remaining = [name for name in WORKFLOW_NAMES if frappe.db.exists("Workflow", name)]
    if remaining:
        frappe.throw(f"Failed to remove app-owned Workflows: {', '.join(remaining)}")

    frappe.db.commit()


def _state_in_use(state_name: str) -> bool:
    """Whether any surviving Workflow still references this state master."""
    return bool(
        frappe.db.exists("Workflow Document State", {"state": state_name})
        or frappe.db.exists("Workflow Transition", {"state": state_name})
        or frappe.db.exists("Workflow Transition", {"next_state": state_name})
    )


def _action_in_use(action_name: str) -> bool:
    """Whether any surviving Workflow transition still references this action master."""
    return bool(frappe.db.exists("Workflow Transition", {"action": action_name}))
