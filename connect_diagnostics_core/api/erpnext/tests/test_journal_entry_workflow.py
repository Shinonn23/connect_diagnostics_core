# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import journal_entry_workflow as workflow


class TestJournalEntryWorkflow(UnitTestCase):
    def _doc(self) -> Document:
        return frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "name": "JE-TEST",
                "owner": "maker@example.com",
                "approval_maker_user": "maker@example.com",
                "workflow_state": workflow.SUBMITTED_STATE,
                "company": "_Test Company",
                "posting_date": date(2026, 9, 26),
                "voucher_type": "Journal Entry",
                "accounts": [
                    {"account": "Cash - _TC", "debit_in_account_currency": 100},
                    {"account": "Income - _TC", "credit_in_account_currency": 100},
                ],
            }
        )

    def test_digest_is_versioned_and_binds_account_rows(self) -> None:
        doc = self._doc()
        baseline = workflow.get_approval_digest(doc)
        doc.get("accounts")[0].debit_in_account_currency = 101
        self.assertTrue(baseline.startswith("je-approval-v1:"))
        self.assertNotEqual(baseline, workflow.get_approval_digest(doc))

    def test_transition_state_and_snapshot_fields_are_excluded(self) -> None:
        doc = self._doc()
        baseline = workflow.get_approval_digest(doc)
        doc.set("workflow_state", workflow.APPROVED_STATE)
        doc.set("approval_digest", "spoof")
        doc.set("approval_checker_user", "checker@example.com")
        self.assertEqual(baseline, workflow.get_approval_digest(doc))

    def test_enabled_accounting_dimension_is_digest_bound(self) -> None:
        doc = self._doc()
        doc.get("accounts")[0].department = "Department A"
        baseline = workflow.get_approval_digest(doc)
        doc.get("accounts")[0].department = "Department B"
        self.assertNotEqual(baseline, workflow.get_approval_digest(doc))

    def test_direct_submit_requires_transition_marker(self) -> None:
        with (
            patch.object(workflow.frappe.db, "get_value", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(self._doc())

    def test_approval_requires_distinct_signed_checker_and_approver(self) -> None:
        doc = self._doc()
        with (
            patch.object(workflow, "_signature", return_value=("EMP-1", "sig")),
            patch.object(workflow, "require_distinct_actors"),
        ):
            with patch.object(workflow, "get_approval_digest", return_value="je-approval-v1:test"):
                workflow.capture_checker_snapshot(doc)
                self.assertEqual(doc.get("approval_digest"), "je-approval-v1:test")

    def test_sync_submit_consumes_transition_proof(self) -> None:
        doc = self._doc()
        persisted = frappe._dict(
            workflow_state=workflow.APPROVED_STATE,
            approval_digest="digest",
            approval_digest_schema="schema",
            approval_submit_proof="proof",
            approval_submit_actor="submitter@example.com",
            approval_maker_user="maker@example.com",
            approval_checker_user="checker@example.com",
            approval_approver_user="approver@example.com",
            approval_checker_signature="checker-signature",
            approval_approver_signature="approver-signature",
        )
        frappe.flags.journal_entry_submit_execution = {
            "doctype": "Journal Entry",
            "name": doc.name,
            "proof": "proof",
        }
        doc.update(
            {
                "approval_submit_proof": "proof",
                "approval_submit_actor": "submitter@example.com",
                "approval_digest": "digest",
                "approval_digest_schema": "schema",
            }
        )
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "approval_digest_schema", return_value="schema"),
            patch.object(workflow, "_proof", return_value="proof"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow.frappe.db, "set_value") as set_value,
            patch.object(workflow, "_actor_has_permission"),
            patch.object(workflow, "require_distinct_actors"),
        ):
            workflow.validate_before_submit(doc)

        set_value.assert_called_once_with(
            "Journal Entry", doc.name, "approval_submit_proof", None, update_modified=False
        )
        self.assertIsNone(doc.get("approval_submit_proof"))

    def test_background_worker_cannot_consume_proof_without_in_process_marker(self) -> None:
        doc = self._doc()
        persisted = frappe._dict(
            workflow_state=workflow.APPROVED_STATE,
            approval_digest="digest",
            approval_digest_schema="schema",
            approval_submit_proof="proof",
            approval_submit_actor="submitter@example.com",
            approval_maker_user="maker@example.com",
            approval_checker_user="checker@example.com",
            approval_approver_user="approver@example.com",
            approval_checker_signature="checker-signature",
            approval_approver_signature="approver-signature",
        )
        doc.update(
            {
                "approval_submit_proof": "proof",
                "approval_submit_actor": "submitter@example.com",
                "approval_digest": "digest",
                "approval_digest_schema": "schema",
            }
        )
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "approval_digest_schema", return_value="schema"),
            patch.object(workflow, "_proof", return_value="proof"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_consumed_proof_cannot_be_replayed(self) -> None:
        doc = self._doc()
        persisted = frappe._dict(
            workflow_state=workflow.APPROVED_STATE,
            approval_digest="digest",
            approval_digest_schema="schema",
            approval_submit_proof=None,
            approval_submit_actor="submitter@example.com",
        )
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "_proof", return_value="proof"),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_queue_worker_rejects_serialized_proof_mismatch(self) -> None:
        doc = self._doc()
        doc.update(
            {
                "approval_submit_proof": "stale-proof",
                "approval_submit_actor": "submitter@example.com",
                "approval_digest": "digest",
                "approval_digest_schema": "schema",
            }
        )
        persisted = frappe._dict(
            workflow_state=workflow.APPROVED_STATE,
            approval_digest="digest",
            approval_digest_schema="schema",
            approval_submit_proof="current-proof",
            approval_submit_actor="submitter@example.com",
        )
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "approval_digest_schema", return_value="schema"),
            patch.object(workflow, "_proof", return_value="current-proof"),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)
