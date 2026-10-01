# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestSalesInvoiceCreditWorkflow(UnitTestCase):
    def tearDown(self) -> None:
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
                side_effect=(self._persisted_identity(), self._original()),
            ),
        ):
            self.assertTrue(workflow.is_credit_note(doc))

    def test_new_named_credit_note_uses_in_memory_scope_before_insert(self) -> None:
        doc = self._doc(name="CN-MANUALLY-NAMED")
        with (
            patch.object(doc, "is_new", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()) as get_value,
        ):
            self.assertTrue(workflow.is_credit_note(doc))
        get_value.assert_called_once_with(
            "Sales Invoice",
            "SI-1",
            ["docstatus", "company", "customer", "currency"],
            as_dict=True,
        )

    def test_original_must_be_submitted_and_match_business_scope(self) -> None:
        doc = self._doc()
        for original in (
            None,
            frappe._dict(docstatus=0, company="ACME", customer="CUST-1", currency="THB"),
            frappe._dict(docstatus=1, company="OTHER", customer="CUST-1", currency="THB"),
        ):
            with (
                self.subTest(original=original),
                patch.object(doc, "is_new", return_value=False),
                patch.object(
                    workflow.frappe.db,
                    "get_value",
                    side_effect=(self._persisted_identity(), original),
                ),
            ):
                self.assertFalse(workflow.is_credit_note(doc))

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
        persisted = frappe._dict(doc.as_dict())
        persisted.workflow_state = workflow.APPROVED_STATE
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow, "critical_payload_digest", return_value="digest"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
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
        persisted = frappe._dict(doc.as_dict())
        persisted.workflow_state = workflow.APPROVED_STATE
        persisted.approval_reviewer_user = "other@example.com"
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow, "consume_approval_field_grant") as consume,
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
