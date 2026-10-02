# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Signed Stock Reconciliation approval and raw-write boundary tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_reconciliation_workflow as workflow
from connect_diagnostics_core.api.frappe.approval_controls import SignedApprovalSnapshot


def _doc(state: str, *, qty: int = 4) -> Document:
    return Document(
        {
            "doctype": "Stock Reconciliation",
            "name": "SR-1",
            "owner": "maker@example.com",
            "workflow_state": state,
            "docstatus": 0,
            "company": "TEST-COMPANY",
            "items": [
                {
                    "item_code": "ITEM-1",
                    "warehouse": "WH-1",
                    "storage_location": "RACK-1",
                    "qty": qty,
                    "current_qty": 3,
                    "current_serial_and_batch_bundle": "CURRENT-1",
                    "serial_and_batch_bundle": "TARGET-1",
                    "batch_no": "BATCH-1",
                }
            ],
        }
    )


class TestStockReconciliationWorkflow(UnitTestCase):
    def test_digest_ignores_recursive_metadata_and_print_evidence_only(self) -> None:
        doc = _doc(workflow.ROUTE.reviewed_state)
        digest = workflow._approval_digest(doc)
        doc.get("items")[0].set("modified", datetime(2026, 10, 1))
        doc.get("items")[0].set("modified_by", "another@example.com")
        doc.set("modified", datetime(2026, 10, 1))
        doc.set("approval_reviewer_user", "reviewer@example.com")
        doc.set("checked_signature", "signed")
        self.assertEqual(workflow._approval_digest(doc), digest)
        for field, value in (
            ("qty", 5),
            ("current_qty", 4),
            ("current_serial_and_batch_bundle", "CURRENT-2"),
            ("batch_no", "BATCH-2"),
            ("storage_location", "RACK-2"),
            ("name", "FORGED-ROW"),
        ):
            original = doc.get("items")[0].get(field)
            doc.get("items")[0].set(field, value)
            with self.subTest(field=field):
                self.assertNotEqual(workflow._approval_digest(doc), digest)
            doc.get("items")[0].set(field, original)

    def test_raw_review_state_and_forged_evidence_require_object_grant(self) -> None:
        previous = _doc(workflow.ROUTE.pending_review_state)
        current = _doc(workflow.ROUTE.reviewed_state)
        current.set("approval_maker_user", "maker@example.com")
        current.set("approval_reviewer_user", "reviewer@example.com")
        current.set("approval_critical_digest", workflow._approval_digest(current))
        with (
            patch.object(current, "get_doc_before_save", return_value=previous),
            patch.object(
                workflow,
                "_persisted_approval",
                return_value={
                    "workflow_state": workflow.ROUTE.pending_review_state,
                    "docstatus": 0,
                },
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(current)

    def test_raw_submitted_state_without_native_docstatus_is_denied(self) -> None:
        previous = _doc(workflow.APPROVED_STATE)
        current = _doc(workflow.SUBMITTED_STATE)
        with patch.object(current, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(current)

    def test_owner_and_maker_retained_on_return_and_original_maker_resubmits(self) -> None:
        returned = _doc(workflow.ROUTE.returned_state)
        returned.set("approval_maker_user", "maker@example.com")
        returned.set("approval_reviewer_user", "reviewer@example.com")
        returned.set("checked_signature", "signature")
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "workflow_state": workflow.ROUTE.reviewed_state,
                    "approval_maker_user": "maker@example.com",
                },
            ),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            workflow.clear_approval(returned)
            authorize.assert_called_once()
        self.assertEqual(returned.get("approval_maker_user"), "maker@example.com")
        self.assertIsNone(returned.get("approval_reviewer_user"))
        self.assertIsNone(returned.get("checked_signature"))
        pending = _doc(workflow.ROUTE.pending_review_state)
        pending.set("approval_maker_user", "maker@example.com")
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "workflow_state": workflow.ROUTE.returned_state,
                    "owner": "maker@example.com",
                    "approval_maker_user": "maker@example.com",
                },
            ),
            patch.object(workflow.frappe, "session", frappe._dict(user="other@example.com")),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_maker(pending)

    def test_signed_review_and_approval_capture_distinct_actors(self) -> None:
        doc = _doc(workflow.ROUTE.reviewed_state)
        doc.set("approval_maker_user", "maker@example.com")
        reviewer = SignedApprovalSnapshot(
            "reviewer@example.com", "EMP-REVIEW", "Reviewer", datetime(2026, 10, 1), "review-signature"
        )
        with (
            patch.object(workflow, "_transition", return_value={"approval_maker_user": "maker@example.com"}),
            patch.object(workflow, "authorize_approval_field_write", return_value=reviewer) as authorize,
        ):
            workflow.capture_review(doc)
            self.assertEqual(authorize.call_args.args[-1], "maker@example.com")
        self.assertEqual(doc.get("checked_by"), "EMP-REVIEW")
        self.assertEqual(doc.get("approval_critical_digest"), workflow._approval_digest(doc))
        doc.set("workflow_state", workflow.APPROVED_STATE)
        approver = SignedApprovalSnapshot(
            "approver@example.com", "EMP-APPROVE", "Approver", datetime(2026, 10, 2), "approval-signature"
        )
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "approval_critical_digest": doc.get("approval_critical_digest"),
                    "approval_maker_user": "maker@example.com",
                    "approval_reviewer_user": "reviewer@example.com",
                    "checked_signature": "review-signature",
                },
            ),
            patch.object(workflow, "authorize_approval_field_write", return_value=approver) as authorize,
        ):
            workflow.capture_approval(doc)
            self.assertEqual(authorize.call_args.args[-2:], ("maker@example.com", ("reviewer@example.com",)))
        self.assertEqual(doc.get("authorized_by"), "EMP-APPROVE")

    def test_submit_and_cancel_require_exact_single_use_grants(self) -> None:
        doc = _doc(workflow.SUBMITTED_STATE)
        with (
            patch.object(workflow, "consume_approval_field_grant", side_effect=frappe.ValidationError),
            patch.object(workflow, "_persisted_approval") as persisted,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)
            persisted.assert_not_called()
        cancelled = _doc(workflow.CANCELLED_STATE)
        cancelled.docstatus = 2
        with (
            patch.object(workflow, "consume_approval_field_grant", side_effect=frappe.ValidationError),
            patch.object(workflow, "_persisted_approval") as persisted,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_cancel(cancelled)
            persisted.assert_not_called()

    def test_submitted_raw_state_and_evidence_update_fail_before_business_change(self) -> None:
        previous = _doc(workflow.SUBMITTED_STATE)
        previous.docstatus = 1
        previous.set("approval_maker_user", "maker@example.com")
        current = _doc(workflow.CANCELLED_STATE)
        current.docstatus = 1
        current.set("approval_maker_user", "maker@example.com")
        with (
            patch.object(current, "get_doc_before_save", return_value=previous),
            patch.object(
                workflow,
                "_persisted_approval",
                return_value={
                    "workflow_state": workflow.SUBMITTED_STATE,
                    "docstatus": 1,
                },
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_after_submit_update(current)
            current.set("workflow_state", workflow.SUBMITTED_STATE)
            current.set("approval_reviewer_user", "forged@example.com")
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_after_submit_update(current)

    def test_legacy_approved_requires_review_but_submitted_can_cancel(self) -> None:
        approved = _doc(workflow.SUBMITTED_STATE)
        approved.set("approval_critical_digest", "stock-reconciliation-approval-v1:historical")
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "workflow_state": workflow.APPROVED_STATE,
                    "approval_critical_digest": "stock-reconciliation-approval-v1:historical",
                },
            ),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.authorize_submit_execution(approved)
            authorize.assert_not_called()
        returned = _doc(workflow.ROUTE.returned_state)
        returned.set("approval_maker_user", "maker@example.com")
        returned.set("approval_critical_digest", "stock-reconciliation-approval-v1:historical")
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "workflow_state": workflow.APPROVED_STATE,
                    "approval_maker_user": "maker@example.com",
                },
            ),
            patch.object(workflow, "authorize_workflow_field_write"),
        ):
            workflow.clear_approval(returned)
        self.assertIsNone(returned.get("approval_critical_digest"))
        submitted = _doc(workflow.CANCELLED_STATE)
        submitted.docstatus = 2
        submitted.set("approval_critical_digest", "stock-reconciliation-approval-v1:historical")
        with (
            patch.object(
                workflow,
                "_transition",
                return_value={
                    "workflow_state": workflow.SUBMITTED_STATE,
                    "docstatus": 1,
                },
            ),
            patch.object(workflow, "consume_approval_field_grant") as consume,
            patch.object(workflow, "require_interactive_user", return_value="reviewer@example.com"),
        ):
            workflow.validate_before_cancel(submitted)
            consume.assert_called_once_with(submitted, workflow.ROUTE.key, workflow.CANCEL_ACTION)
