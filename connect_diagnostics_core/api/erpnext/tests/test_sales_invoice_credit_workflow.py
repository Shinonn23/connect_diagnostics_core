# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import frappe
from erpnext.controllers import sales_and_purchase_return as native_returns
from erpnext.controllers.sales_and_purchase_return import validate_quantity
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls
from connect_diagnostics_core.api.frappe.approval_routes import get_route


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

    def test_canonical_route_roles_are_used_without_test_override(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        self.assertEqual(route.maker_roles, ("Sales User", "Accounts User"))
        self.assertEqual(route.reviewer_roles, ("Sales Manager",))
        self.assertEqual(route.final_approver_roles, ("Accounts Manager",))
        self.assertEqual(route.execution_roles, ("Accounts Manager",))
        self.assertEqual(route.cancel_roles, ("Sales Manager",))

    def test_credit_terminal_label_requires_matching_native_docstatus(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        for state, status in ((route.submitted_state, 0), (route.cancelled_state, 1)):
            with (
                self.subTest(state=state),
                patch.object(workflow, "is_credit_note", return_value=True),
                self.assertRaises(frappe.ValidationError),
            ):
                workflow.validate_approval_fields(self._doc(workflow_state=state, docstatus=status))

    def test_submitted_credit_update_requires_locked_same_state(self) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, docstatus=1)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "require_locked_submitted_update") as locked,
            patch.object(workflow.SalesInvoice, "check_if_fields_updated", return_value=False) as native,
            patch.object(doc, "get_doc_before_save", return_value=doc),
            patch.object(workflow, "critical_payload_digest", return_value="same"),
        ):
            workflow.validate_after_submit_update(doc)
        locked.assert_called_once_with(doc, workflow.SUBMITTED_STATE)
        self.assertEqual(
            native.call_args.args[2],
            {"items": ("income_account", "expense_account", "discount_account"), "taxes": ("account_head",)},
        )
        with (
            patch.object(workflow, "is_credit_note", return_value=False),
            patch.object(workflow, "require_locked_submitted_update") as locked,
        ):
            workflow.validate_after_submit_update(doc)
        locked.assert_not_called()

    def test_submitted_credit_update_rejects_approval_and_critical_changes(self) -> None:
        previous = self._doc(workflow_state=workflow.SUBMITTED_STATE, docstatus=1)
        changed = self._doc(
            workflow_state=workflow.SUBMITTED_STATE,
            docstatus=1,
            approval_maker_user="forged",
        )
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "require_locked_submitted_update"),
            patch.object(workflow.SalesInvoice, "check_if_fields_updated", return_value=False),
            patch.object(changed, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_after_submit_update(changed)

        changed.set("approval_maker_user", None)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "require_locked_submitted_update"),
            patch.object(workflow.SalesInvoice, "check_if_fields_updated", return_value=False),
            patch.object(changed, "get_doc_before_save", return_value=previous),
            patch.object(workflow, "critical_payload_digest", side_effect=("before", "after")),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_after_submit_update(changed)

    def test_submitted_credit_native_repost_fields_are_blocked_first(self) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, docstatus=1)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "require_locked_submitted_update") as locked,
            patch.object(workflow.SalesInvoice, "check_if_fields_updated", return_value=True) as native,
            patch.object(doc, "get_doc_before_save") as previous,
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_after_submit_update(doc)
        locked.assert_called_once_with(doc, workflow.SUBMITTED_STATE)
        native.assert_called_once()
        previous.assert_not_called()
        self.assertIn("additional_discount_account", native.call_args.args[1])
        self.assertIn("loyalty_redemption_account", native.call_args.args[1])
        self.assertIn("unrealized_profit_loss_account", native.call_args.args[1])

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

        self.assertEqual(doc.get("workflow_state"), "Sales Invoice Draft")
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
                patch.object(
                    workflow, "_lock_and_read_return_rows", return_value=(self._original(), [], [], {}, {})
                ),
                patch.object(workflow, "_require_target_projection_matches"),
                patch.object(workflow, "_validate_cumulative_return_quantity"),
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

    def test_credit_note_route_identity_cannot_be_saved_away(self) -> None:
        previous = self._doc(is_return=1, return_against="SI-1")
        for changes in ({"is_return": 0, "return_against": None}, {"return_against": "SI-2"}):
            doc = self._doc(**changes)
            doc._doc_before_save = previous
            with (
                self.subTest(changes=changes),
                patch.object(workflow, "is_credit_note", return_value=True),
                self.assertRaisesRegex(frappe.ValidationError, "route identity cannot be changed"),
            ):
                workflow.validate_approval_fields(doc)

    def test_locked_target_projection_rejects_stale_loaded_posting_fields(self) -> None:
        doc = self._doc(debit_to="Debtors - ACME")
        with (
            patch.object(
                workflow,
                "_native_document_projection",
                side_effect=({"debit_to": "Debtors - ACME"}, {"debit_to": "Other - ACME"}),
            ),
            self.assertRaisesRegex(frappe.ValidationError, "changed after it was loaded"),
        ):
            workflow._require_target_projection_matches(doc, {"debit_to": "Other - ACME"})

    def test_approved_return_is_an_action_bound_evidence_reset(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        previous = self._doc(
            workflow_state=route.approved_state,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="v1-stale-digest",
            checked_by="reviewer employee",
        )
        doc = self._doc(
            workflow_state=route.returned_state,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="v1-stale-digest",
            checked_by="old reviewer",
            checked_at="old timestamp",
            checked_signature="old signature",
            authorized_by="old approver",
            authorized_at="old timestamp",
            authorized_signature="old signature",
        )
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(
                workflow, "authorize_workflow_field_write", return_value="manager@example.com"
            ) as authorize,
        ):
            workflow.clear_on_return(doc)
        authorize.assert_called_once_with(doc, workflow.ROUTE, route.return_action, route.reviewer_roles)
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
        for field in workflow.APPROVAL_FIELDS - {"approval_maker_user"}:
            self.assertIsNone(doc.get(field))
        doc._doc_before_save = previous
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.validate_approval_fields(doc)
        consume.assert_called_once_with(doc, workflow.ROUTE, route.return_action)

        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "critical_payload_digest", return_value="fresh-digest"),
            patch.object(
                workflow, "authorize_workflow_field_write", return_value="maker@example.com"
            ) as authorize_maker,
        ):
            workflow.capture_maker(doc)
        authorize_maker.assert_called_once_with(doc, workflow.ROUTE, route.resubmit_action, route.maker_roles)
        self.assertEqual(doc.get("approval_critical_digest"), "fresh-digest")
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")

        forged = self._doc(
            workflow_state=route.returned_state,
            approval_maker_user="maker@example.com",
            approval_critical_digest=None,
        )
        forged._doc_before_save = previous
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_approval_fields(forged)

    def test_revision_two_digest_binds_additional_native_posting_fields(self) -> None:
        doc = self._doc(
            debit_to="Debtors - ACME",
            is_opening="No",
            cost_center="Main - ACME",
            items=[
                {
                    "item_code": "ITEM-1",
                    "stock_qty": -2,
                    "discount_percentage": 5,
                    "discount_amount": 10,
                    "discount_account": "Discount - ACME",
                    "serial_and_batch_bundle": "SABB-1",
                }
            ],
        )
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=self._original()),
        ):
            self.assertEqual(workflow.critical_payload(doc)["digest_version"], "sales-invoice-credit-note-v2")
            original = workflow.critical_payload_digest(doc)
            doc.set("debit_to", "Other Debtors - ACME")
            self.assertNotEqual(original, workflow.critical_payload_digest(doc))
            original = workflow.critical_payload_digest(doc)
            doc.get("items")[0].set("discount_account", "Other Discount - ACME")
            self.assertNotEqual(original, workflow.critical_payload_digest(doc))

    def test_current_return_guard_uses_only_native_quantity_branch_and_precision(self) -> None:
        source = [frappe._dict(name="SII-1", item_code="ITEM-1", qty=1.2, stock_qty=2.4, conversion_factor=2)]
        returned = [
            frappe._dict(
                parent="CN-OLD",
                child="CN-OLD-ROW",
                item_code="ITEM-1",
                sales_invoice_item="SII-1",
                qty=-0.3,
                stock_qty=-0.6,
                conversion_factor=2,
            )
        ]
        doc = self._doc(
            update_stock=0,
            company="ACME",
            items=[
                {
                    "item_code": "ITEM-1",
                    "sales_invoice_item": "SII-1",
                    "qty": -0.9,
                    "stock_qty": -1.8,
                    "conversion_factor": 2,
                    "idx": 1,
                }
            ],
        )
        with (
            patch.object(workflow, "get_field_precision", return_value=2) as precision,
            patch.object(workflow.erpnext, "get_company_currency", return_value="THB"),
            patch.object(workflow.frappe, "get_meta") as get_meta,
            patch.object(native_returns, "get_field_precision", return_value=2),
        ):
            get_meta.return_value.get_field.return_value = object()
            workflow._validate_cumulative_return_quantity(doc, source, returned)
            validate_quantity(
                doc,
                ("ITEM-1", "SII-1"),
                doc.get("items")[0],
                frappe._dict(qty=1.2, stock_qty=2.4, conversion_factor=2),
                {},
                {("ITEM-1", "SII-1"): frappe._dict(qty=0.3, stock_qty=0.6)},
            )
            precision.assert_called_once()
        doc.set("update_stock", 1)
        with (
            patch.object(workflow, "get_field_precision", return_value=2),
            patch.object(workflow.erpnext, "get_company_currency", return_value="THB"),
            patch.object(workflow.frappe, "get_meta") as get_meta,
            patch.object(native_returns, "get_field_precision", return_value=2),
        ):
            get_meta.return_value.get_field.return_value = object()
            workflow._validate_cumulative_return_quantity(doc, source, returned)
            validate_quantity(
                doc,
                ("ITEM-1", "SII-1"),
                doc.get("items")[0],
                frappe._dict(qty=1.2, stock_qty=2.4, conversion_factor=2),
                {},
                {("ITEM-1", "SII-1"): frappe._dict(qty=0.3, stock_qty=0.6)},
            )
        doc.get("items")[0].set("stock_qty", -1.81)
        with (
            patch.object(workflow, "get_field_precision", return_value=2),
            patch.object(workflow.erpnext, "get_company_currency", return_value="THB"),
            patch.object(workflow.frappe, "get_meta") as get_meta,
            patch.object(native_returns, "get_field_precision", return_value=2),
            self.assertRaises(frappe.ValidationError),
        ):
            get_meta.return_value.get_field.return_value = object()
            workflow._validate_cumulative_return_quantity(doc, source, returned)

    def test_bundle_entry_identity_and_quantity_are_bound_to_credit_note_digest(self) -> None:
        doc = self._doc(items=[{"item_code": "SERIAL-ITEM", "serial_and_batch_bundle": "SABB-1"}])
        source = self._original()
        source_items = [frappe._dict(name="SII-1", item_code="SERIAL-ITEM", serial_and_batch_bundle="SABB-0")]
        masters = {
            "Serial and Batch Bundle:SABB-1": {"name": "SABB-1", "docstatus": 0},
            "Serial and Batch Entry:SBE-1": {
                "name": "SBE-1",
                "parent": "SABB-1",
                "serial_no": "SN-1",
                "qty": 1.0,
            },
        }
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(workflow.frappe.db, "get_value", return_value=source),
        ):
            digest = workflow.critical_payload_digest(doc, source, source_items, masters)
            masters["Serial and Batch Entry:SBE-1"]["serial_no"] = "SN-2"
            self.assertNotEqual(digest, workflow.critical_payload_digest(doc, source, source_items, masters))

    def test_unsealed_native_posting_paths_fail_closed(self) -> None:
        for field, value in (
            ("is_pos", 1),
            ("allocate_advances_automatically", 1),
            ("advances", [{"reference_type": "Payment Entry", "reference_name": "PE-1"}]),
            ("payments", [{"mode_of_payment": "Bank", "amount": -10}]),
            ("redeem_loyalty_points", 1),
            ("tax_withholding_category", "TDS"),
            ("items", [{"item_code": "FA-1", "is_fixed_asset": 1, "asset": "ASSET-1"}]),
            ("items", [{"item_code": "BATCH-1", "batch_no": "BATCH-A"}]),
            ("items", [{"item_code": "SERIAL-1", "serial_and_batch_bundle": "SABB-1"}]),
        ):
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(frappe.ValidationError, "requires separate approval controls"),
            ):
                workflow._require_supported_return_posting_path(self._doc(**{field: value}))

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

    def test_cancel_authorization_uses_cancellation_roles(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        doc = self._doc(workflow_state=route.cancelled_state)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
        ):
            workflow.authorize_cancel_transition(doc)
        authorize.assert_called_once_with(
            doc, workflow.ROUTE, route.cancel_action, ("Sales Manager",), permission="cancel"
        )

    def test_submit_role_alone_cannot_cancel_credit_note(self) -> None:
        route = get_route(workflow.ROUTE)
        doc = self._doc(workflow_state=route.cancelled_state)
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(workflow, "get_route", return_value=route),
            patch.object(workflow.frappe.db, "get_value", return_value=route.submitted_state),
            patch.object(workflow, "resolve_user", return_value="accounts@example.com"),
            patch.object(workflow.frappe, "get_roles", return_value=list(route.execution_roles)),
            patch.object(workflow, "consume_approval_field_grant") as consume,
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_cancel(doc)
        consume.assert_not_called()

    def test_incomplete_cancellation_contract_fails_before_grant(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        doc = self._doc(workflow_state=route.cancelled_state)
        for missing in ("cancel_action", "cancelled_state", "cancel_roles"):
            incomplete = replace(route, **{missing: () if missing == "cancel_roles" else ""})
            for handler in (workflow.authorize_cancel_transition, workflow.validate_before_cancel):
                with (
                    self.subTest(missing=missing, handler=handler.__name__),
                    patch.object(workflow, "is_credit_note", return_value=True),
                    patch.object(workflow, "get_route", return_value=incomplete),
                    patch.object(workflow, "authorize_workflow_field_write") as authorize,
                    patch.object(workflow, "consume_approval_field_grant") as consume,
                    self.assertRaises(frappe.ValidationError),
                ):
                    handler(doc)
                authorize.assert_not_called()
                consume.assert_not_called()

    def test_ordinary_invoice_cancellation_remains_native(self) -> None:
        doc = self._doc(is_return=0, return_against=None)
        with (
            patch.object(workflow, "is_credit_note", return_value=False),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.authorize_cancel_transition(doc)
            workflow.validate_before_cancel(doc)
        authorize.assert_not_called()
        consume.assert_not_called()

    def test_execute_validation_leaves_grant_for_before_submit(self) -> None:
        route = workflow.get_route(workflow.ROUTE)
        previous = self._doc(workflow_state=route.approved_state)
        doc = self._doc(workflow_state=route.submitted_state, docstatus=1)
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
            patch.object(
                workflow,
                "_lock_and_read_return_rows",
                return_value=(self._original(), [], [], {}, {}),
            ),
            patch.object(workflow, "_require_target_projection_matches"),
            patch.object(workflow, "_validate_cumulative_return_quantity"),
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
            patch.object(
                workflow,
                "_lock_and_read_return_rows",
                return_value=(self._original(), [], [], {}, {}),
            ),
            patch.object(workflow, "_require_target_projection_matches"),
            patch.object(workflow, "_validate_cumulative_return_quantity"),
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
        with (
            patch.object(workflow, "is_credit_note", return_value=True),
            patch.object(
                workflow, "_lock_and_read_return_rows", return_value=(self._original(), [], [], {}, {})
            ) as lock_rows,
            patch.object(workflow, "_require_target_projection_matches") as projection_check,
            patch.object(workflow, "_validate_cumulative_return_quantity") as quantity_guard,
            patch.object(workflow.frappe.db, "get_value", return_value=persisted) as get_value,
            patch.object(workflow, "critical_payload_digest", return_value="digest"),
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
            patch.object(workflow, "require_distinct_actors"),
            patch.object(workflow.frappe, "get_roles", return_value=["Accounts Manager"]),
            patch.object(workflow, "require_permission"),
            patch.object(doc, "validate", create=True) as native_validate,
            patch.object(workflow, "consume_approval_field_grant") as consume,
            patch.dict(frappe.session, {"user": "executor@example.com"}),
        ):
            workflow.validate_before_submit(doc)
        self.assertEqual(get_value.call_args_list[0].args[:2], ("Sales Invoice", "CN-1"))
        lock_rows.assert_called_once_with(doc)
        projection_check.assert_called_once_with(doc, {})
        quantity_guard.assert_called_once_with(doc, [], [])
        native_validate.assert_called_once_with()
        consume.assert_called_once_with(
            doc,
            workflow.ROUTE,
            workflow.get_route(workflow.ROUTE).execute_action,
        )
