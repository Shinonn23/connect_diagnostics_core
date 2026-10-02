# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payment_entry_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls
from connect_diagnostics_core.api.frappe.approval_controls import SignedApprovalSnapshot


def _doc(state: str, **values: object) -> Document:
    return Document(
        {
            "doctype": "Payment Entry",
            "name": "PAY-1",
            "owner": "maker@example.com",
            "workflow_state": state,
            "paid_amount": 10,
            **values,
        }
    )


def _row(state: str, **values: object) -> dict[str, object]:
    return {
        "owner": "maker@example.com",
        "workflow_state": state,
        "docstatus": 0,
        **values,
    }


class TestPaymentEntryWorkflow(UnitTestCase):
    def tearDown(self) -> None:
        if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
            delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
        super().tearDown()

    def test_versioned_digest_ignores_recursive_native_stamps_and_print_evidence(self) -> None:
        first = _doc(
            workflow.ROUTE.reviewed_state,
            approval_digest="old",
            status="Draft",
            checked_by="EMP-1",
            references=[
                {
                    "doctype": "Payment Entry Reference",
                    "name": "ROW-1",
                    "modified": "2026-01-01",
                    "modified_by": "maker@example.com",
                    "idx": 1,
                    "reference_name": "INV-1",
                    "allocated_amount": 10,
                }
            ],
        )
        second = _doc(
            workflow.SUBMITTED_STATE,
            docstatus=1,
            approval_digest="new",
            status="Submitted",
            checked_by="EMP-2",
            references=[
                {
                    "doctype": "Payment Entry Reference",
                    "name": "ROW-2",
                    "modified": "2026-01-02",
                    "modified_by": "checker@example.com",
                    "idx": 2,
                    "reference_name": "INV-1",
                    "allocated_amount": 10,
                }
            ],
        )
        self.assertEqual(workflow.get_approval_digest(first), workflow.get_approval_digest(second))
        self.assertTrue(workflow.get_approval_digest(first).startswith("payment-entry-approval-v2:"))

    def test_business_mutations_and_child_order_change_digest(self) -> None:
        original = _doc(
            workflow.ROUTE.reviewed_state,
            references=[
                {"reference_name": "INV-1", "allocated_amount": 10},
                {"reference_name": "INV-2", "allocated_amount": 2},
            ],
        )
        for mutation in (
            {"paid_amount": 11},
            {"paid_to": "Different Bank"},
            {"department": "Different Department"},
            {"references": [{"reference_name": "INV-1", "allocated_amount": 11}]},
            {
                "references": [
                    {"reference_name": "INV-2", "allocated_amount": 2},
                    {"reference_name": "INV-1", "allocated_amount": 10},
                ]
            },
        ):
            changed = _doc(workflow.ROUTE.reviewed_state, **{**original.as_dict(), **mutation})
            self.assertNotEqual(workflow.get_approval_digest(original), workflow.get_approval_digest(changed))

    def test_first_send_requires_locked_owner_and_captures_maker_once(self) -> None:
        doc = _doc(workflow.ROUTE.pending_review_state)
        with (
            patch.object(workflow, "_persisted", return_value=_row(workflow.ROUTE.draft_state)),
            patch.object(workflow.frappe, "session", user="other@example.com"),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_maker_snapshot(doc)
            authorize.assert_not_called()
        with (
            patch.object(workflow, "_persisted", return_value=_row(workflow.ROUTE.draft_state)),
            patch.object(workflow.frappe, "session", user="maker@example.com"),
            patch.object(workflow, "authorize_workflow_field_write", return_value="maker@example.com"),
        ):
            workflow.capture_maker_snapshot(doc)
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
        self.assertTrue(doc.get("approval_maker_at"))

    def test_resubmit_keeps_original_maker_and_timestamp(self) -> None:
        acted_at = datetime(2026, 10, 1)
        doc = _doc(
            workflow.ROUTE.pending_review_state,
            approval_maker_user="maker@example.com",
            approval_maker_at=acted_at,
        )
        with (
            patch.object(
                workflow,
                "_persisted",
                return_value=_row(
                    workflow.ROUTE.returned_state,
                    approval_maker_user="maker@example.com",
                    approval_maker_at=acted_at,
                ),
            ),
            patch.object(workflow.frappe, "session", user="maker@example.com"),
            patch.object(workflow, "authorize_workflow_field_write", return_value="maker@example.com"),
        ):
            workflow.capture_maker_snapshot(doc)
        self.assertEqual(doc.get("approval_maker_at"), acted_at)

    def test_review_captures_signed_employee_and_v2_digest(self) -> None:
        doc = _doc(workflow.ROUTE.reviewed_state, approval_maker_user="maker@example.com")
        snapshot = SignedApprovalSnapshot(
            "checker@example.com", "EMP-1", "Checker", datetime(2026, 10, 1), "signed"
        )
        with (
            patch.object(
                workflow,
                "_persisted",
                return_value=_row(
                    workflow.ROUTE.pending_review_state, approval_maker_user="maker@example.com"
                ),
            ),
            patch.object(workflow, "authorize_approval_field_write", return_value=snapshot),
        ):
            workflow.capture_checker_snapshot(doc)
        self.assertEqual(doc.get("approval_digest"), workflow.get_approval_digest(doc))
        self.assertEqual(doc.get("checked_by"), "EMP-1")
        self.assertEqual(doc.get("checked_at"), snapshot.acted_at)
        self.assertEqual(doc.get("checked_signature"), "signed")

    def test_old_digest_cannot_approve(self) -> None:
        doc = _doc(workflow.APPROVED_STATE, approval_maker_user="maker@example.com")
        with (
            patch.object(
                workflow,
                "_persisted",
                return_value=_row(
                    workflow.ROUTE.reviewed_state,
                    approval_digest="payment-entry-approval-v1:old",
                ),
            ),
            patch.object(workflow, "authorize_approval_field_write") as authorize,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_approver_snapshot(doc)
            authorize.assert_not_called()

    def test_approved_return_clears_decision_but_retains_maker(self) -> None:
        acted_at = datetime(2026, 10, 1)
        doc = _doc(
            workflow.ROUTE.returned_state,
            approval_maker_user="maker@example.com",
            approval_maker_at=acted_at,
            approval_digest="old",
            checked_signature="old signature",
        )
        with (
            patch.object(
                workflow,
                "_persisted",
                return_value=_row(
                    workflow.APPROVED_STATE,
                    approval_maker_user="maker@example.com",
                    approval_maker_at=acted_at,
                ),
            ),
            patch.object(workflow, "authorize_workflow_field_write"),
        ):
            workflow.clear_approval_snapshots(doc)
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
        self.assertEqual(doc.get("approval_maker_at"), acted_at)
        self.assertIsNone(doc.get("approval_digest"))
        self.assertIsNone(doc.get("checked_signature"))

    def test_direct_submit_and_cancel_without_grant_fail_closed(self) -> None:
        for state, guard in (
            (workflow.SUBMITTED_STATE, workflow.validate_before_submit),
            (workflow.CANCELLED_STATE, workflow.validate_before_cancel),
        ):
            with self.subTest(state=state):
                with self.assertRaises(frappe.ValidationError):
                    guard(_doc(state))

    def test_new_document_allows_native_default_draft_only_without_evidence(self) -> None:
        blank = _doc("")
        with patch.object(blank, "get_doc_before_save", return_value=None):
            workflow.validate_workflow(blank)
        forbidden = _doc(workflow.ROUTE.pending_review_state)
        with patch.object(forbidden, "get_doc_before_save", return_value=None):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(forbidden)
        forged = _doc("", approval_maker_user="maker@example.com")
        with patch.object(forged, "get_doc_before_save", return_value=None):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(forged)

    def test_submit_grant_is_object_bound_and_consumed_once(self) -> None:
        doc = _doc(workflow.SUBMITTED_STATE, approval_submit_actor="maker@example.com")
        other = _doc(workflow.SUBMITTED_STATE, approval_submit_actor="maker@example.com")
        approval_controls._mint_approval_field_grant(doc, workflow.ROUTE.key, workflow.ROUTE.execute_action)
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_before_submit(other)
        with (
            patch.object(workflow, "_transition", return_value=_row(workflow.APPROVED_STATE)),
            patch.object(workflow, "_validate_approval"),
            patch.object(workflow, "require_interactive_user", return_value="maker@example.com"),
            patch.object(workflow.frappe, "session", user="maker@example.com"),
        ):
            workflow.validate_before_submit(doc)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)

    def test_wrong_stage_rejected_before_grant_minted(self) -> None:
        doc = _doc(workflow.SUBMITTED_STATE)
        with (
            patch.object(workflow, "_persisted", return_value=_row(workflow.ROUTE.draft_state)),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.authorize_submit_transition(doc)
            authorize.assert_not_called()

    def test_legacy_submitted_cancel_needs_stage_and_grant_but_no_new_digest(self) -> None:
        doc = _doc(workflow.CANCELLED_STATE, approval_cancel_actor="maker@example.com")
        approval_controls._mint_approval_field_grant(doc, workflow.ROUTE.key, workflow.CANCEL_ACTION)
        with (
            patch.object(
                workflow,
                "_persisted",
                return_value=_row(
                    workflow.SUBMITTED_STATE,
                    docstatus=1,
                    approval_digest="payment-entry-approval-v1:old",
                ),
            ),
            patch.object(workflow.frappe, "session", user="maker@example.com"),
            patch.object(workflow, "require_interactive_user", return_value="maker@example.com"),
        ):
            workflow.validate_before_cancel(doc)
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_before_cancel(doc)

    def test_same_state_evidence_edit_and_illegal_transition_are_rejected(self) -> None:
        previous = _doc(workflow.ROUTE.pending_review_state, approval_maker_user="maker@example.com")
        changed = _doc(workflow.ROUTE.pending_review_state, approval_maker_user="other@example.com")
        with patch.object(changed, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(changed)
        illegal = _doc(workflow.APPROVED_STATE)
        with patch.object(illegal, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(illegal)
        changed_owner = _doc(workflow.ROUTE.pending_review_state, owner="other@example.com")
        with patch.object(changed_owner, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(changed_owner)

    def test_submitted_state_only_save_requires_native_docstatus(self) -> None:
        previous = _doc(workflow.APPROVED_STATE, docstatus=0)
        candidate = _doc(workflow.SUBMITTED_STATE, docstatus=0)
        with (
            patch.object(candidate, "get_doc_before_save", return_value=previous),
            patch.object(workflow, "_persisted") as persisted,
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_workflow(candidate)
            persisted.assert_not_called()

    def test_submitted_update_rejects_business_or_evidence_edit(self) -> None:
        previous = _doc(workflow.SUBMITTED_STATE, docstatus=1, checked_signature="original")
        for mutation in (
            {"paid_amount": 11},
            {"checked_signature": "forged"},
            {"owner": "other@example.com"},
        ):
            changed = _doc(
                workflow.SUBMITTED_STATE,
                **{"docstatus": 1, "checked_signature": "original", **mutation},
            )
            with (
                patch.object(changed, "get_doc_before_save", return_value=previous),
                patch.object(
                    workflow,
                    "_persisted",
                    return_value=_row(workflow.SUBMITTED_STATE, docstatus=1),
                ),
            ):
                with self.assertRaises(frappe.ValidationError):
                    workflow.validate_after_submit_update(changed)

    def test_submitted_update_rejects_state_spoof_even_with_forged_flags(self) -> None:
        previous = _doc(workflow.SUBMITTED_STATE, docstatus=1)
        for state, status, persisted in (
            (workflow.CANCELLED_STATE, 1, _row(workflow.SUBMITTED_STATE, docstatus=1)),
            (workflow.SUBMITTED_STATE, 2, _row(workflow.SUBMITTED_STATE, docstatus=1)),
            (workflow.SUBMITTED_STATE, 1, _row(workflow.CANCELLED_STATE, docstatus=1)),
        ):
            with self.subTest(state=state, status=status, persisted=persisted):
                changed = _doc(state, docstatus=status)
                changed.flags.ignore_validate_update_after_submit = True
                changed.flags.ignore_reposting_on_reconciliation = True
                with (
                    patch.object(changed, "get_doc_before_save", return_value=previous),
                    patch.object(workflow, "_persisted", return_value=persisted),
                ):
                    with self.assertRaisesRegex(
                        frappe.ValidationError,
                        "Submitted Payment Entry state cannot change through an update.",
                    ):
                        workflow.validate_after_submit_update(changed)

    def test_unchanged_submitted_update_keeps_state(self) -> None:
        previous = _doc(workflow.SUBMITTED_STATE, docstatus=1)
        changed = _doc(workflow.SUBMITTED_STATE, docstatus=1, modified="later")
        with (
            patch.object(changed, "get_doc_before_save", return_value=previous),
            patch.object(workflow, "_persisted", return_value=_row(workflow.SUBMITTED_STATE, docstatus=1)),
        ):
            workflow.validate_after_submit_update(changed)

    def test_submitted_reference_identity_change_requires_native_capability(self) -> None:
        original_rows = [
            {"name": "ROW-1", "reference_name": "SI-1", "allocated_amount": 10},
            {"name": "ROW-2", "reference_name": "SI-1", "allocated_amount": 10},
        ]
        previous = _doc(workflow.SUBMITTED_STATE, docstatus=1, references=original_rows)
        for changed_rows in (
            [{**original_rows[0], "name": "FORGED"}, original_rows[1]],
            [original_rows[1], original_rows[0]],
            [original_rows[0]],
            [original_rows[0], {**original_rows[1], "name": "RECREATED"}],
        ):
            with self.subTest(changed_rows=changed_rows):
                changed = _doc(workflow.SUBMITTED_STATE, docstatus=1, references=changed_rows)
                with (
                    patch.object(changed, "get_doc_before_save", return_value=previous),
                    patch.object(
                        workflow,
                        "_persisted",
                        return_value=_row(workflow.SUBMITTED_STATE, docstatus=1),
                    ),
                ):
                    with self.assertRaises(frappe.ValidationError):
                        workflow.validate_after_submit_update(changed)

    def test_submitted_business_change_requires_matching_capability_after_evidence_check(self) -> None:
        previous = _doc(workflow.SUBMITTED_STATE, docstatus=1, checked_signature="original")
        changed = _doc(workflow.SUBMITTED_STATE, docstatus=1, checked_signature="original", paid_amount=11)
        with (
            patch.object(changed, "get_doc_before_save", return_value=previous),
            patch.object(workflow, "_persisted", return_value=_row(workflow.SUBMITTED_STATE, docstatus=1)),
            patch(
                "connect_diagnostics_core.api.erpnext.payment_reconciliation.consume_matching_capability"
            ) as consume,
        ):
            workflow.validate_after_submit_update(changed)
            consume.assert_called_once_with(changed, previous)
            changed.set("checked_signature", "forged")
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_after_submit_update(changed)
            consume.assert_called_once()
