# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reviewed route declarations consumed by document-specific approval adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalRoute:
    """One approved native Workflow route and its actor contract."""

    key: str
    doctype: str
    scope_key: str
    maker_roles: tuple[str, ...]
    reviewer_roles: tuple[str, ...]
    final_approver_roles: tuple[str, ...]
    execution_roles: tuple[str, ...]
    send_action: str
    resubmit_action: str
    review_action: str
    return_action: str
    approve_action: str
    reject_action: str
    execute_action: str
    draft_state: str
    pending_review_state: str
    reviewed_state: str
    returned_state: str
    approved_state: str
    submitted_state: str
    excluded_scope: tuple[str, ...] = ()
    requires_distinct_actors: bool = True

    @property
    def protected_actions(self) -> tuple[str, str]:
        """Return the actions that require a distinct signed business actor."""
        return (self.review_action, self.approve_action)


APPROVAL_ROUTES: tuple[ApprovalRoute, ...] = (
    ApprovalRoute(
        key="stock_entry_material_transfer",
        doctype="Stock Entry",
        scope_key="direct_material_transfer",
        maker_roles=("Stock User",),
        reviewer_roles=("Stock Manager",),
        final_approver_roles=("C-Level Approver",),
        execution_roles=("Stock Manager",),
        send_action="Send Stock Transfer for Review",
        resubmit_action="Resubmit Stock Transfer for Review",
        review_action="Review Stock Transfer",
        return_action="Return Stock Transfer",
        approve_action="Approve Stock Transfer",
        reject_action="Reject Stock Transfer",
        execute_action="Submit Stock Transfer",
        draft_state="Stock Transfer Draft",
        pending_review_state="Stock Transfer Pending Review",
        reviewed_state="Stock Transfer Reviewed",
        returned_state="Stock Transfer Returned",
        approved_state="Stock Transfer Approved",
        submitted_state="Stock Transfer Submitted",
        excluded_scope=("transit legs", "non-Material-Transfer Stock Entry"),
    ),
    ApprovalRoute(
        key="stock_reconciliation",
        doctype="Stock Reconciliation",
        scope_key="stock_reconciliation",
        maker_roles=("Stock User",),
        reviewer_roles=("Stock Manager",),
        final_approver_roles=("Accounts Manager",),
        execution_roles=("Stock Manager",),
        send_action="Send Stock Reconciliation for Review",
        resubmit_action="Resubmit Stock Reconciliation for Review",
        review_action="Review Stock Reconciliation",
        return_action="Return Stock Reconciliation",
        approve_action="Approve Stock Reconciliation",
        reject_action="Reject Stock Reconciliation",
        execute_action="Post Stock Reconciliation",
        draft_state="Stock Reconciliation Draft",
        pending_review_state="Stock Reconciliation Pending Review",
        reviewed_state="Stock Reconciliation Reviewed",
        returned_state="Stock Reconciliation Returned",
        approved_state="Stock Reconciliation Approved",
        submitted_state="Stock Reconciliation Submitted",
    ),
    ApprovalRoute(
        key="asset_movement",
        doctype="Asset Movement",
        scope_key="asset_movement",
        maker_roles=("Stock User",),
        reviewer_roles=("Stock Manager",),
        final_approver_roles=("C-Level Approver",),
        execution_roles=("Stock Manager",),
        send_action="Send Asset Movement for Review",
        resubmit_action="Resubmit Asset Movement for Review",
        review_action="Review Asset Movement",
        return_action="Return Asset Movement",
        approve_action="Approve Asset Movement",
        reject_action="Reject Asset Movement",
        execute_action="Submit Asset Movement",
        draft_state="Asset Movement Draft",
        pending_review_state="Asset Movement Pending Review",
        reviewed_state="Asset Movement Reviewed",
        returned_state="Asset Movement Returned",
        approved_state="Asset Movement Approved",
        submitted_state="Asset Movement Submitted",
        excluded_scope=("Equipment Assignment", "Equipment Installation"),
    ),
    ApprovalRoute(
        key="manual_journal_entry",
        doctype="Journal Entry",
        scope_key="manual_journal_entry",
        maker_roles=("Accounts User",),
        reviewer_roles=("Accounts Manager",),
        final_approver_roles=("C-Level Approver",),
        execution_roles=("Accounts Manager",),
        send_action="Send Journal Entry for Review",
        resubmit_action="Resubmit Journal Entry for Review",
        review_action="Review Journal Entry",
        return_action="Return Journal Entry",
        approve_action="Approve Journal Entry",
        reject_action="Reject Journal Entry",
        execute_action="Post Journal Entry",
        draft_state="Journal Entry Draft",
        pending_review_state="Journal Entry Pending Review",
        reviewed_state="Journal Entry Reviewed",
        returned_state="Journal Entry Returned",
        approved_state="Journal Entry Approved",
        submitted_state="Journal Entry Submitted",
        excluded_scope=("ERPNext-generated Journal Entry", "HRMS-generated Journal Entry"),
    ),
    ApprovalRoute(
        key="sales_order_credit",
        doctype="Sales Order",
        scope_key="credit_approval",
        maker_roles=("Sales User",),
        reviewer_roles=("Sales Manager",),
        final_approver_roles=("Accounts Manager",),
        execution_roles=("Sales Manager",),
        send_action="Send Sales Order for Review",
        resubmit_action="Resubmit Sales Order for Review",
        review_action="Review Sales Order",
        return_action="Return Sales Order",
        approve_action="Approve Sales Order Credit",
        reject_action="Reject Sales Order Credit",
        execute_action="Submit Sales Order",
        draft_state="Sales Order Draft",
        pending_review_state="Sales Order Pending Review",
        reviewed_state="Sales Order Reviewed",
        returned_state="Sales Order Returned",
        approved_state="Sales Order Approved",
        submitted_state="Sales Order Submitted",
        excluded_scope=("Sales Order without credit approval",),
    ),
    ApprovalRoute(
        key="sales_invoice_credit_note",
        doctype="Sales Invoice",
        scope_key="credit_note",
        maker_roles=("Sales User", "Accounts User"),
        reviewer_roles=("Sales Manager",),
        final_approver_roles=("Accounts Manager",),
        execution_roles=("Accounts Manager",),
        send_action="Send Sales Invoice Credit for Review",
        resubmit_action="Resubmit Sales Invoice Credit for Review",
        review_action="Review Sales Invoice Credit",
        return_action="Return Sales Invoice Credit",
        approve_action="Approve Sales Invoice Credit",
        reject_action="Reject Sales Invoice Credit",
        execute_action="Post Sales Invoice Credit",
        draft_state="Sales Invoice Credit Draft",
        pending_review_state="Sales Invoice Credit Pending Review",
        reviewed_state="Sales Invoice Credit Reviewed",
        returned_state="Sales Invoice Credit Returned",
        approved_state="Sales Invoice Credit Approved",
        submitted_state="Sales Invoice Credit Submitted",
        excluded_scope=("ordinary Sales Invoice",),
    ),
    ApprovalRoute(
        key="purchase_order",
        doctype="Purchase Order",
        scope_key="purchase_order",
        maker_roles=("Purchase User",),
        reviewer_roles=("Purchase Manager",),
        final_approver_roles=("C-Level Approver",),
        execution_roles=("Purchase Manager",),
        send_action="Send Purchase Order for Review",
        resubmit_action="Resubmit Purchase Order for Review",
        review_action="Review Purchase Order",
        return_action="Return Purchase Order",
        approve_action="Approve Purchase Order",
        reject_action="Reject Purchase Order",
        execute_action="Submit Purchase Order",
        draft_state="Purchase Order Draft",
        pending_review_state="Purchase Order Pending Review",
        reviewed_state="Purchase Order Reviewed",
        returned_state="Purchase Order Returned",
        approved_state="Purchase Order Approved",
        submitted_state="Purchase Order Submitted",
    ),
    ApprovalRoute(
        key="purchase_invoice",
        doctype="Purchase Invoice",
        scope_key="purchase_invoice",
        maker_roles=("Accounts User",),
        reviewer_roles=("Purchase Manager",),
        final_approver_roles=("Accounts Manager",),
        execution_roles=("Accounts Manager",),
        send_action="Send Purchase Invoice for Review",
        resubmit_action="Resubmit Purchase Invoice for Review",
        review_action="Review Purchase Invoice",
        return_action="Return Purchase Invoice",
        approve_action="Approve Purchase Invoice",
        reject_action="Reject Purchase Invoice",
        execute_action="Post Purchase Invoice",
        draft_state="Purchase Invoice Draft",
        pending_review_state="Purchase Invoice Pending Review",
        reviewed_state="Purchase Invoice Reviewed",
        returned_state="Purchase Invoice Returned",
        approved_state="Purchase Invoice Approved",
        submitted_state="Purchase Invoice Submitted",
    ),
    ApprovalRoute(
        key="payment_entry",
        doctype="Payment Entry",
        scope_key="payment_entry",
        maker_roles=("Accounts User",),
        reviewer_roles=("Accounts Manager",),
        final_approver_roles=("C-Level Approver",),
        execution_roles=("Accounts Manager",),
        send_action="Send Payment Entry for Review",
        resubmit_action="Resubmit Payment Entry for Review",
        review_action="Review Payment Entry",
        return_action="Return Payment Entry",
        approve_action="Approve Payment Entry",
        reject_action="Reject Payment Entry",
        execute_action="Post Payment Entry",
        draft_state="Payment Entry Draft",
        pending_review_state="Payment Entry Pending Review",
        reviewed_state="Payment Entry Reviewed",
        returned_state="Payment Entry Returned",
        approved_state="Payment Entry Approved",
        submitted_state="Payment Entry Submitted",
    ),
    ApprovalRoute(
        key="payroll_entry",
        doctype="Payroll Entry",
        scope_key="payroll_entry",
        maker_roles=("HR User",),
        reviewer_roles=("HR Manager",),
        final_approver_roles=("Accounts Manager",),
        execution_roles=("HR Manager",),
        send_action="Send Payroll Entry for Review",
        resubmit_action="Resubmit Payroll Entry for Review",
        review_action="Review Payroll Entry",
        return_action="Return Payroll Entry",
        approve_action="Approve Payroll Entry",
        reject_action="Reject Payroll Entry",
        execute_action="Submit Payroll Entry",
        draft_state="Payroll Entry Draft",
        pending_review_state="Payroll Entry Pending Review",
        reviewed_state="Payroll Entry Reviewed",
        returned_state="Payroll Entry Returned",
        approved_state="Payroll Entry Approved",
        submitted_state="Payroll Entry Submitted",
        excluded_scope=("Salary Slip direct submit",),
    ),
)

ROUTES_BY_KEY = {route.key: route for route in APPROVAL_ROUTES}


def get_route(key: str) -> ApprovalRoute:
    """Return a declared route or fail clearly for an adapter typo."""
    try:
        return ROUTES_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown approval route: {key}") from exc
