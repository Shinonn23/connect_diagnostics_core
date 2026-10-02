# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_order_workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestSalesOrderWorkflow(UnitTestCase):
    def test_digest_changes_when_item_rate_changes(self) -> None:
        first = Document(
            {
                "doctype": "Sales Order",
                "customer": "CUST-1",
                "items": [{"item_code": "ITEM-1", "qty": 1, "rate": 10}],
            }
        )
        second = Document(
            {
                "doctype": "Sales Order",
                "customer": "CUST-1",
                "items": [{"item_code": "ITEM-1", "qty": 1, "rate": 11}],
            }
        )
        self.assertNotEqual(
            sales_order_workflow.approval_digest(first), sales_order_workflow.approval_digest(second)
        )

    def test_digest_changes_for_unknown_child_field(self) -> None:
        class Meta:
            def get_valid_columns(self):
                return ["items"]

        class Fake:
            meta = Meta()

            def __init__(self, value):
                self.value = value

            def get(self, fieldname):
                return self.value if fieldname == "items" else None

        first = Fake([{"custom_risk": "A"}])
        second = Fake([{"custom_risk": "B"}])
        self.assertTrue(
            sales_order_workflow._disallowed_changed(cast(Document, second), cast(Document, first))
        )

    def test_normalized_route_has_no_demo_gate(self) -> None:
        self.assertFalse(hasattr(sales_order_workflow, "_enabled"))
        self.assertEqual(sales_order_workflow.APPROVAL_REVISION, "sales-order-native-v1")

    def test_final_approval_rejects_policy_change_after_review(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "workflow_state": "Sales Order Approved",
                "approval_digest": "review-digest",
                "checked_signature": "checked",
            }
        )
        with (
            patch.object(sales_order_workflow, "approval_digest", return_value="changed-policy"),
        ):
            with self.assertRaises(Exception):
                sales_order_workflow.capture_sales_order_final_approval(doc)

    def test_signed_review_and_final_approval_keep_distinct_actors(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "workflow_state": "Sales Order Reviewed",
                "approval_maker_user": "maker@example.com",
                "approval_digest": "digest",
                "checked_by": "EMP-REVIEWER",
                "checked_at": "2026-09-19 10:00:00",
                "checked_signature": "reviewer-signed",
                "authorized_by": "EMP-APPROVER",
                "authorized_at": "2026-09-19 11:00:00",
                "authorized_signature": "approver-signed",
            }
        )
        with (
            patch.object(sales_order_workflow, "approval_digest", return_value="digest"),
            patch.object(sales_order_workflow, "get_party_account", return_value="AR - CO"),
            patch.object(
                sales_order_workflow,
                "_employee_signature",
                side_effect=[
                    ("EMP-REVIEWER", "reviewer-signed"),
                    ("EMP-APPROVER", "approver-signed"),
                ],
            ),
        ):
            with patch.object(sales_order_workflow.frappe, "session", user="reviewer@example.com"):
                sales_order_workflow.capture_sales_order_review(doc)
            doc.set("workflow_state", "Sales Order Approved")
            with patch.object(sales_order_workflow.frappe, "session", user="approver@example.com"):
                sales_order_workflow.capture_sales_order_final_approval(doc)
        self.assertEqual(doc.get("approval_reviewer_user"), "reviewer@example.com")
        self.assertEqual(doc.get("approval_approver_user"), "approver@example.com")
        self.assertEqual(doc.get("billing_receivable_account"), "AR - CO")

    def test_finance_cannot_sign_unresolved_item_account(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "workflow_state": "Sales Order Approved",
                "approval_digest": "digest",
                "checked_signature": "reviewed",
                "authorized_by": "EMP-FINANCE",
                "authorized_at": "2026-10-01 10:00:00",
                "authorized_signature": "signed",
                "items": [{"item_code": "ITEM", "income_account": "Income - CO"}],
            }
        )
        with (
            patch.object(sales_order_workflow, "approval_digest", return_value="digest"),
            patch.object(sales_order_workflow, "_employee_signature", return_value=("EMP-FINANCE", "signed")),
            patch.object(sales_order_workflow.frappe, "session", user="finance@example.invalid"),
            self.assertRaises(frappe.ValidationError),
        ):
            sales_order_workflow.capture_sales_order_final_approval(doc)

    def test_critical_mutation_after_review_requires_return(self) -> None:
        previous = Document(
            {"doctype": "Sales Order", "workflow_state": "Sales Order Reviewed", "items": [{"rate": 10}]}
        )
        doc = Document(
            {"doctype": "Sales Order", "workflow_state": "Sales Order Reviewed", "items": [{"rate": 11}]}
        )
        with (
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(sales_order_workflow, "_credit_inputs", return_value={}),
            self.assertRaises(Exception),
        ):
            sales_order_workflow.validate_sales_order(doc)

    def test_payment_schedule_is_part_of_approval_digest(self) -> None:
        first = Document(
            {
                "doctype": "Sales Order",
                "customer": "CUST-1",
                "payment_schedule": [{"invoice_portion": 100, "due_date": "2026-01-01"}],
            }
        )
        second = Document(
            {
                "doctype": "Sales Order",
                "customer": "CUST-1",
                "payment_schedule": [{"invoice_portion": 100, "due_date": "2026-02-01"}],
            }
        )
        with patch.object(sales_order_workflow, "_credit_inputs", return_value={}):
            self.assertNotEqual(
                sales_order_workflow.approval_digest(first), sales_order_workflow.approval_digest(second)
            )

    def test_digest_includes_item_business_and_custom_fields(self) -> None:
        base = {
            "doctype": "Sales Order",
            "customer": "CUST-1",
            "items": [
                {
                    "item_code": "I",
                    "qty": 1,
                    "project": "P",
                    "cost_center": "CC",
                    "income_account": "A",
                    "stock_uom": "Nos",
                    "custom_risk": "low",
                }
            ],
        }
        changed = {
            "doctype": "Sales Order",
            "customer": "CUST-1",
            "items": [{**base["items"][0], "project": "P-2"}],
        }
        with patch.object(sales_order_workflow, "_credit_inputs", return_value={}):
            first = sales_order_workflow.approval_payload(Document(base))["items"]
            second = sales_order_workflow.approval_payload(Document(changed))["items"]
            self.assertNotEqual(first, second)

    def test_submit_guard_recomputes_current_payload(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "approval_digest": "approved-digest",
            }
        )
        persisted = {
            "docstatus": 0,
            "workflow_state": "Sales Order Approved",
            "approval_digest": "approved-digest",
        }
        sales_order_workflow.frappe.flags.sales_order_submission = {
            "doctype": "Sales Order",
            "name": "SO-1",
            "approval_revision": sales_order_workflow.APPROVAL_REVISION,
            "approval_digest": "approved-digest",
            "action": "Post Sales Order",
            "actor": "Administrator",
        }
        with (
            patch.object(sales_order_workflow, "approval_digest", return_value="changed-current-payload"),
            patch.object(sales_order_workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(sales_order_workflow.frappe, "session", user="Administrator"),
            patch.object(sales_order_workflow, "require_interactive_user", return_value="Administrator"),
        ):
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_submit(doc)

    def test_sales_manager_executes_after_distinct_accounts_approval(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "workflow_state": "Sales Order Approved",
                "company": "_Test Company",
                "customer": "_Test Customer",
                "approval_revision": sales_order_workflow.APPROVAL_REVISION,
                "approval_digest": "digest",
                "approval_maker_user": "maker@example.com",
                "approval_reviewer_user": "manager@example.com",
                "checked_signature": "review-signature",
                "authorized_by": "EMP-APPROVER",
                "authorized_at": "2026-10-02 10:00:00",
                "authorized_signature": "approve-signature",
            }
        )
        with (
            patch.object(sales_order_workflow, "approval_digest", return_value="digest"),
            patch.object(sales_order_workflow, "billing_dimension_fields", return_value=()),
            patch.object(sales_order_workflow, "billing_authority_digest", return_value="billing-seal"),
            patch.object(sales_order_workflow, "get_party_account", return_value="AR - CO"),
            patch.object(
                sales_order_workflow,
                "_employee_signature",
                return_value=("EMP-APPROVER", "approve-signature"),
            ),
            patch.object(sales_order_workflow.frappe, "session", user="approver@example.com"),
        ):
            sales_order_workflow.capture_sales_order_final_approval(doc)

        doc.set("workflow_state", "Sales Order Submitted")
        persisted = {"workflow_state": "Sales Order Approved", "docstatus": 0}
        persisted.update(
            {
                field: doc.get(field)
                for field in (
                    "approval_revision",
                    "approval_digest",
                    "approval_maker_user",
                    "approval_maker_at",
                    "approval_reviewer_user",
                    "approval_reviewer_at",
                    "approval_approver_user",
                    "approval_approver_at",
                    "checked_by",
                    "checked_at",
                    "checked_signature",
                    "authorized_by",
                    "authorized_at",
                    "authorized_signature",
                    "billing_receivable_account",
                    "billing_authority_revision",
                    "billing_authority_digest",
                    "billing_authorized_by",
                    "billing_authorized_at",
                    "billing_authorized_signature",
                    "billing_authority_source_state",
                )
            }
        )
        with (
            patch.object(sales_order_workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(sales_order_workflow, "approval_digest", return_value="digest"),
            patch.object(sales_order_workflow, "billing_authority_digest", return_value="billing-seal"),
            patch.object(
                sales_order_workflow, "require_interactive_user", return_value="manager@example.com"
            ) as actor,
            patch.object(sales_order_workflow.frappe, "session", user="manager@example.com"),
        ):
            sales_order_workflow.authorize_sales_order_submission(doc)
            self.assertEqual(doc.get("approval_approver_user"), "approver@example.com")
            sales_order_workflow.validate_sales_order_before_submit(doc)
            actor.assert_any_call(doc, ("Sales Manager",), "submit")
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_submit(doc)

    def test_submission_authorization_rejects_wrong_persisted_status(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "workflow_state": "Sales Order Submitted",
                "approval_maker_user": "maker",
                "approval_reviewer_user": "reviewer",
                "approval_approver_user": "approver",
            }
        )
        with (
            patch.object(
                sales_order_workflow.frappe.db,
                "get_value",
                return_value={"workflow_state": "Sales Order Approved", "docstatus": 1},
            ),
            patch.object(sales_order_workflow, "require_interactive_user") as actor,
            self.assertRaises(Exception),
        ):
            sales_order_workflow.authorize_sales_order_submission(doc)
        actor.assert_not_called()

    def test_submission_requires_active_scoped_sales_manager(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "workflow_state": "Sales Order Submitted",
                "approval_maker_user": "maker",
                "approval_reviewer_user": "reviewer",
                "approval_approver_user": "approver",
            }
        )
        persisted = {"workflow_state": "Sales Order Approved", "docstatus": 0}
        for user, roles, enabled, permission in (
            ("approver@example.com", ["Accounts Manager"], True, True),
            ("maker@example.com", ["Sales User"], True, True),
            ("outsider@example.com", ["Accounts User"], True, True),
            ("manager@example.com", ["Sales Manager"], False, True),
            ("manager@example.com", ["Sales Manager"], True, False),
        ):
            with self.subTest(user=user, roles=roles, enabled=enabled, permission=permission):
                with (
                    patch.object(sales_order_workflow.frappe.db, "get_value", return_value=persisted),
                    patch.object(sales_order_workflow.frappe, "session", user=user),
                    patch.object(sales_order_workflow.frappe.local, "request", object(), create=True),
                    patch.object(sales_order_workflow.frappe, "get_roles", return_value=roles),
                    patch.object(
                        approval_controls,
                        "require_permission",
                        side_effect=None if permission else frappe.PermissionError("denied"),
                    ),
                    patch.object(
                        approval_controls,
                        "resolve_user",
                        side_effect=(lambda value: value) if enabled else frappe.ValidationError("disabled"),
                    ),
                    self.assertRaises((frappe.ValidationError, frappe.PermissionError)),
                ):
                    sales_order_workflow.authorize_sales_order_submission(doc)

    def test_credit_payload_contains_native_precedence_inputs(self) -> None:
        doc = Document({"doctype": "Sales Order", "customer": "CUST-1", "company": "COMP-1"})
        with (
            patch.object(sales_order_workflow, "get_credit_limit", return_value=120),
            patch.object(
                sales_order_workflow.frappe.db,
                "get_value",
                side_effect=[
                    {"credit_limit": 100, "bypass_credit_limit_check": 0},
                    "GROUP-1",
                    {"credit_limit": 200, "bypass_credit_limit_check": 1},
                    300,
                ],
            ),
            patch.object(sales_order_workflow.frappe.db, "get_single_value", return_value="C-Level Approver"),
        ):
            credit = sales_order_workflow._credit_inputs(doc)
        self.assertEqual(credit["effective_credit_limit"], 120)
        self.assertEqual(credit["customer_group"], "GROUP-1")
        self.assertEqual(credit["company_credit_limit"], 300)
        self.assertEqual(credit["credit_controller"], "C-Level Approver")

    def test_submission_marker_is_cleared_after_failure(self) -> None:
        with (
            patch.object(sales_order_workflow.frappe.db, "get_value", return_value=None),
            patch.object(sales_order_workflow.frappe, "throw", side_effect=Exception("blocked")),
        ):
            doc = Document({"doctype": "Sales Order", "name": "SO-1"})
            sales_order_workflow.frappe.flags.sales_order_submission = {"stale": True}
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_submit(doc)
            self.assertIsNone(getattr(sales_order_workflow.frappe.flags, "sales_order_submission", None))

    def test_direct_cancel_fails_closed_and_clears_marker(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "workflow_state": "Sales Order Cancelled",
            }
        )
        setattr(sales_order_workflow.frappe.flags, sales_order_workflow._CANCELLATION_FLAG, None)
        with patch.object(
            sales_order_workflow.frappe.db,
            "get_value",
            return_value={"workflow_state": "Sales Order Submitted", "docstatus": 1},
        ):
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_cancel(doc)
        self.assertIsNone(
            getattr(sales_order_workflow.frappe.flags, sales_order_workflow._CANCELLATION_FLAG, None)
        )

    def test_cancel_authorization_is_consumed_by_cancel_guard(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "workflow_state": "Sales Order Cancelled",
            }
        )
        persisted = {"workflow_state": "Sales Order Submitted", "docstatus": 1}
        with (
            patch.object(sales_order_workflow.frappe.db, "get_value", return_value=persisted) as get_value,
            patch.object(sales_order_workflow.frappe, "has_permission", return_value=True),
        ):
            sales_order_workflow.authorize_sales_order_cancellation(doc)
            sales_order_workflow.validate_sales_order_before_cancel(doc)
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_cancel(doc)
        self.assertEqual(get_value.call_args_list[0].kwargs, {"as_dict": True, "for_update": True})
        self.assertIsNone(
            getattr(sales_order_workflow.frappe.flags, sales_order_workflow._CANCELLATION_FLAG, None)
        )
