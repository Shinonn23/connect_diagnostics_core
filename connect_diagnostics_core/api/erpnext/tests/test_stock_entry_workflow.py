# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_entry_workflow


class TestStockEntryWorkflow(UnitTestCase):
    def test_direct_transfer_requires_approved_workflow_state(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
                "workflow_state": "Stock Transfer Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_before_submit(doc)

    def test_direct_transfer_can_submit_only_from_persisted_approved_state(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-APPROVED",
                "owner": "maker@example.com",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
                "workflow_state": "Stock Transfer Submitted",
                "items": [
                    {
                        "item_code": "ITEM-A",
                        "s_warehouse": "SOURCE",
                        "t_warehouse": "TARGET",
                        "qty": 1,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "conversion_factor": 1,
                    }
                ],
            }
        )
        digest = stock_entry_workflow.get_approval_digest(doc)
        doc.approval_critical_digest = digest
        persisted = {
            "workflow_state": "Stock Transfer Approved",
            "approval_critical_digest": digest,
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "reviewer-signature",
            "authorized_signature": "approver-signature",
        }
        with (
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "require_distinct_actors"),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=persisted) as get_value,
        ):
            stock_entry_workflow.validate_before_submit(doc)

        get_value.assert_called_once_with(
            "Stock Entry",
            "STE-APPROVED",
            [
                "workflow_state",
                "approval_critical_digest",
                "approval_reviewer_user",
                "approval_authorized_user",
                "checked_signature",
                "authorized_signature",
            ],
            as_dict=True,
            for_update=True,
        )

    def test_direct_submit_from_spoofed_persisted_state_is_denied(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-SPOOFED",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Submitted",
            }
        )
        with (
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(
                stock_entry_workflow.frappe.db,
                "get_value",
                return_value={"workflow_state": "Stock Transfer Draft"},
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_submit(doc)

    def test_mutation_after_review_invalidates_authorization(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "owner": "maker@example.com",
                "purpose": "Material Transfer",
                "items": [
                    {
                        "item_code": "ITEM-A",
                        "s_warehouse": "SOURCE",
                        "t_warehouse": "TARGET",
                        "qty": 1,
                    }
                ],
            }
        )
        with patch.dict(stock_entry_workflow.frappe.session, {"user": "reviewer@example.com"}):
            stock_entry_workflow.capture_review_snapshot(doc)
        doc.items[0].qty = 2

        with (
            patch.dict(stock_entry_workflow.frappe.session, {"user": "approver@example.com"}),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.capture_authorization_snapshot(doc)

    def test_return_clears_current_approval_evidence(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "approval_critical_digest": "digest",
                "approval_reviewer_user": "reviewer@example.com",
                "approval_authorized_user": "approver@example.com",
                "checked_signature": "reviewer-signature",
                "authorized_signature": "approver-signature",
            }
        )

        stock_entry_workflow.clear_approval_snapshots(doc)

        self.assertFalse(doc.approval_critical_digest)
        self.assertFalse(doc.approval_reviewer_user)
        self.assertFalse(doc.approval_authorized_user)
        self.assertFalse(doc.checked_signature)
        self.assertFalse(doc.authorized_signature)

    def test_exception_requires_native_completed_review(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-EXCEPTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Urgent controlled movement",
            }
        )
        with patch.object(stock_entry_workflow.frappe.db, "exists", return_value=False):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_completed_reject_evidence_is_not_posting_authorization(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-REJECTED-EXCEPTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Rejected history must not authorize posting",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_native_execution_task_is_required_after_approval_evidence(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NATIVE-EXECUTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Native execution task proof",
                "freeze_exception_reconciliation_scope": "[]",
            }
        )
        with patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True):
            with patch.object(stock_entry_workflow.frappe, "throw") as throw:
                stock_entry_workflow.authorize_freeze_exception_execution(doc)
            throw.assert_not_called()
            self.assertTrue(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_scope_rejects_new_freeze_before_execute(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NEW-FREEZE",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "New Freeze must not be bypassed",
                "freeze_exception_reconciliation_scope": "[]",
            }
        )
        current_freeze = [
            {
                "item_code": "ITEM-A",
                "reconciliation": "SR-B",
                "warehouse": "WH-1",
                "modified": "2026-09-18 10:00:00",
            }
        ]
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.object(
                stock_entry_workflow,
                "_has_native_execution_provenance",
                return_value=True,
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.get_active_freeze_scope",
                return_value=current_freeze,
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_stale_completed_history_cannot_authorize_after_resubmit(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-STALE-RESUBMIT",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Old approval must not be reused",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_prior_history_and_spoofed_state_do_not_authorize_changed_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-SPOOFED-ROUTE",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Transit must not use direct exception",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(
                stock_entry_workflow.frappe.flags,
                {"freeze_exception_execution": {"doctype": doc.doctype, "name": doc.name}},
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_requires_reason_and_direct_route(self) -> None:
        missing_reason = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Stock Transfer Draft",
                "freeze_exception": 1,
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_workflow(missing_reason)
        throw.assert_called_once()

        transit = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "workflow_state": "Stock Transfer Draft",
                "freeze_exception": 1,
                "freeze_exception_reason": "Urgent controlled movement",
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_workflow(transit)
        throw.assert_called_once()

    def test_transit_outbound_and_receipt_are_not_direct_route(self) -> None:
        outbound = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
            }
        )
        receipt = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": "STE-OUT",
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(outbound))
        self.assertFalse(stock_entry_workflow.is_direct_transfer(receipt))

    def test_other_stock_entry_purposes_are_not_direct_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Issue",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(doc))

    def test_non_transfer_submit_guard_is_a_noop(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Issue",
                "workflow_state": "Stock Entry Submitted",
            }
        )

        with patch.object(stock_entry_workflow.frappe.db, "get_value") as get_value:
            stock_entry_workflow.validate_before_submit(doc)

        get_value.assert_not_called()

    def test_direct_transfer_cancel_requires_workflow_transition(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-CANCEL",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Entry Cancelled",
            }
        )
        with (
            patch.object(
                stock_entry_workflow.frappe.db,
                "get_value",
                return_value="Stock Transfer Submitted",
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_cancel(doc)

        doc.workflow_state = "Stock Transfer Cancelled"
        with patch.object(
            stock_entry_workflow.frappe.db,
            "get_value",
            return_value="Stock Transfer Submitted",
        ):
            stock_entry_workflow.validate_before_cancel(doc)
