# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.model.workflow import is_transition_condition_satisfied
from frappe.tests import IntegrationTestCase
from frappe.tests.classes.context_managers import set_user

from connect_diagnostics_core.api.erpnext import payment_approval
from connect_diagnostics_core.setup import payment_approval as payment_approval_setup


class TestPaymentApproval(IntegrationTestCase):
    def test_outgoing_payment_cannot_submit_before_approval(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_paid_amount=1500,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    def test_approved_outgoing_payment_can_submit(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_paid_amount=1500,
        )

        payment_approval.validate_before_submit(payment_entry, "before_submit")

    def test_non_outgoing_payment_does_not_require_approval(self) -> None:
        for payment_type in ("Receive", "Internal Transfer"):
            with self.subTest(payment_type=payment_type):
                payment_entry = self._decision_document(
                    previous_state=payment_approval_setup.DRAFT_STATE,
                    next_state=payment_approval_setup.DRAFT_STATE,
                    base_paid_amount=1500,
                    payment_type=payment_type,
                )
                payment_approval.validate_before_submit(payment_entry, "before_submit")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.SECONDARY_APPROVER_ROLE],
    )
    def test_payment_approver_without_accounts_role_cannot_submit_non_outgoing(
        self, _mocked_get_roles: MagicMock
    ) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_paid_amount=1500,
            payment_type="Receive",
        )

        with set_user("secondary@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval.frappe, "get_roles", return_value=["Accounts User"])
    def test_accounts_user_can_submit_non_outgoing(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_paid_amount=1500,
            payment_type="Receive",
        )

        with set_user("accounts@example.com"):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval.frappe, "get_roles", return_value=[])
    def test_non_approver_non_outgoing_submit_keeps_standard_path(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_paid_amount=1500,
            payment_type="Receive",
        )

        with set_user("gateway@example.com"):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.SECONDARY_APPROVER_ROLE],
    )
    def test_ignore_permissions_non_outgoing_submit_keeps_standard_path(
        self, _mocked_get_roles: MagicMock
    ) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_paid_amount=1500,
            payment_type="Receive",
            ignore_permissions=True,
        )

        with set_user("gateway@example.com"):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    def test_payment_below_1500_routes_to_low_value_approval(self) -> None:
        next_states = self._maker_next_states("Pay", 1499.99)

        self.assertEqual(next_states, {payment_approval_setup.PENDING_LOW_VALUE_STATE})

    def test_payment_of_exactly_1500_routes_to_primary_approval(self) -> None:
        next_states = self._maker_next_states("Pay", 1500)

        self.assertEqual(next_states, {payment_approval_setup.PENDING_PRIMARY_STATE})

    def test_receive_routes_to_standard_submission(self) -> None:
        next_states = self._maker_next_states("Receive", 1500)

        self.assertEqual(next_states, {payment_approval_setup.SUBMITTED_STATE})

    def test_low_value_approval_is_hidden_when_amount_reaches_1500(self) -> None:
        roles = self._approval_roles_for_amount(
            payment_approval_setup.PENDING_LOW_VALUE_STATE,
            1500,
        )

        self.assertEqual(roles, set())

    def test_low_value_payment_cannot_be_approved_after_amount_increase(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_paid_amount=1500,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    def test_document_owner_cannot_approve_own_payment(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_paid_amount=1500,
            owner="owner@example.com",
        )

        with set_user("owner@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    def test_changed_owner_cannot_bypass_self_approval_on_submit(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_paid_amount=1500,
            owner="replacement@example.com",
            previous_owner="maker@example.com",
        )

        with set_user("maker@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval, "now_datetime")
    def test_entering_pending_state_sets_server_owned_deadline(self, mocked_now_datetime: MagicMock) -> None:
        now = datetime(2026, 7, 16, 12, 0, 0)
        mocked_now_datetime.return_value = now
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_paid_amount=1500,
            approval_due_at=now - timedelta(days=1),
        )

        payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

        cast(MagicMock, payment_entry.set).assert_called_once_with(
            payment_approval_setup.APPROVAL_DUE_AT_FIELD,
            now + timedelta(hours=24),
        )

    def test_pending_deadline_cannot_be_changed_to_force_escalation(self) -> None:
        now = datetime(2026, 7, 16, 12, 0, 0)
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.ESCALATED_PRIMARY_STATE,
            base_paid_amount=1500,
            approval_due_at=now - timedelta(minutes=1),
            previous_approval_due_at=now + timedelta(hours=1),
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    def test_rejected_payment_can_be_saved_before_revision(self) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.REJECTED_STATE,
            next_state=payment_approval_setup.REJECTED_STATE,
            base_paid_amount=1500,
        )

        payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.SECONDARY_APPROVER_ROLE],
    )
    def test_secondary_cannot_edit_before_escalation(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_paid_amount=1500,
        )

        with set_user("secondary@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.LOW_VALUE_APPROVER_ROLE],
    )
    def test_low_value_approver_cannot_edit_high_value_payment(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_paid_amount=1500,
        )

        with set_user("low-value@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    @patch.object(payment_approval.frappe, "get_roles", return_value=["Accounts User"])
    def test_maker_cannot_edit_payment_while_approval_is_pending(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_paid_amount=1500,
        )

        with set_user("accounts@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.PRIMARY_APPROVER_ROLE],
    )
    def test_primary_can_edit_primary_payment_while_approval_is_pending(
        self, _mocked_get_roles: MagicMock
    ) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_paid_amount=1500,
        )

        with set_user("primary@example.com"):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.SECONDARY_APPROVER_ROLE],
    )
    def test_approver_role_does_not_grant_general_draft_editing(self, _mocked_get_roles: MagicMock) -> None:
        payment_entry = self._decision_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_paid_amount=1500,
        )

        with set_user("secondary@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_approval_transition(payment_entry, "before_save")

    def test_cancellation_sets_cancelled_workflow_state(self) -> None:
        payment_entry = MagicMock()

        payment_approval.set_cancelled_workflow_state(payment_entry, "before_cancel")

        payment_entry.set.assert_called_once_with(
            payment_approval_setup.WORKFLOW_STATE_FIELD,
            payment_approval_setup.CANCELLED_STATE,
        )

    def test_active_outgoing_approval_cannot_be_discarded(self) -> None:
        payment_entry = MagicMock()
        payment_entry.get.side_effect = lambda fieldname, default=None: {
            "payment_type": "Pay",
            payment_approval_setup.WORKFLOW_STATE_FIELD: (payment_approval_setup.PENDING_PRIMARY_STATE),
        }.get(fieldname, default)

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_before_discard(payment_entry, "before_discard")

    def test_non_outgoing_payment_keeps_standard_discard_path(self) -> None:
        payment_entry = MagicMock()
        payment_entry.get.side_effect = lambda fieldname, default=None: {
            "payment_type": "Receive",
            payment_approval_setup.WORKFLOW_STATE_FIELD: payment_approval_setup.DRAFT_STATE,
        }.get(fieldname, default)

        payment_approval.validate_before_discard(payment_entry, "before_discard")

    def test_escalated_low_value_payment_keeps_original_approvers_and_adds_secondary(self) -> None:
        roles = self._approval_roles(payment_approval_setup.ESCALATED_LOW_VALUE_STATE)

        self.assertEqual(
            roles,
            {
                payment_approval_setup.LOW_VALUE_APPROVER_ROLE,
                payment_approval_setup.SECONDARY_APPROVER_ROLE,
            },
        )

    def test_escalated_primary_payment_keeps_primary_and_adds_secondary(self) -> None:
        roles = self._approval_roles(payment_approval_setup.ESCALATED_PRIMARY_STATE)

        self.assertEqual(
            roles,
            {
                payment_approval_setup.PRIMARY_APPROVER_ROLE,
                payment_approval_setup.SECONDARY_APPROVER_ROLE,
            },
        )

    @patch.object(payment_approval, "_delete_completed_workflow_actions")
    def test_revisiting_actionable_state_clears_completed_action(
        self, mocked_delete_actions: MagicMock
    ) -> None:
        payment_entry = MagicMock()
        payment_entry.get.side_effect = lambda fieldname, default=None: {
            "name": "PAY-TEST-0003",
            payment_approval_setup.WORKFLOW_STATE_FIELD: payment_approval_setup.PENDING_PRIMARY_STATE,
        }.get(fieldname, default)
        payment_entry.get_doc_before_save.return_value = frappe._dict(
            {
                payment_approval_setup.WORKFLOW_STATE_FIELD: payment_approval_setup.REJECTED_STATE,
            }
        )

        payment_approval.clear_completed_workflow_actions_for_next_state(payment_entry, "before_save")

        mocked_delete_actions.assert_called_once_with(
            "PAY-TEST-0003", payment_approval_setup.PENDING_PRIMARY_STATE
        )

    @patch.object(payment_approval, "_delete_completed_workflow_actions")
    @patch.object(payment_approval, "process_workflow_actions")
    @patch.object(payment_approval.frappe, "get_doc")
    @patch.object(payment_approval.frappe.db, "set_value")
    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval, "now_datetime")
    def test_due_payment_escalates_under_lock(
        self,
        mocked_now_datetime: MagicMock,
        mocked_get_value: MagicMock,
        mocked_set_value: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_process_actions: MagicMock,
        mocked_delete_actions: MagicMock,
    ) -> None:
        now = datetime(2026, 7, 16, 12, 0, 0)
        mocked_now_datetime.return_value = now
        mocked_get_value.return_value = frappe._dict(
            docstatus=0,
            payment_type="Pay",
            payment_approval_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            approval_due_at=now - timedelta(minutes=1),
        )
        payment_entry = MagicMock()
        mocked_get_doc.return_value = payment_entry

        result = payment_approval.escalate_payment_approval("PAY-TEST-0001")

        self.assertTrue(result)
        mocked_get_value.assert_any_call(
            payment_approval_setup.PAYMENT_ENTRY_DOCTYPE,
            "PAY-TEST-0001",
            [
                "docstatus",
                "payment_type",
                payment_approval_setup.WORKFLOW_STATE_FIELD,
                payment_approval_setup.APPROVAL_DUE_AT_FIELD,
            ],
            as_dict=True,
            for_update=True,
        )
        mocked_set_value.assert_any_call(
            payment_approval_setup.PAYMENT_ENTRY_DOCTYPE,
            "PAY-TEST-0001",
            payment_approval_setup.WORKFLOW_STATE_FIELD,
            payment_approval_setup.ESCALATED_PRIMARY_STATE,
            modified_by="Administrator",
        )
        mocked_delete_actions.assert_called_once_with(
            "PAY-TEST-0001", payment_approval_setup.ESCALATED_PRIMARY_STATE
        )
        mocked_process_actions.assert_called_once_with(payment_entry, "on_update")
        payment_entry.add_comment.assert_called_once()
        payment_entry.notify_update.assert_called_once_with()

    @patch.object(payment_approval, "process_workflow_actions")
    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval, "now_datetime")
    def test_payment_not_due_is_not_escalated(
        self,
        mocked_now_datetime: MagicMock,
        mocked_get_value: MagicMock,
        mocked_process_actions: MagicMock,
    ) -> None:
        now = datetime(2026, 7, 16, 12, 0, 0)
        mocked_now_datetime.return_value = now
        mocked_get_value.return_value = frappe._dict(
            docstatus=0,
            payment_type="Pay",
            payment_approval_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            approval_due_at=now + timedelta(minutes=1),
        )

        result = payment_approval.escalate_payment_approval("PAY-TEST-0002")

        self.assertFalse(result)
        mocked_process_actions.assert_not_called()

    def _approval_roles(self, state: str) -> set[str]:
        return {
            transition["allowed"]
            for transition in payment_approval_setup.WORKFLOW_TRANSITIONS
            if transition["state"] == state and transition["action"] == payment_approval_setup.APPROVE_ACTION
        }

    def _approval_roles_for_amount(self, state: str, base_paid_amount: float) -> set[str]:
        payment_entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": payment_approval_setup.PAYMENT_ENTRY_DOCTYPE,
                    "payment_type": "Pay",
                    "base_paid_amount": base_paid_amount,
                }
            ),
        )
        return {
            transition_values["allowed"]
            for transition_values in payment_approval_setup.WORKFLOW_TRANSITIONS
            if transition_values["state"] == state
            and transition_values["action"] == payment_approval_setup.APPROVE_ACTION
            and is_transition_condition_satisfied(
                frappe._dict(transition_values),
                payment_entry,
            )
        }

    def _maker_next_states(self, payment_type: str, base_paid_amount: float) -> set[str]:
        payment_entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": payment_approval_setup.PAYMENT_ENTRY_DOCTYPE,
                    "payment_type": payment_type,
                    "base_paid_amount": base_paid_amount,
                }
            ),
        )
        return {
            transition_values["next_state"]
            for transition_values in payment_approval_setup.WORKFLOW_TRANSITIONS
            if transition_values["state"] == payment_approval_setup.DRAFT_STATE
            and transition_values["allowed"] == "Accounts User"
            and is_transition_condition_satisfied(
                frappe._dict(transition_values),
                payment_entry,
            )
        }

    def _decision_document(
        self,
        *,
        previous_state: str,
        next_state: str,
        base_paid_amount: float,
        owner: str = "creator@example.com",
        previous_owner: str | None = None,
        payment_type: str = "Pay",
        approval_due_at: datetime | None = None,
        previous_approval_due_at: datetime | None = None,
        ignore_permissions: bool = False,
    ) -> Document:
        if previous_owner is None:
            previous_owner = owner
        payment_entry = MagicMock()
        payment_entry.flags.ignore_permissions = ignore_permissions
        payment_entry.get.side_effect = lambda fieldname, default=None: {
            "payment_type": payment_type,
            "base_paid_amount": base_paid_amount,
            "owner": owner,
            payment_approval_setup.APPROVAL_DUE_AT_FIELD: approval_due_at,
            payment_approval_setup.WORKFLOW_STATE_FIELD: next_state,
        }.get(fieldname, default)
        payment_entry.get_doc_before_save.return_value = frappe._dict(
            {
                "owner": previous_owner,
                payment_approval_setup.APPROVAL_DUE_AT_FIELD: previous_approval_due_at,
                payment_approval_setup.WORKFLOW_STATE_FIELD: previous_state,
            }
        )
        return cast(Document, payment_entry)
