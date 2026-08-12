# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Structural tests for the code-managed Stock Count approval workflow."""

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import stock_count

_VALID_STYLES = {"Primary", "Info", "Success", "Warning", "Danger", "Inverse"}


class TestStockCountWorkflowSetup(UnitTestCase):
    def test_state_styles_are_supported_by_workflow_state(self) -> None:
        for style in stock_count.WORKFLOW_STATE_STYLES.values():
            self.assertIn(style, _VALID_STYLES)

    def test_every_transition_references_a_declared_state(self) -> None:
        declared_states = set(stock_count.WORKFLOW_STATE_STYLES)
        for transition in stock_count.WORKFLOW_TRANSITIONS:
            self.assertIn(transition["state"], declared_states)
            self.assertIn(transition["next_state"], declared_states)
            self.assertIn(transition["allowed"], {"Stock User", "Stock Manager", "Accounts Manager"})

    def test_every_transition_action_is_a_declared_action(self) -> None:
        for transition in stock_count.WORKFLOW_TRANSITIONS:
            self.assertIn(transition["action"], stock_count.WORKFLOW_ACTIONS)

    def test_monthly_approval_never_reaches_accounts_review(self) -> None:
        monthly_transitions = [
            t
            for t in stock_count.WORKFLOW_TRANSITIONS
            if t["state"] == stock_count.PENDING_STOCK_APPROVAL
            and t["action"] == "Approve"
            and t.get("condition") == f"doc.count_type != '{stock_count.YEARLY}'"
        ]
        self.assertEqual(len(monthly_transitions), 1)
        self.assertEqual(monthly_transitions[0]["next_state"], stock_count.APPROVED)

    def test_yearly_approval_routes_through_accounts_review(self) -> None:
        yearly_transitions = [
            t
            for t in stock_count.WORKFLOW_TRANSITIONS
            if t["state"] == stock_count.PENDING_STOCK_APPROVAL
            and t["action"] == "Approve"
            and t.get("condition") == f"doc.count_type == '{stock_count.YEARLY}'"
        ]
        self.assertEqual(len(yearly_transitions), 1)
        self.assertEqual(yearly_transitions[0]["next_state"], stock_count.PENDING_ACCOUNTS_APPROVAL)

    def test_only_accounts_manager_can_clear_accounts_review(self) -> None:
        approvals = [
            t
            for t in stock_count.WORKFLOW_TRANSITIONS
            if t["state"] == stock_count.PENDING_ACCOUNTS_APPROVAL and t["action"] == "Approve"
        ]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["allowed"], "Accounts Manager")
        self.assertEqual(approvals[0]["next_state"], stock_count.APPROVED)
