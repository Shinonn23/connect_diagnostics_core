# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payment_entry_workflow


class TestPaymentEntryWorkflow(UnitTestCase):
    def test_digest_excludes_structural_and_approval_fields(self) -> None:
        first = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "docstatus": 0,
                "workflow_state": "Payment Entry Approved",
                "approval_submit_actor": None,
                "paid_amount": 10,
            }
        )
        second = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "docstatus": 1,
                "workflow_state": "Payment Entry Submitted",
                "approval_submit_actor": "submit@example.com",
                "paid_amount": 10,
            }
        )
        self.assertEqual(
            payment_entry_workflow.get_approval_digest(first),
            payment_entry_workflow.get_approval_digest(second),
        )

    def test_digest_changes_when_business_value_changes(self) -> None:
        first = Document({"doctype": "Payment Entry", "paid_amount": 10})
        second = Document({"doctype": "Payment Entry", "paid_amount": 11})
        self.assertNotEqual(
            payment_entry_workflow.get_approval_digest(first),
            payment_entry_workflow.get_approval_digest(second),
        )

    def test_direct_submit_fails_closed_and_clears_marker(self) -> None:
        doc = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "workflow_state": payment_entry_workflow.SUBMITTED_STATE,
            }
        )
        setattr(payment_entry_workflow.frappe.flags, payment_entry_workflow._EXECUTION_FLAG, None)
        with self.assertRaises(Exception):
            payment_entry_workflow.validate_before_submit(doc)
        self.assertIsNone(
            getattr(payment_entry_workflow.frappe.flags, payment_entry_workflow._EXECUTION_FLAG, None)
        )

    def test_submit_marker_is_consumed_after_valid_guard(self) -> None:
        doc = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "workflow_state": payment_entry_workflow.SUBMITTED_STATE,
                "approval_digest": "digest",
            }
        )
        persisted = {
            "workflow_state": payment_entry_workflow.APPROVED_STATE,
            "docstatus": 0,
            "approval_digest": "digest",
            "approval_maker_user": "maker@example.com",
            "approval_checker_user": "checker@example.com",
            "approval_approver_user": "approver@example.com",
        }
        setattr(
            payment_entry_workflow.frappe.flags,
            payment_entry_workflow._EXECUTION_FLAG,
            payment_entry_workflow._execution_marker(doc, "submit"),
        )
        with (
            patch.object(payment_entry_workflow, "get_approval_digest", return_value="digest"),
            patch.object(payment_entry_workflow, "_persisted", return_value=persisted),
            patch.object(payment_entry_workflow, "require_permission"),
            patch.object(payment_entry_workflow, "require_distinct_actors"),
        ):
            payment_entry_workflow.validate_before_submit(doc)
        self.assertIsNone(
            getattr(payment_entry_workflow.frappe.flags, payment_entry_workflow._EXECUTION_FLAG, None)
        )

    def test_direct_cancel_fails_closed(self) -> None:
        doc = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "workflow_state": payment_entry_workflow.CANCELLED_STATE,
            }
        )
        setattr(payment_entry_workflow.frappe.flags, payment_entry_workflow._EXECUTION_FLAG, None)
        with self.assertRaises(Exception):
            payment_entry_workflow.validate_before_cancel(doc)

    def test_authorize_submit_binds_marker_to_request_and_actor(self) -> None:
        doc = Document(
            {
                "doctype": "Payment Entry",
                "name": "PAY-1",
                "workflow_state": payment_entry_workflow.SUBMITTED_STATE,
                "approval_digest": "digest",
            }
        )
        persisted = {
            "workflow_state": payment_entry_workflow.APPROVED_STATE,
            "docstatus": 0,
            "approval_digest": "digest",
            "approval_maker_user": "maker@example.com",
            "approval_checker_user": "checker@example.com",
            "approval_approver_user": "approver@example.com",
        }
        with (
            patch.object(payment_entry_workflow, "get_approval_digest", return_value="digest"),
            patch.object(payment_entry_workflow, "_persisted", return_value=persisted),
            patch.object(payment_entry_workflow, "require_permission"),
            patch.object(payment_entry_workflow, "require_distinct_actors"),
            patch.object(payment_entry_workflow.frappe, "session", user="submit@example.com"),
        ):
            payment_entry_workflow.authorize_submit_transition(doc)
            self.assertEqual(doc.get("approval_submit_actor"), "submit@example.com")
            self.assertEqual(
                getattr(payment_entry_workflow.frappe.flags, payment_entry_workflow._EXECUTION_FLAG),
                payment_entry_workflow._execution_marker(doc, "submit"),
            )
        payment_entry_workflow._clear_execution_marker()
