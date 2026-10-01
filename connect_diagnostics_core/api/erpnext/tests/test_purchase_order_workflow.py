# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import Mock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import purchase_order_workflow as workflow


class TestPurchaseOrderWorkflow(UnitTestCase):
    def _doc(self, **values: object) -> Document:
        return frappe.get_doc({"doctype": "Purchase Order", "name": "PO-TEST", **values})

    def test_digest_is_stable_and_changes_for_commitment_value(self) -> None:
        doc = self._doc(
            owner="maker@example.com",
            supplier="SUP-1",
            company="Company",
            currency="THB",
            items=[],
        )
        first = workflow.get_commitment_digest(doc)
        self.assertEqual(first, workflow.get_commitment_digest(doc))
        doc.set("currency", "USD")
        self.assertNotEqual(first, workflow.get_commitment_digest(doc))
        doc.set("currency", "THB")
        doc.set("owner", "approver@example.com")
        self.assertNotEqual(first, workflow.get_commitment_digest(doc))

    def test_digest_accepts_native_integral_float_conversion(self) -> None:
        first = self._doc(base_discount_amount=0, items=[{"item_code": "A", "qty": 1}])
        second = self._doc(base_discount_amount=0.0, items=[{"item_code": "A", "qty": 1.0}])
        changed = self._doc(base_discount_amount=0.01, items=[{"item_code": "A", "qty": 1.0}])
        self.assertEqual(workflow.get_commitment_digest(first), workflow.get_commitment_digest(second))
        self.assertNotEqual(workflow.get_commitment_digest(first), workflow.get_commitment_digest(changed))

    @patch.object(workflow.frappe, "throw")
    def test_maker_change_after_review_is_rejected(self, throw: Mock) -> None:
        previous = self._doc(
            workflow_state=workflow.APPROVAL_STATE,
            owner="maker@example.com",
            supplier="SUP-1",
        )
        current = self._doc(
            workflow_state=workflow.APPROVAL_STATE,
            owner="approver@example.com",
            supplier="SUP-1",
        )
        with patch.object(Document, "get_doc_before_save", return_value=previous):
            workflow.validate_workflow(current)
        throw.assert_called_once()

    def test_child_row_order_is_commitment_critical(self) -> None:
        first = self._doc(items=[{"item_code": "A", "qty": 1}, {"item_code": "B", "qty": 1}])
        second = self._doc(items=[{"item_code": "B", "qty": 1}, {"item_code": "A", "qty": 1}])
        self.assertNotEqual(workflow.get_commitment_digest(first), workflow.get_commitment_digest(second))

    def test_downstream_generated_status_values_do_not_invalidate_approval(self) -> None:
        doc = self._doc(
            supplier="SUP-1",
            items=[{"item_code": "A", "qty": 1, "received_qty": 0, "returned_qty": 0}],
        )
        first = workflow.get_commitment_digest(doc)

        doc.set("status", "To Receive")
        doc.set("per_received", 50)
        doc.set("per_billed", 25)
        doc.set("advance_paid", 100)
        doc.get("items")[0].received_qty = 0.5
        doc.get("items")[0].returned_qty = 0.25

        self.assertEqual(first, workflow.get_commitment_digest(doc))

    @patch.object(workflow, "require_permission")
    @patch.object(workflow, "_employee_snapshot", return_value=("EMP-1", "sig"))
    @patch.object(workflow.frappe, "session", Mock(user="reviewer@example.com"))
    def test_review_snapshot_captures_revision_evidence(self, _employee: Mock, _permission: Mock) -> None:
        doc = self._doc(owner="maker@example.com", supplier="SUP-1")
        with patch.object(workflow, "require_distinct_actors"):
            workflow.capture_review_snapshot(doc)
        self.assertEqual(doc.get("approval_digest_version"), workflow.DIGEST_VERSION)
        self.assertEqual(doc.get("approval_reviewer_user"), "reviewer@example.com")
        self.assertEqual(doc.get("checked_by"), "EMP-1")
        self.assertEqual(doc.get("checked_signature"), "sig")

    def test_clear_snapshot_removes_all_approval_evidence(self) -> None:
        doc = self._doc(
            approval_critical_digest="digest",
            approval_digest_version=workflow.DIGEST_VERSION,
            approval_reviewer_user="reviewer",
            approval_authorized_user="approver",
            checked_by="EMP-1",
            checked_signature="review",
            authorized_by="EMP-2",
            authorized_signature="approve",
        )
        workflow.clear_approval_snapshots(doc)
        for field in workflow.SNAPSHOT_FIELDS:
            self.assertFalse(doc.get(field))

    @patch.object(workflow.frappe, "throw")
    def test_mutation_after_review_is_rejected(self, throw: Mock) -> None:
        previous = self._doc(workflow_state=workflow.APPROVAL_STATE, supplier="SUP-1")
        current = self._doc(workflow_state=workflow.APPROVAL_STATE, supplier="SUP-2")
        with patch.object(Document, "get_doc_before_save", return_value=previous):
            workflow.validate_workflow(current)
        throw.assert_called_once()

    @patch.object(workflow.frappe, "throw")
    @patch.object(workflow, "require_permission")
    def test_submit_requires_persisted_approved_digest_and_signatures(
        self, _permission: Mock, throw: Mock
    ) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-1")
        digest = workflow.get_commitment_digest(doc)
        doc.set("approval_critical_digest", digest)
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": digest,
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "submit"),
        )
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "require_distinct_actors"),
        ):
            workflow.validate_before_submit(doc)
        throw.assert_not_called()

    @patch.object(workflow, "require_permission")
    def test_state_spoof_without_native_post_transition_is_rejected(self, _permission: Mock) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-1")
        digest = workflow.get_commitment_digest(doc)
        doc.set("approval_critical_digest", digest)
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": digest,
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    @patch.object(workflow, "require_permission")
    def test_submit_rejects_stale_commitment_digest(self, _permission: Mock) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-2")
        doc.set("approval_critical_digest", "old-digest")
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": "old-digest",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "submit"),
        )

        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_persisted_approval_uses_row_lock(self) -> None:
        doc = self._doc()
        with patch.object(workflow.frappe.db, "get_value", return_value={"workflow_state": "Draft"}) as get:
            workflow._persisted_approval(doc)

        self.assertTrue(get.call_args.kwargs["for_update"])

    def test_cancel_accepts_only_native_submitted_to_cancelled_transition(self) -> None:
        doc = self._doc(docstatus=1, workflow_state=workflow.CANCELLED_STATE)
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "cancel"),
        )

        with patch.object(workflow.frappe.db, "get_value", return_value=workflow.SUBMITTED_STATE):
            workflow.validate_before_cancel(doc)

    @patch.object(workflow.frappe, "throw")
    def test_cancel_requires_persisted_submitted_state(self, throw: Mock) -> None:
        doc = self._doc(docstatus=1, workflow_state=workflow.CANCELLED_STATE)
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "cancel"),
        )

        with patch.object(workflow.frappe.db, "get_value", return_value=workflow.APPROVED_STATE):
            workflow.validate_before_cancel(doc)

        throw.assert_called_once()
