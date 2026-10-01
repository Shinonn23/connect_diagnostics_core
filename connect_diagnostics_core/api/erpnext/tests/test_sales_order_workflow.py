# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_order_workflow


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
        ):
            with self.assertRaises(Exception):
                sales_order_workflow.validate_sales_order_before_submit(doc)

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
            patch.object(sales_order_workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(sales_order_workflow.frappe, "has_permission", return_value=True),
        ):
            sales_order_workflow.authorize_sales_order_cancellation(doc)
            sales_order_workflow.validate_sales_order_before_cancel(doc)
        self.assertIsNone(
            getattr(sales_order_workflow.frappe.flags, sales_order_workflow._CANCELLATION_FLAG, None)
        )
