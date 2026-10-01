# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

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
        workflows = {
            workflow["document_type"]: workflow
            for workflow in json.loads(
                (Path(__file__).resolve().parents[3] / "fixtures" / "workflow.json").read_text()
            )
        }
        for route in APPROVAL_ROUTES:
            with self.subTest(route=route.key):
                workflow = workflows[route.doctype]
                actions = {transition["action"] for transition in workflow["transitions"]}
                states = {state["state"] for state in workflow["states"]}
                self.assertTrue(
                    {
                        route.send_action,
                        route.resubmit_action,
                        route.review_action,
                        route.return_action,
                        route.approve_action,
                        route.reject_action,
                        route.execute_action,
                    }.issubset(actions)
                )
                self.assertTrue(
                    {
                        route.draft_state,
                        route.pending_review_state,
                        route.reviewed_state,
                        route.returned_state,
                        route.approved_state,
                        route.submitted_state,
                    }.issubset(states)
                )
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

    def test_route_lookup_is_strict(self) -> None:
        with self.assertRaises(KeyError):
            get_route("material_request")
