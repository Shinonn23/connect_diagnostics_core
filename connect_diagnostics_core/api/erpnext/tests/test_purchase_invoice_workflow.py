# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import purchase_invoice_workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestPurchaseInvoiceWorkflow(UnitTestCase):
    def _doc(self) -> Document:
        return frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "name": "PI-TEST",
                "owner": "maker@example.com",
                "workflow_state": purchase_invoice_workflow.SUBMITTED_STATE,
                "company": "_Test Company",
                "supplier": "_Test Supplier",
                "credit_to": "Creditors - _TC",
                "items": [
                    {
                        "purchase_order": "PO-1",
                        "po_detail": "POI-1",
                        "purchase_receipt": "PR-1",
                        "pr_detail": "PRI-1",
                        "item_code": "ITEM-1",
                        "qty": 1,
                        "rate": 100,
                        "expense_account": "Expenses - _TC",
                    }
                ],
            }
        )

    def _first_item(self, doc: Document) -> Document:
        return doc.get("items")[0]

    def test_direct_submit_without_transition_marker_is_denied(self) -> None:
        with (
            patch.object(purchase_invoice_workflow, "_require_sources"),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.validate_before_submit(self._doc())

    def test_maker_capture_requires_canonical_owner_and_write_permission(self) -> None:
        doc = self._doc()
        doc.set("owner", "EMP-MAKER")

        def canonical(identity: str) -> str:
            return "maker@example.com" if identity == "EMP-MAKER" else identity

        with (
            patch.object(purchase_invoice_workflow, "require_permission") as permission,
            patch.object(purchase_invoice_workflow, "resolve_user", side_effect=canonical),
            patch.dict(purchase_invoice_workflow.frappe.session, {"user": "maker@example.com"}),
        ):
            purchase_invoice_workflow.capture_maker_snapshot(doc)
        permission.assert_called_once_with(doc, "write")
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")

        doc.set("approval_maker_user", None)
        with (
            patch.object(purchase_invoice_workflow, "require_permission"),
            patch.object(purchase_invoice_workflow, "resolve_user", side_effect=canonical),
            patch.dict(purchase_invoice_workflow.frappe.session, {"user": "other@example.com"}),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.capture_maker_snapshot(doc)
        self.assertFalse(doc.get("approval_maker_user"))

        with (
            patch.object(purchase_invoice_workflow, "require_permission", side_effect=frappe.PermissionError),
            patch.object(purchase_invoice_workflow, "resolve_user") as resolve,
            self.assertRaises(frappe.PermissionError),
        ):
            purchase_invoice_workflow.capture_maker_snapshot(doc)
        resolve.assert_not_called()

        doc.set("owner", "")
        with (
            patch.object(purchase_invoice_workflow, "require_permission"),
            patch.object(purchase_invoice_workflow, "resolve_user", wraps=approval_controls.resolve_user),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.capture_maker_snapshot(doc)
        self.assertFalse(doc.get("approval_maker_user"))

    def test_paid_invoice_is_denied(self) -> None:
        doc = self._doc()
        doc.set("is_paid", 1)
        with self.assertRaises(frappe.ValidationError):
            purchase_invoice_workflow.authorize_submit_execution(doc)

    def test_digest_binds_all_posting_values_and_children(self) -> None:
        mutations = (
            ("credit_to", "Other Creditors - _TC"),
            ("cash_bank_account", "Bank - _TC"),
            ("paid_amount", 25),
            ("write_off_amount", 5),
            ("taxes_and_charges_added", 7),
            ("base_rounding_adjustment", 0.5),
            ("taxes", [{"account_head": "VAT - _TC", "tax_amount": 7}]),
            ("payment_schedule", [{"due_date": "2026-10-01", "payment_amount": 100}]),
            ("advances", [{"reference_name": "PE-1", "allocated_amount": 20}]),
        )
        for fieldname, value in mutations:
            doc = self._doc()
            baseline = purchase_invoice_workflow.get_approval_digest(doc)
            doc.set(fieldname, value)
            self.assertNotEqual(
                baseline,
                purchase_invoice_workflow.get_approval_digest(doc),
                fieldname,
            )

        for fieldname, value in (
            ("expense_account", "Other Expense - _TC"),
            ("deferred_expense_account", "Deferred - _TC"),
            ("net_amount", 90),
            ("department", "_Test Department"),
        ):
            doc = self._doc()
            baseline = purchase_invoice_workflow.get_approval_digest(doc)
            self._first_item(doc).set(fieldname, value)
            self.assertNotEqual(
                baseline,
                purchase_invoice_workflow.get_approval_digest(doc),
                fieldname,
            )

    def test_digest_ignores_only_transition_and_snapshot_values(self) -> None:
        doc = self._doc()
        baseline = purchase_invoice_workflow.get_approval_digest(doc)
        for fieldname, value in (
            ("workflow_state", "Purchase Invoice Approved"),
            ("approval_critical_digest", "digest"),
            ("approval_reviewer_user", "reviewer@example.com"),
            ("checked_signature", "data:image/png;base64,test"),
        ):
            doc.set(fieldname, value)
        self.assertEqual(baseline, purchase_invoice_workflow.get_approval_digest(doc))

    def test_digest_ignores_only_system_managed_posting_time(self) -> None:
        doc = self._doc()
        doc.set("set_posting_time", 0)
        doc.set("posting_time", "12:00:00")
        baseline = purchase_invoice_workflow.get_approval_digest(doc)
        doc.set("posting_time", "12:00:01")
        self.assertEqual(baseline, purchase_invoice_workflow.get_approval_digest(doc))

        doc.set("set_posting_time", 1)
        baseline = purchase_invoice_workflow.get_approval_digest(doc)
        doc.set("posting_time", "12:00:02")
        self.assertNotEqual(baseline, purchase_invoice_workflow.get_approval_digest(doc))

    def test_digest_normalizes_dates_and_ignores_submit_generated_remarks(self) -> None:
        doc = self._doc()
        doc.set("posting_date", date(2026, 9, 23))
        baseline = purchase_invoice_workflow.get_approval_digest(doc)
        doc.set("posting_date", "2026-09-23")
        doc.set("remarks", "Against Supplier Invoice TEST-1")
        self.assertEqual(baseline, purchase_invoice_workflow.get_approval_digest(doc))

        doc.set("posting_date", "2026-09-24")
        self.assertNotEqual(baseline, purchase_invoice_workflow.get_approval_digest(doc))

    def test_source_policy_requires_receipt_for_goods_even_with_supplier_bypass(self) -> None:
        doc = self._doc()
        self._first_item(doc).set("purchase_receipt", None)
        self._first_item(doc).set("pr_detail", None)
        doc.set("supplier", "Supplier with native Receipt bypass")
        with (
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_values",
                return_value=[frappe._dict(name="ITEM-1", is_stock_item=1, is_fixed_asset=0)],
            ),
            self.assertRaisesRegex(frappe.ValidationError, "require a Purchase Receipt"),
        ):
            purchase_invoice_workflow._require_sources(doc)

    def test_service_without_receipt_keeps_exact_purchase_order_item(self) -> None:
        doc = self._doc()
        row = self._first_item(doc)
        row.set("purchase_receipt", None)
        row.set("pr_detail", None)
        item = frappe._dict(name="ITEM-1", is_stock_item=0, is_fixed_asset=0)
        po_child = frappe._dict(name="POI-1", parent="PO-1", item_code="ITEM-1")
        po = Document({"doctype": "Purchase Order", "name": "PO-1", "items": [dict(po_child)]})

        def values(doctype: str, **kwargs: object) -> list[frappe._dict]:
            return [item] if doctype == "Item" else [po_child]

        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values) as reads,
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_value",
                return_value=frappe._dict(name="PO-1", docstatus=1),
            ),
            patch.object(purchase_invoice_workflow.frappe, "get_doc", return_value=po),
        ):
            purchase_invoice_workflow._require_sources(doc)
        self.assertEqual(reads.call_args_list[0].args[0], "Item")
        self.assertTrue(
            all(call.kwargs["for_update"] and not call.kwargs["wait"] for call in reads.call_args_list)
        )

        row.set("po_detail", "POI-OTHER")
        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values),
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_value",
                return_value=frappe._dict(name="PO-1", docstatus=1),
            ),
            patch.object(purchase_invoice_workflow.frappe, "get_doc", return_value=po),
            self.assertRaisesRegex(frappe.ValidationError, "selected order"),
        ):
            purchase_invoice_workflow._require_sources(doc)

        # A real row belonging to another order is no better than an unknown row.
        row.set("po_detail", "POI-1")
        po_child.parent = "PO-OTHER"
        po.get("items")[0].parent = "PO-OTHER"
        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values),
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_value",
                return_value=frappe._dict(name="PO-1", docstatus=1),
            ),
            patch.object(purchase_invoice_workflow.frappe, "get_doc", return_value=po),
            self.assertRaisesRegex(frappe.ValidationError, "selected order"),
        ):
            purchase_invoice_workflow._require_sources(doc)

    def test_optional_service_receipt_must_match_same_po_item(self) -> None:
        doc = self._doc()
        item = frappe._dict(name="ITEM-1", is_stock_item=0, is_fixed_asset=0)
        po_child = frappe._dict(name="POI-1", parent="PO-1", item_code="ITEM-1")
        pr_child = frappe._dict(
            name="PRI-1",
            parent="PR-1",
            item_code="ITEM-1",
            purchase_order="PO-OTHER",
            purchase_order_item="POI-1",
        )
        sources = {
            "Purchase Order": Document(
                {"doctype": "Purchase Order", "name": "PO-1", "items": [dict(po_child)]}
            ),
            "Purchase Receipt": Document(
                {"doctype": "Purchase Receipt", "name": "PR-1", "items": [dict(pr_child)]}
            ),
        }

        def values(doctype: str, **kwargs: object) -> list[frappe._dict]:
            return {"Item": [item], "Purchase Order Item": [po_child], "Purchase Receipt Item": [pr_child]}[
                doctype
            ]

        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values),
            patch.object(
                purchase_invoice_workflow.frappe.db, "get_value", return_value=frappe._dict(docstatus=1)
            ),
            patch.object(
                purchase_invoice_workflow.frappe,
                "get_doc",
                side_effect=lambda doctype, _name: sources[doctype],
            ),
            self.assertRaisesRegex(frappe.ValidationError, "must match"),
        ):
            purchase_invoice_workflow._require_sources(doc)
        pr_child.parent = "PR-OTHER"
        sources["Purchase Receipt"].get("items")[0].parent = "PR-OTHER"
        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values),
            patch.object(
                purchase_invoice_workflow.frappe.db, "get_value", return_value=frappe._dict(docstatus=1)
            ),
            patch.object(
                purchase_invoice_workflow.frappe,
                "get_doc",
                side_effect=lambda doctype, _name: sources[doctype],
            ),
            self.assertRaisesRegex(frappe.ValidationError, "must match"),
        ):
            purchase_invoice_workflow._require_sources(doc)
        pr_child.parent = "PR-1"
        sources["Purchase Receipt"].get("items")[0].parent = "PR-1"
        pr_child.purchase_order = "PO-1"
        sources["Purchase Receipt"].get("items")[0].purchase_order = "PO-1"
        with (
            patch.object(purchase_invoice_workflow.frappe.db, "get_values", side_effect=values),
            patch.object(
                purchase_invoice_workflow.frappe.db, "get_value", return_value=frappe._dict(docstatus=1)
            ),
            patch.object(
                purchase_invoice_workflow.frappe,
                "get_doc",
                side_effect=lambda doctype, _name: sources[doctype],
            ),
        ):
            purchase_invoice_workflow._require_sources(doc)

    def test_draft_or_cancelled_source_fails_closed(self) -> None:
        doc = self._doc()
        self._first_item(doc).set("purchase_receipt", None)
        self._first_item(doc).set("pr_detail", None)
        with (
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_values",
                return_value=[frappe._dict(name="ITEM-1", is_stock_item=0, is_fixed_asset=0)],
            ),
            patch.object(
                purchase_invoice_workflow.frappe.db, "get_value", return_value=frappe._dict(docstatus=0)
            ),
            self.assertRaisesRegex(frappe.ValidationError, "remain submitted"),
        ):
            purchase_invoice_workflow._require_sources(doc)

    def test_item_current_read_conflict_cannot_reuse_stale_service_classification(self) -> None:
        doc = self._doc()
        self._first_item(doc).set("purchase_receipt", None)
        self._first_item(doc).set("pr_detail", None)
        with (
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_values",
                side_effect=frappe.QueryDeadlockError("Item changed"),
            ),
            self.assertRaisesRegex(frappe.ValidationError, "retry"),
        ):
            purchase_invoice_workflow._require_sources(doc)

    def test_source_verifier_cannot_be_maker(self) -> None:
        doc = self._doc()
        with (
            patch.object(purchase_invoice_workflow, "_require_sources"),
            patch(
                "connect_diagnostics_core.api.frappe.approval_controls.resolve_user",
                side_effect=lambda identity: identity,
            ),
            patch.dict(purchase_invoice_workflow.frappe.session, {"user": doc.owner}),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.capture_source_verification_snapshot(doc)

    def test_source_snapshot_requires_employee_signature(self) -> None:
        doc = self._doc()
        with (
            patch.object(purchase_invoice_workflow, "_require_sources"),
            patch.object(purchase_invoice_workflow, "require_distinct_actors"),
            patch("connect_diagnostics_core.api.erpnext.print_actions.capture_checked_action"),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.capture_source_verification_snapshot(doc)

    def test_source_snapshot_keeps_user_actor_separate_from_employee(self) -> None:
        doc = self._doc()

        def capture_employee_snapshot(target: Document) -> None:
            target.set("checked_by", "EMP-REVIEWER")
            target.set("checked_signature", "data:image/png;base64,reviewer")

        with (
            patch.object(purchase_invoice_workflow, "_require_sources"),
            patch(
                "connect_diagnostics_core.api.frappe.approval_controls.resolve_user",
                side_effect=lambda identity: identity,
            ),
            patch.object(
                purchase_invoice_workflow,
                "require_distinct_actors",
                wraps=purchase_invoice_workflow.require_distinct_actors,
            ) as distinct,
            patch.dict(
                purchase_invoice_workflow.frappe.session,
                {"user": "reviewer@example.com"},
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.print_actions.capture_checked_action",
                side_effect=capture_employee_snapshot,
            ),
        ):
            purchase_invoice_workflow.capture_source_verification_snapshot(doc)

        distinct.assert_called_once_with(doc.owner, "reviewer@example.com", ())
        self.assertEqual(doc.get("approval_reviewer_user"), "reviewer@example.com")
        self.assertEqual(doc.get("checked_by"), "EMP-REVIEWER")

    def test_new_blank_state_is_allowed_but_existing_blank_state_is_denied(self) -> None:
        doc = self._doc()
        doc.set("workflow_state", None)
        with patch.object(doc, "is_new", return_value=True):
            purchase_invoice_workflow.validate_workflow(doc)
        with (
            patch.object(doc, "is_new", return_value=False),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.validate_workflow(doc)

    def test_critical_mutation_after_review_is_denied(self) -> None:
        previous = self._doc()
        previous.set("workflow_state", "Purchase Invoice Pending Accounting Approval")
        previous.set("approval_critical_digest", purchase_invoice_workflow.get_approval_digest(previous))
        current = self._doc()
        current.set("workflow_state", "Purchase Invoice Pending Accounting Approval")
        current.set("approval_critical_digest", previous.get("approval_critical_digest"))
        current.set("credit_to", "Other Creditors - _TC")
        with (
            patch.object(current, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            purchase_invoice_workflow.validate_workflow(current)

    def test_cancel_requires_permission_marker_and_consumes_marker(self) -> None:
        doc = self._doc()
        doc.set("workflow_state", "Purchase Invoice Cancelled")
        with self.assertRaises(frappe.ValidationError):
            purchase_invoice_workflow.validate_before_cancel(doc)
        with (
            patch.object(purchase_invoice_workflow, "require_permission") as permission,
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_value",
                return_value=purchase_invoice_workflow.SUBMITTED_STATE,
            ),
            patch.dict(
                purchase_invoice_workflow.frappe.flags,
                {
                    "purchase_invoice_cancel_execution": {
                        "doctype": doc.doctype,
                        "name": doc.name,
                    }
                },
            ),
        ):
            purchase_invoice_workflow.validate_before_cancel(doc)
        permission.assert_called_once_with(doc, "cancel")
        self.assertIsNone(
            getattr(purchase_invoice_workflow.frappe.flags, "purchase_invoice_cancel_execution", None)
        )

    def test_submit_rechecks_sources_and_current_persisted_approval(self) -> None:
        doc = self._doc()
        digest = purchase_invoice_workflow.get_approval_digest(doc)
        with (
            patch.object(purchase_invoice_workflow, "_require_sources") as sources,
            patch.object(purchase_invoice_workflow, "require_permission"),
            patch.object(purchase_invoice_workflow, "require_distinct_actors"),
            patch.object(
                purchase_invoice_workflow.frappe.db,
                "get_value",
                return_value={
                    "workflow_state": purchase_invoice_workflow.APPROVED_STATE,
                    "approval_critical_digest": digest,
                    "approval_reviewer_user": "reviewer@example.com",
                    "approval_authorized_user": "approver@example.com",
                    "checked_signature": "checked",
                    "authorized_signature": "authorized",
                },
            ),
            patch.dict(
                purchase_invoice_workflow.frappe.flags,
                {
                    "purchase_invoice_execution": {
                        "doctype": "Purchase Invoice",
                        "name": "PI-TEST",
                    }
                },
            ),
        ):
            purchase_invoice_workflow.validate_before_submit(doc)
        sources.assert_called_once_with(doc)
