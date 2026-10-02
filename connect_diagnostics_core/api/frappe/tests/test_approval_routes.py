# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe.approval_routes import APPROVAL_ROUTES, get_route


class TestApprovalRoutes(UnitTestCase):
    def test_approved_actor_matrix_is_exact(self) -> None:
        expected = {
            "stock_entry_material_transfer": (
                "Stock Entry",
                "Stock User",
                "Stock Manager",
                "C-Level Approver",
                "Stock Manager",
            ),
            "stock_reconciliation": (
                "Stock Reconciliation",
                "Stock User",
                "Stock Manager",
                "Accounts Manager",
                "Stock Manager",
            ),
            "asset_movement": (
                "Asset Movement",
                "Stock User",
                "Stock Manager",
                "C-Level Approver",
                "Stock Manager",
            ),
            "manual_journal_entry": (
                "Journal Entry",
                "Accounts User",
                "Accounts Manager",
                "C-Level Approver",
                "Accounts Manager",
            ),
            "sales_order_credit": (
                "Sales Order",
                "Sales User",
                "Sales Manager",
                "Accounts Manager",
                "Sales Manager",
            ),
            "purchase_order": (
                "Purchase Order",
                "Purchase User",
                "Purchase Manager",
                "C-Level Approver",
                "Purchase Manager",
            ),
            "purchase_invoice": (
                "Purchase Invoice",
                "Accounts User",
                "Purchase Manager",
                "Accounts Manager",
                "Accounts Manager",
            ),
            "payment_entry": (
                "Payment Entry",
                "Accounts User",
                "Accounts Manager",
                "C-Level Approver",
                "Accounts Manager",
            ),
            "payroll_entry": ("Payroll Entry", "HR User", "HR Manager", "Accounts Manager", "HR Manager"),
        }
        actual = {
            route.key: (
                route.doctype,
                route.maker_roles[0],
                route.reviewer_roles[0],
                route.final_approver_roles[0],
                route.execution_roles[0],
            )
            for route in APPROVAL_ROUTES
            if route.key != "sales_invoice_credit_note"
        }
        self.assertEqual(actual, expected)
        credit_note = get_route("sales_invoice_credit_note")
        self.assertEqual(credit_note.maker_roles, ("Sales User", "Accounts User"))

    def test_actions_states_and_scopes_are_explicit(self) -> None:
        for route in APPROVAL_ROUTES:
            with self.subTest(route=route.key):
                self.assertTrue(route.send_action.startswith(("Send ", "Submit ")))
                self.assertTrue(route.resubmit_action.startswith("Resubmit "))
                self.assertEqual(route.protected_actions, (route.review_action, route.approve_action))
                self.assertNotEqual(route.pending_review_state, route.reviewed_state)
                self.assertNotEqual(route.reviewed_state, route.approved_state)
                self.assertTrue(route.scope_key)
                self.assertTrue(route.requires_distinct_actors)

        self.assertIn("ordinary Sales Invoice", get_route("sales_invoice_credit_note").excluded_scope)
        self.assertIn("ERPNext-generated Journal Entry", get_route("manual_journal_entry").excluded_scope)

        credit_note = get_route("sales_invoice_credit_note")
        self.assertEqual(credit_note.draft_state, "Sales Invoice Draft")
        self.assertEqual(credit_note.submitted_state, "Sales Invoice Submitted")

    def test_asset_custodian_status_does_not_grant_a_workflow_role(self) -> None:
        route = get_route("asset_movement")
        self.assertEqual(route.maker_roles, ("Stock User",))
        self.assertNotIn("Asset Custodian", route.maker_roles)

    def test_stock_transfer_uses_generic_entry_draft_only(self) -> None:
        route = get_route("stock_entry_material_transfer")
        self.assertEqual(route.draft_state, "Stock Entry Draft")
        self.assertEqual(route.pending_review_state, "Stock Transfer Pending Review")
        self.assertEqual(route.submitted_state, "Stock Transfer Submitted")

    def test_aligned_route_actions_and_states_are_exact(self) -> None:
        expected = {
            "asset_movement": {
                "resubmit_action": "Resubmit Asset Movement",
                "reviewed_state": "Asset Movement Pending Approval",
                "returned_state": "Asset Movement Draft",
            },
            "manual_journal_entry": {"execute_action": "Submit Journal Entry"},
            "sales_order_credit": {
                "approve_action": "Approve Sales Order",
                "reject_action": "Reject Sales Order",
                "excluded_scope": (),
            },
            "purchase_order": {
                "send_action": "Submit Purchase Order for Review",
                "resubmit_action": "Resubmit Purchase Order",
                "execute_action": "Post Purchase Order",
                "reviewed_state": "Purchase Order Pending Approval",
                "returned_state": "Purchase Order Draft",
            },
            "purchase_invoice": {
                "send_action": "Submit Purchase Invoice for Review",
                "resubmit_action": "Resubmit Purchase Invoice",
                "review_action": "Verify Purchase Invoice Source",
                "execute_action": "Post Purchase Invoice",
                "pending_review_state": "Purchase Invoice Pending Source Verification",
                "reviewed_state": "Purchase Invoice Pending Accounting Approval",
            },
            "payment_entry": {"execute_action": "Submit Payment Entry"},
        }
        for key, fields in expected.items():
            route = get_route(key)
            with self.subTest(route=key):
                self.assertEqual({field: getattr(route, field) for field in fields}, fields)

    def test_unaffected_routes_keep_their_actions(self) -> None:
        expected = {
            "stock_entry_material_transfer": ("Send Stock Transfer for Review", "Submit Stock Transfer"),
            "stock_reconciliation": ("Send Stock Reconciliation for Review", "Post Stock Reconciliation"),
            "sales_invoice_credit_note": (
                "Send Sales Invoice Credit for Review",
                "Post Sales Invoice Credit",
            ),
            "payroll_entry": ("Send Payroll Entry for Review", "Submit Payroll Entry"),
        }
        for key, actions in expected.items():
            route = get_route(key)
            with self.subTest(route=key):
                self.assertEqual((route.send_action, route.execute_action), actions)

    def test_route_lookup_is_strict(self) -> None:
        with self.assertRaises(KeyError):
            get_route("material_request")

    def test_credit_cancellation_has_its_own_explicit_actor_contract(self) -> None:
        route = get_route("sales_invoice_credit_note")
        self.assertEqual(route.cancel_action, "Cancel Sales Invoice Credit")
        self.assertEqual(route.cancelled_state, "Sales Invoice Cancelled")
        self.assertEqual(route.cancel_roles, ("Sales Manager",))
        self.assertEqual(route.execution_roles, ("Accounts Manager",))
        for other in APPROVAL_ROUTES:
            if other.key != route.key:
                self.assertEqual(
                    (other.cancel_action, other.cancelled_state, other.cancel_roles), ("", "", ())
                )
