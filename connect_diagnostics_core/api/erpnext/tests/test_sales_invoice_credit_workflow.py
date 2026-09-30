# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestSalesInvoiceCreditWorkflow(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        route = replace(
            workflow.get_route(workflow.ROUTE),
            maker_roles=("Sales User",),
            reviewer_roles=("Sales Manager",),
            final_approver_roles=("C-Level Approver",),
            execution_roles=("Sales Manager",),
        )
        self.route_patcher = patch.object(workflow, "get_route", return_value=route)
        self.route_patcher.start()

    def tearDown(self) -> None:
        self.route_patcher.stop()
        if hasattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY):
            delattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY)
        super().tearDown()

    def _doc(self, **values: object) -> Document:
        return Document(
            {
                "doctype": "Sales Invoice",
                "name": "CN-1",
                "is_return": 1,
                "return_against": "SI-1",
                "company": "ACME",
                "customer": "CUST-1",
                "currency": "THB",
                **values,
            }
        )

    def _persisted_identity(self) -> frappe._dict:
        return frappe._dict(
            is_return=1,
            return_against="SI-1",
            company="ACME",
            customer="CUST-1",
            currency="THB",
        )

    def _original(self) -> frappe._dict:
        return frappe._dict(
            name="SI-1",
            docstatus=1,
            company="ACME",
            customer="CUST-1",
            currency="THB",
        )

    def _persisted_approval(self, doc: Document) -> frappe._dict:
        fields = (
            "approval_critical_digest",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "checked_by",
            "checked_at",
            "checked_signature",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        )
        return frappe._dict(
            workflow_state=workflow.APPROVED_STATE,
            **{field: doc.get(field) for field in fields},
        )

    def test_ordinary_invoice_bypasses_route(self) -> None:
        doc = Document({"doctype": "Sales Invoice", "is_return": 0})
        self.assertFalse(workflow.is_credit_note(doc))

    def test_existing_credit_note_scope_uses_persisted_identity(self) -> None:
        doc = self._doc(is_return=0, return_against=None, company="FORGED")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(
                workflow.frappe.db,
                "get_value",
                return_value=self._persisted_identity(),
            ),
        ):
            self.assertTrue(workflow.is_credit_note(doc))

    def test_new_named_credit_note_uses_in_memory_scope_before_insert(self) -> None:
        doc = self._doc(name="CN-MANUALLY-NAMED")
        with (
            patch.object(doc, "is_new", return_value=True),
            patch.object(workflow.frappe.db, "get_value") as get_value,
        ):
            self.assertTrue(workflow.is_credit_note(doc))
        get_value.assert_not_called()

    def test_invalid_original_cannot_make_the_protected_route_disappear(self) -> None:
        doc = self._doc()
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(workflow.frappe.db, "get_value", return_value=self._persisted_identity()),
        ):
            self.assertTrue(workflow.is_credit_note(doc))

    def test_return_without_source_is_rejected(self) -> None:
        doc = self._doc(return_against=None)
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_approval_fields(doc)

    def test_new_credit_note_rejects_preloaded_approval_evidence(self) -> None:
        doc = self._doc(approval_maker_user="spoofed@example.com")
        with (
            patch.object(doc, "is_new", return_value=True),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_approval_fields(doc)

    def test_amendment_resets_workflow_and_approval_evidence(self) -> None:
        doc = self._doc(
            amended_from="SINV-RETURN-1",
            workflow_state="Sales Invoice Cancelled",
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="old-digest",
        )

        with patch.object(doc, "is_new", return_value=True):
            workflow.validate_approval_fields(doc)

        self.assertEqual(doc.workflow_state, "Sales Invoice Draft")
        for field in workflow.APPROVAL_FIELDS:
            self.assertIsNone(doc.get(field))

    def test_digest_changes_for_tax_and_dynamic_dimension(self) -> None:
        doc = self._doc(
            department="SALES",
            taxes=[{"charge_type": "On Net Total", "rate": 7, "tax_amount": -7}],
        )
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=["department"]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            first = workflow.critical_payload_digest(doc)
            doc.get("taxes")[0].set("tax_amount", -8)
            self.assertNotEqual(first, workflow.critical_payload_digest(doc))
            second = workflow.critical_payload_digest(doc)
            doc.set("department", "SERVICE")
            self.assertNotEqual(second, workflow.critical_payload_digest(doc))

    def test_digest_accepts_native_frappe_posting_time(self) -> None:
        doc = self._doc(set_posting_time=1, posting_time=timedelta(hours=9, minutes=30))
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            self.assertEqual(workflow.critical_payload(doc)["posting_time"], "9:30:00")
            self.assertTrue(workflow.critical_payload_digest(doc))

    def test_digest_ignores_native_auto_posting_time(self) -> None:
        doc = self._doc(set_posting_time=0, posting_time=timedelta(hours=9, minutes=30))
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            first = workflow.critical_payload_digest(doc)
            doc.set("posting_time", timedelta(hours=9, minutes=31))
            self.assertEqual(first, workflow.critical_payload_digest(doc))

    def test_digest_binds_update_stock_behavior(self) -> None:
        doc = self._doc(update_stock=0)
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            first = workflow.critical_payload_digest(doc)
            doc.set("update_stock", 1)
            self.assertNotEqual(first, workflow.critical_payload_digest(doc))

    def test_digest_binds_settlement_fields_and_allocations(self) -> None:
        doc = self._doc(
            write_off_amount=0,
            advances=[
                {
                    "reference_type": "Payment Entry",
                    "reference_name": "ACC-PAY-1",
                    "allocated_amount": 10,
                }
            ],
        )
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            first = workflow.critical_payload_digest(doc)
            doc.set("write_off_amount", -1)
            self.assertNotEqual(first, workflow.critical_payload_digest(doc))
            second = workflow.critical_payload_digest(doc)
            doc.get("advances")[0].set("allocated_amount", 9)
            self.assertNotEqual(second, workflow.critical_payload_digest(doc))

    def test_send_overwrites_maker_but_resubmit_preserves_it(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        send = self._doc(name="new-sales-invoice-1")
        resubmit = self._doc(approval_maker_user="original@example.com")
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "critical_payload_digest", return_value="digest"),
            patch.object(
                workflow,
                "authorize_workflow_field_write",
                return_value="current@example.com",
            ) as authorize,
        ):
            workflow.capture_maker(send)
            self.assertEqual(send.get("approval_maker_user"), "current@example.com")
            authorize.assert_called_with(send, workflow.ROUTE, route.send_action, route.maker_roles)

            workflow.capture_maker(resubmit)
            self.assertEqual(resubmit.get("approval_maker_user"), "original@example.com")
            authorize.assert_called_with(
                resubmit,
                workflow.ROUTE,
                route.resubmit_action,
                route.maker_roles,
            )

    def test_approve_rejects_missing_or_stale_review_digest(self) -> None:
        for stored in (None, "stale"):
            doc = self._doc(
                approval_maker_user="maker@example.com",
                approval_reviewer_user="reviewer@example.com",
                approval_critical_digest=stored,
            )
            with (
                self.subTest(stored=stored),
                patch.object(workflow, "is_credit_note", return_value=True),
                patch.object(workflow, "critical_payload_digest", return_value="current"),
                patch.object(workflow, "authorize_approval_field_write") as authorize,
                self.assertRaises(frappe.ValidationError),
            ):
                workflow.capture_approval(doc)
            authorize.assert_not_called()

    def test_unknown_transition_cannot_change_evidence(self) -> None:
        previous = self._doc(
            workflow_state="Sales Invoice Credit Draft",
            approval_maker_user="maker@example.com",
        )
        doc = self._doc(
            workflow_state="Sales Invoice Credit Draft",
            approval_maker_user="forged@example.com",
        )
        doc._doc_before_save = previous
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_approval_fields(doc)

    def test_review_consumes_exact_grant_and_blocks_unrelated_evidence(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        previous = self._doc(
            workflow_state=route.pending_review_state,
            approval_maker_user="maker@example.com",
        )
        doc = self._doc(
            workflow_state=route.reviewed_state,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="signature",
        )
        doc._doc_before_save = previous
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.validate_approval_fields(doc)
        consume.assert_called_once_with(doc, workflow.ROUTE, route.review_action)

        doc.set("approval_authorized_user", "forged@example.com")
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "consume_approval_field_grant") as consume,
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_approval_fields(doc)
        consume.assert_not_called()

    def test_direct_cancel_without_transition_grant_is_denied(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        doc = self._doc(workflow_state=route.cancelled_state)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=route.submitted_state),
            patch.object(workflow, "resolve_user", return_value="manager@example.com"),
            patch.object(workflow.frappe, "get_roles", return_value=["Sales Manager"]),
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "consume_approval_field_grant", side_effect=frappe.ValidationError),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_cancel(doc)

    def test_cancel_consumes_exact_transition_grant(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        doc = self._doc(workflow_state=route.cancelled_state)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=route.submitted_state),
            patch.object(workflow, "resolve_user", return_value="manager@example.com"),
            patch.object(workflow.frappe, "get_roles", return_value=["Sales Manager"]),
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "consume_approval_field_grant") as consume,
            patch.dict(frappe.session, {"user": "manager@example.com"}),
        ):
            workflow.validate_before_cancel(doc)
        consume.assert_called_once_with(doc, workflow.ROUTE, route.cancel_action)

    def test_execute_validation_leaves_grant_for_before_submit(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        previous = self._doc(workflow_state=route.approved_state)
        doc = self._doc(workflow_state=route.submitted_state)
        doc._doc_before_save = previous
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.validate_approval_fields(doc)
        consume.assert_not_called()

    def test_direct_submit_without_transition_grant_is_denied(self) -> None:
        doc = self._doc(
            workflow_state=workflow.SUBMITTED_STATE,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="review-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-09-26 11:00:00",
            authorized_signature="approve-signature",
        )
        persisted = self._persisted_approval(doc)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow, "critical_payload_digest", return_value="digest"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
            patch.object(doc, "validate", create=True),
            patch.dict(frappe.session, {"user": "approver@example.com"}),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_submit_rejects_persisted_actor_tampering_before_grant_use(self) -> None:
        doc = self._doc(
            workflow_state=workflow.SUBMITTED_STATE,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="review-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-09-26 11:00:00",
            authorized_signature="approve-signature",
        )
        persisted = self._persisted_approval(doc)
        persisted.approval_reviewer_user = "other@example.com"
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow, "consume_approval_field_grant") as consume,
            patch.object(doc, "validate", create=True),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)
        consume.assert_not_called()

    def test_return_and_reject_use_distinct_declared_actions(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        doc = self._doc(approval_maker_user="maker@example.com")
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            workflow.clear_on_return(doc)
            authorize.assert_called_once_with(
                doc,
                workflow.ROUTE,
                route.return_action,
                route.reviewer_roles,
            )
            authorize.reset_mock()
            workflow.clear_on_reject(doc)
            authorize.assert_called_once_with(
                doc,
                workflow.ROUTE,
                route.reject_action,
                route.final_approver_roles,
            )

    def test_submit_locks_source_then_note_and_runs_native_validation(self) -> None:
        doc = self._doc(
            workflow_state=workflow.SUBMITTED_STATE,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="review-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-09-26 11:00:00",
            authorized_signature="approve-signature",
        )
        persisted = self._persisted_approval(doc)
        source = self._original()
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", side_effect=(source, persisted)) as get_value,
            patch.object(workflow, "critical_payload_digest", return_value="digest"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
            patch.object(workflow, "require_distinct_actors"),
            patch.object(workflow.frappe, "get_roles", return_value=["Sales Manager"]),
            patch.object(workflow, "require_permission"),
            patch.object(doc, "validate", create=True) as native_validate,
            patch.object(workflow, "consume_approval_field_grant") as consume,
            patch.dict(frappe.session, {"user": "executor@example.com"}),
        ):
            workflow.validate_before_submit(doc)
        self.assertEqual(get_value.call_args_list[0].args[:2], ("Sales Invoice", "SI-1"))
        self.assertEqual(get_value.call_args_list[1].args[:2], ("Sales Invoice", "CN-1"))
        native_validate.assert_called_once_with()
        consume.assert_called_once_with(
            doc,
            workflow.ROUTE,
            workflow.get_route(workflow.ROUTE).execute_action,
        )
