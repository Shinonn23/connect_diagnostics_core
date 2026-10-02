# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import journal_entry_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls


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

    def _write_off(self, refs: list[tuple[str, str, str, float]]) -> Document:
        return frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "name": "JE-WRITE-OFF",
                "company": "_Test Company",
                "voucher_type": "Write Off Entry",
                "write_off_based_on": "Accounts Receivable",
                "accounts": [
                    {
                        "account": account,
                        "account_currency": "INR",
                        "party_type": "Customer",
                        "party": customer,
                        "credit_in_account_currency": amount,
                        "credit": amount,
                        "reference_type": "Sales Invoice",
                        "reference_name": invoice,
                    }
                    for invoice, customer, account, amount in refs
                ],
            }
        )

    def test_ar_write_off_requires_exact_submitted_invoice_rows(self) -> None:
        doc = self._write_off([("SI-1", "C-1", "AR-1", 40)])

        def source(doctype: str, name: str, field: str | list[str], **kwargs: object) -> object:
            del kwargs
            if doctype == "Account":
                return "Receivable"
            self.assertEqual((doctype, name), ("Sales Invoice", "SI-1"))
            self.assertIn("party_account_currency", field)
            return frappe._dict(
                docstatus=1,
                company="_Test Company",
                customer="C-1",
                debit_to="AR-1",
                party_account_currency="INR",
            )

        with patch.object(workflow.frappe.db, "get_value", side_effect=source):
            workflow._validate_ar_write_off_rows(doc)

        doc.get("accounts")[0].party = "C-2"
        with patch.object(workflow.frappe.db, "get_value", side_effect=source):
            with self.assertRaises(frappe.ValidationError):
                workflow._validate_ar_write_off_rows(doc)

    def test_ar_write_off_rejects_wrong_company_and_receivable_account(self) -> None:
        for change in ("company", "account"):
            doc = self._write_off([("SI-1", "C-1", "AR-1", 40)])
            if change == "company":
                doc.set("company", "Other Company")
            else:
                doc.get("accounts")[0].account = "AR-OTHER"

            def source(doctype: str, name: str, field: object, **kwargs: object) -> object:
                del kwargs
                if doctype == "Account":
                    return "Receivable"
                return frappe._dict(
                    docstatus=1,
                    company="_Test Company",
                    customer="C-1",
                    debit_to="AR-1",
                    party_account_currency="INR",
                )

            with patch.object(workflow.frappe.db, "get_value", side_effect=source):
                with self.assertRaises(frappe.ValidationError):
                    workflow._validate_ar_write_off_rows(doc)

    def test_ar_reference_and_allocation_are_bound_by_digest(self) -> None:
        doc = self._write_off([("SI-1", "C-1", "AR-1", 40)])

        def facts(_doc: Document, **_kwargs: object) -> list[dict[str, object]]:
            return [
                {
                    "name": name,
                    "docstatus": 1,
                    "company": "_Test Company",
                    "customer": "C-1",
                    "debit_to": "AR-1",
                    "currency": "INR",
                    "party_account_currency": "INR",
                    "outstanding_amount": 100,
                }
                for name in workflow._selected_sales_invoice_names(_doc)
            ]

        with patch.object(workflow, "_receivable_source_facts", side_effect=facts):
            baseline = workflow.get_approval_digest(doc)
            doc.get("accounts")[0].reference_name = "SI-2"
            self.assertNotEqual(baseline, workflow.get_approval_digest(doc))
            doc.get("accounts")[0].reference_name = "SI-1"
            doc.get("accounts")[0].credit_in_account_currency = 41
            doc.get("accounts")[0].credit = 41
            self.assertNotEqual(baseline, workflow.get_approval_digest(doc))

    def test_ar_write_off_rejects_duplicate_rows_and_unreferenced_receivable(self) -> None:
        duplicate = self._write_off([("SI-1", "C-1", "AR-1", 20), ("SI-1", "C-1", "AR-1", 20)])
        with patch.object(workflow.frappe.db, "get_value", return_value="Receivable"):
            with self.assertRaises(frappe.ValidationError):
                workflow._validate_ar_write_off_rows(duplicate)

        duplicate.get("accounts").pop()
        duplicate.append(
            "accounts",
            {"account": "AR-EXTRA", "credit": 1, "credit_in_account_currency": 1},
        )
        with patch.object(workflow.frappe.db, "get_value", return_value="Receivable"):
            with self.assertRaises(frappe.ValidationError):
                workflow._validate_ar_write_off_rows(duplicate)

    def test_ar_write_off_locks_sources_in_sorted_order_and_bounds_allocation(self) -> None:
        doc = self._write_off([("SI-2", "C-2", "AR-2", 20), ("SI-1", "C-1", "AR-1", 10)])
        calls: list[tuple[str, str, bool]] = []

        def source(doctype: str, name: str, field: object, **kwargs: object) -> object:
            if doctype == "Account":
                return "Receivable"
            calls.append((doctype, name, bool(kwargs.get("for_update"))))
            if isinstance(field, list) and "outstanding_amount" in field:
                return frappe._dict(
                    docstatus=1,
                    company="_Test Company",
                    customer=f"C-{name[-1:]}",
                    debit_to=f"AR-{name[-1:]}",
                    currency="INR",
                    party_account_currency="INR",
                    outstanding_amount=5 if name == "SI-1" else 25,
                )
            return frappe._dict(
                docstatus=1,
                company="_Test Company",
                customer=f"C-{name[-1:]}",
                debit_to=f"AR-{name[-1:]}",
                party_account_currency="INR",
            )

        with (
            patch.object(workflow.frappe.db, "get_value", side_effect=source),
            patch.object(workflow.frappe, "get_precision", return_value=2),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow._lock_and_validate_ar_sources(doc)
        self.assertEqual([name for _doctype, name, locked in calls if locked], ["SI-1", "SI-2"])

    def test_ar_source_facts_are_part_of_approval_digest(self) -> None:
        doc = self._write_off([("SI-1", "C-1", "AR-1", 10)])
        source = frappe._dict(
            docstatus=1,
            company="_Test Company",
            customer="C-1",
            debit_to="AR-1",
            currency="INR",
            party_account_currency="INR",
            outstanding_amount=50,
        )
        with patch.object(
            workflow, "_receivable_source_facts", return_value=[{"name": "SI-1", **source}]
        ) as facts:
            first = workflow.get_approval_digest(doc)
            facts.return_value = [{"name": "SI-1", **source, "outstanding_amount": 49}]
            second = workflow.get_approval_digest(doc)
        self.assertNotEqual(first, second)

    def test_user_cannot_spoof_generated_journal_entry_provenance(self) -> None:
        doc = self._write_off([("SI-1", "C-1", "AR-1", 10)])
        doc.set("approval_source_proof", "user-entered")
        with (
            patch(
                "connect_diagnostics_core.api.erpnext.journal_entry_generators._validate_source_provenance",
                side_effect=frappe.ValidationError,
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow._validate_ar_write_off_rows(doc)

    def test_signed_generated_draft_cannot_be_mutated_into_ar_write_off(self) -> None:
        from connect_diagnostics_core.api.erpnext import journal_entry_generators as generators

        doc = self._doc()
        doc.name = "JE-SIGNED-GENERATED"
        doc.set("is_system_generated", 1)
        doc.set("approval_source_doctype", "Bank Transaction")
        doc.set("approval_source_name", "BANK-1")
        doc.set("approval_source_action", "bank_reconciliation")
        doc.set("approval_operation_id", "operation-1")
        doc.set(
            "approval_source_proof",
            generators._source_proof(
                "Bank Transaction", "BANK-1", "bank_reconciliation", "operation-1", doc.name
            ),
        )
        doc.set("voucher_type", "Write Off Entry")
        doc.set("write_off_based_on", "Accounts Receivable")
        doc.set(
            "accounts",
            [
                {
                    "account": "AR-1",
                    "account_currency": "INR",
                    "party_type": "Customer",
                    "party": "C-1",
                    "credit_in_account_currency": 10,
                    "reference_type": "Sales Invoice",
                    "reference_name": "SI-1",
                }
            ],
        )
        with self.assertRaises(frappe.ValidationError):
            workflow._validate_ar_write_off_rows(doc)

    def test_foreign_currency_allocation_uses_native_account_currency_precision(self) -> None:
        doc = self._write_off([("SI-USD", "C-USD", "AR-USD", 60)])
        row = doc.get("accounts")[0]
        row.set("account_currency", "USD")
        row.set("credit_in_account_currency", 60)
        row.set("credit", 120)

        def source(doctype: str, name: str, _field: object, **_kwargs: object) -> object:
            if doctype == "Account":
                return "Receivable"
            return frappe._dict(
                docstatus=1,
                company="_Test Company",
                customer="C-USD",
                debit_to="AR-USD",
                currency="USD",
                party_account_currency="USD",
                outstanding_amount=100,
            )

        with (
            patch.object(workflow.frappe.db, "get_value", side_effect=source),
            patch.object(workflow.frappe, "get_precision", return_value=2) as precision,
        ):
            workflow._lock_and_validate_ar_sources(doc)
        precision.assert_called_with("Sales Invoice", "outstanding_amount", currency="USD")

        row.set("credit_in_account_currency", 101)
        with (
            patch.object(workflow.frappe.db, "get_value", side_effect=source),
            patch.object(workflow.frappe, "get_precision", return_value=2),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow._lock_and_validate_ar_sources(doc)

    def test_direct_submit_requires_transition_marker(self) -> None:
        with (
            patch.object(workflow.frappe.db, "get_value", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(self._doc())

    def test_approval_requires_distinct_signed_checker_and_approver(self) -> None:
        doc = self._doc()
        with (
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(workflow, "_signature", return_value=("EMP-1", "sig")),
            patch.object(workflow, "get_approval_digest", return_value="je-approval-v1:test"),
            patch.object(
                workflow, "require_distinct_actors", wraps=workflow.require_distinct_actors
            ) as distinct,
        ):
            workflow.capture_checker_snapshot(doc)
        distinct.assert_called_once_with("maker@example.com", frappe.session.user, ())
        self.assertEqual(doc.get("approval_digest"), "je-approval-v1:test")

    def test_checker_cannot_be_maker(self) -> None:
        doc = self._doc()
        with (
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.dict(workflow.frappe.session, {"user": "maker@example.com"}),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.capture_checker_snapshot(doc)

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
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow.frappe.db, "set_value") as set_value,
            patch.object(workflow, "_actor_has_permission"),
            patch.object(workflow, "resolve_user", side_effect=lambda identity: identity),
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(
                workflow, "require_distinct_actors", wraps=workflow.require_distinct_actors
            ) as distinct,
        ):
            workflow.validate_before_submit(doc)

        distinct.assert_called_once_with(
            "maker@example.com", "approver@example.com", ("checker@example.com",)
        )
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
