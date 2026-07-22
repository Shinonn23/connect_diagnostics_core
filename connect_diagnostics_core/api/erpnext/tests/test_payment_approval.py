# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.model.document import Document
from frappe.model.workflow import is_transition_condition_satisfied
from frappe.tests import UnitTestCase
from frappe.tests.classes.context_managers import set_user

from connect_diagnostics_core.api.erpnext import payment_approval
from connect_diagnostics_core.setup import payment_approval as payment_approval_setup


class WorkflowDocument(frappe._dict):
    def as_dict(self) -> dict[str, Any]:
        return self


class TestPaymentRequestApproval(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        rounding_patch = patch.object(
            frappe,
            "get_system_settings",
            return_value="Banker's Rounding (legacy)",
        )
        rounding_patch.start()
        self.addCleanup(rounding_patch.stop)

    def test_blank_limit_routes_outward_request_to_primary_approval(self) -> None:
        self.assertEqual(
            self._maker_next_states("Outward", 500, None),
            {payment_approval_setup.PENDING_PRIMARY_STATE},
        )

    def test_amount_below_positive_limit_routes_to_low_value_approval(self) -> None:
        self.assertEqual(
            self._maker_next_states("Outward", 999.99, 1000),
            {payment_approval_setup.PENDING_LOW_VALUE_STATE},
        )

    def test_amount_equal_to_limit_routes_to_primary_approval(self) -> None:
        self.assertEqual(
            self._maker_next_states("Outward", 1000, 1000),
            {payment_approval_setup.PENDING_PRIMARY_STATE},
        )

    def test_amount_above_limit_routes_to_primary_approval(self) -> None:
        self.assertEqual(
            self._maker_next_states("Outward", 1000.01, 1000),
            {payment_approval_setup.PENDING_PRIMARY_STATE},
        )

    def test_inward_request_routes_to_standard_submission(self) -> None:
        self.assertEqual(
            self._maker_next_states("Inward", 1000, 1500),
            {payment_approval_setup.SUBMITTED_STATE},
        )

    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval.frappe, "get_meta")
    @patch.object(payment_approval.frappe, "get_cached_value", return_value="THB")
    def test_company_currency_amount_uses_grand_total_without_conversion(
        self,
        _mocked_company_currency: MagicMock,
        mocked_get_meta: MagicMock,
        mocked_get_value: MagicMock,
    ) -> None:
        mocked_get_meta.return_value.has_field.side_effect = lambda _fieldname: True
        mocked_get_value.return_value = frappe._dict(
            company="Connect Diagnostics",
            currency="THB",
            conversion_rate=35,
        )
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_grand_total=0,
            grand_total=250,
            currency="THB",
        )

        result = payment_approval._calculate_base_grand_total(payment_request)

        self.assertEqual(result, 250)

    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval.frappe, "get_meta")
    @patch.object(payment_approval.frappe, "get_cached_value", return_value="THB")
    def test_foreign_currency_amount_uses_reference_conversion_rate(
        self,
        _mocked_company_currency: MagicMock,
        mocked_get_meta: MagicMock,
        mocked_get_value: MagicMock,
    ) -> None:
        mocked_get_meta.return_value.has_field.side_effect = lambda _fieldname: True
        mocked_get_value.return_value = frappe._dict(
            company="Connect Diagnostics",
            currency="USD",
            conversion_rate=35.5,
        )
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_grand_total=0,
            grand_total=100,
            currency="USD",
        )

        result = payment_approval._calculate_base_grand_total(payment_request)

        self.assertEqual(result, 3550)

    @patch.object(payment_approval, "now_datetime")
    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    @patch.object(payment_approval.frappe.db, "get_value", return_value=1000)
    def test_request_approval_snapshots_limit_and_deadline(
        self,
        _mocked_limit: MagicMock,
        _mocked_base_total: MagicMock,
        mocked_now_datetime: MagicMock,
    ) -> None:
        now = datetime(2026, 7, 19, 12, 0, 0)
        mocked_now_datetime.return_value = now
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_grand_total=500,
            payment_approval_limit=None,
        )

        payment_approval.validate_payment_request_transition(payment_request, "before_save")

        self.assertIn(
            call(payment_approval_setup.PAYMENT_APPROVAL_LIMIT_FIELD, 1000),
            cast(MagicMock, payment_request.set).call_args_list,
        )
        self.assertIn(
            call(payment_approval_setup.APPROVAL_DUE_AT_FIELD, now + timedelta(hours=24)),
            cast(MagicMock, payment_request.set).call_args_list,
        )

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_company_limit_change_does_not_change_pending_snapshot(
        self, _mocked_base_total: MagicMock
    ) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_grand_total=500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with patch.object(payment_approval.frappe.db, "get_value") as mocked_get_value:
            payment_approval.validate_payment_request_before_submit(payment_request, "before_submit")

        mocked_get_value.assert_not_called()

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=1500)
    def test_low_value_threshold_bypass_is_rejected(self, _mocked_base_total: MagicMock) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_grand_total=1500,
            previous_base_grand_total=1500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_before_submit(payment_request, "before_submit")

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_payment_approval_limit_tampering_is_rejected(self, _mocked_base_total: MagicMock) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_grand_total=500,
            payment_approval_limit=2000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_pending_deadline_tampering_is_rejected(self, _mocked_base_total: MagicMock) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_grand_total=500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at - timedelta(hours=1),
            previous_approval_due_at=due_at,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_pending_base_amount_tampering_is_rejected(self, _mocked_base_total: MagicMock) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_grand_total=750,
            previous_base_grand_total=500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_changed_creator_is_rejected(self, _mocked_base_total: MagicMock) -> None:
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_grand_total=500,
            owner="replacement@example.com",
            previous_owner="maker@example.com",
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=1500)
    def test_document_owner_cannot_approve_own_request(self, _mocked_base_total: MagicMock) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.APPROVED_STATE,
            base_grand_total=1500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
            owner="maker@example.com",
        )

        with set_user("maker@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_before_submit(payment_request, "before_submit")

    def test_inward_request_keeps_standard_submit_path(self) -> None:
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.SUBMITTED_STATE,
            base_grand_total=0,
            payment_request_type="Inward",
        )

        payment_approval.validate_payment_request_before_submit(payment_request, "before_submit")

    @patch.object(
        payment_approval.frappe, "get_roles", return_value=[payment_approval_setup.SECONDARY_APPROVER_ROLE]
    )
    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=1500)
    def test_secondary_cannot_edit_before_escalation(
        self,
        _mocked_base_total: MagicMock,
        _mocked_get_roles: MagicMock,
    ) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_grand_total=1500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with set_user("secondary@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(payment_approval.frappe, "get_roles", return_value=["Accounts User"])
    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_maker_cannot_edit_request_while_approval_is_pending(
        self,
        _mocked_base_total: MagicMock,
        _mocked_get_roles: MagicMock,
    ) -> None:
        due_at = datetime(2026, 7, 20, 12, 0, 0)
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            next_state=payment_approval_setup.PENDING_LOW_VALUE_STATE,
            base_grand_total=500,
            payment_approval_limit=1000,
            previous_payment_approval_limit=1000,
            approval_due_at=due_at,
            previous_approval_due_at=due_at,
        )

        with set_user("maker@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    @patch.object(
        payment_approval.frappe,
        "get_roles",
        return_value=[payment_approval_setup.PRIMARY_APPROVER_ROLE],
    )
    @patch.object(payment_approval, "_calculate_base_grand_total", return_value=500)
    def test_approver_role_does_not_grant_general_draft_editing(
        self,
        _mocked_base_total: MagicMock,
        _mocked_get_roles: MagicMock,
    ) -> None:
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.DRAFT_STATE,
            next_state=payment_approval_setup.DRAFT_STATE,
            base_grand_total=500,
        )

        with set_user("approver@example.com"), self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_request_transition(payment_request, "before_save")

    def test_cancellation_sets_cancelled_workflow_state(self) -> None:
        payment_request = MagicMock()

        payment_approval.set_cancelled_workflow_state(payment_request, "before_cancel")

        payment_request.set.assert_called_once_with(
            payment_approval_setup.WORKFLOW_STATE_FIELD,
            payment_approval_setup.CANCELLED_STATE,
        )

    def test_active_outward_approval_cannot_be_discarded(self) -> None:
        payment_request = frappe._dict(
            payment_request_type="Outward",
            payment_approval_state=payment_approval_setup.PENDING_PRIMARY_STATE,
        )

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_before_discard(cast(Document, payment_request), "before_discard")

    @patch.object(payment_approval, "_delete_completed_workflow_actions")
    def test_revisiting_actionable_state_clears_completed_action(
        self,
        mocked_delete_actions: MagicMock,
    ) -> None:
        payment_request = self._payment_request_document(
            previous_state=payment_approval_setup.REJECTED_STATE,
            next_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            base_grand_total=1500,
        )

        payment_approval.clear_completed_workflow_actions_for_next_state(
            payment_request,
            "before_save",
        )

        mocked_delete_actions.assert_called_once_with(
            "PRQ-TEST-0001",
            payment_approval_setup.PENDING_PRIMARY_STATE,
        )

    @patch.object(payment_approval, "_delete_completed_workflow_actions")
    @patch.object(payment_approval, "process_workflow_actions")
    @patch.object(payment_approval.frappe, "get_doc")
    @patch.object(payment_approval.frappe.db, "set_value")
    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval, "now_datetime")
    def test_due_payment_request_escalates_under_lock(
        self,
        mocked_now_datetime: MagicMock,
        mocked_get_value: MagicMock,
        mocked_set_value: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_process_actions: MagicMock,
        mocked_delete_actions: MagicMock,
    ) -> None:
        now = datetime(2026, 7, 19, 12, 0, 0)
        mocked_now_datetime.return_value = now
        mocked_get_value.return_value = frappe._dict(
            docstatus=0,
            payment_request_type="Outward",
            payment_approval_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            approval_due_at=now - timedelta(minutes=1),
        )
        payment_request = MagicMock()
        mocked_get_doc.return_value = payment_request

        result = payment_approval.escalate_payment_approval("PRQ-TEST-0001")

        self.assertTrue(result)
        mocked_get_value.assert_called_once_with(
            payment_approval_setup.PAYMENT_REQUEST_DOCTYPE,
            "PRQ-TEST-0001",
            [
                "docstatus",
                "payment_request_type",
                payment_approval_setup.WORKFLOW_STATE_FIELD,
                payment_approval_setup.APPROVAL_DUE_AT_FIELD,
            ],
            as_dict=True,
            for_update=True,
        )
        mocked_set_value.assert_any_call(
            payment_approval_setup.PAYMENT_REQUEST_DOCTYPE,
            "PRQ-TEST-0001",
            payment_approval_setup.WORKFLOW_STATE_FIELD,
            payment_approval_setup.ESCALATED_PRIMARY_STATE,
            modified_by="Administrator",
        )
        mocked_delete_actions.assert_called_once_with(
            "PRQ-TEST-0001", payment_approval_setup.ESCALATED_PRIMARY_STATE
        )
        mocked_process_actions.assert_called_once_with(payment_request, "on_update")

    @patch.object(payment_approval.frappe.db, "set_value")
    @patch.object(payment_approval.frappe.db, "get_value")
    @patch.object(payment_approval, "now_datetime")
    def test_payment_request_not_due_is_not_escalated(
        self,
        mocked_now_datetime: MagicMock,
        mocked_get_value: MagicMock,
        mocked_set_value: MagicMock,
    ) -> None:
        now = datetime(2026, 7, 19, 12, 0, 0)
        mocked_now_datetime.return_value = now
        mocked_get_value.return_value = frappe._dict(
            docstatus=0,
            payment_request_type="Outward",
            payment_approval_state=payment_approval_setup.PENDING_PRIMARY_STATE,
            approval_due_at=now + timedelta(minutes=1),
        )

        result = payment_approval.escalate_payment_approval("PRQ-TEST-0001")

        self.assertFalse(result)
        mocked_set_value.assert_not_called()

    def _maker_next_states(
        self,
        payment_request_type: str,
        base_grand_total: float,
        company_limit: float | None,
    ) -> set[str]:
        payment_request = cast(
            Document,
            WorkflowDocument(
                payment_request_type=payment_request_type,
                company="Connect Diagnostics",
                base_grand_total=base_grand_total,
            ),
        )
        with patch.object(payment_approval_setup.frappe.db, "get_value", return_value=company_limit):
            return {
                transition["next_state"]
                for transition in payment_approval_setup.WORKFLOW_TRANSITIONS
                if transition["state"] == payment_approval_setup.DRAFT_STATE
                and transition["allowed"] == "Accounts Manager"
                and is_transition_condition_satisfied(frappe._dict(transition), payment_request)
            }

    def _payment_request_document(
        self,
        *,
        previous_state: str,
        next_state: str,
        base_grand_total: float,
        previous_base_grand_total: float | None = None,
        payment_approval_limit: float | None = None,
        previous_payment_approval_limit: float | None = None,
        grand_total: float = 500,
        currency: str = "THB",
        payment_request_type: str = "Outward",
        approval_due_at: datetime | None = None,
        previous_approval_due_at: datetime | None = None,
        owner: str = "maker@example.com",
        previous_owner: str | None = None,
    ) -> Document:
        if previous_owner is None:
            previous_owner = owner
        if previous_base_grand_total is None:
            previous_base_grand_total = base_grand_total
        values: dict[str, Any] = {
            "doctype": payment_approval_setup.PAYMENT_REQUEST_DOCTYPE,
            "name": "PRQ-TEST-0001",
            "owner": owner,
            "company": "Connect Diagnostics",
            "currency": currency,
            "reference_doctype": "Purchase Invoice",
            "reference_name": "PINV-TEST-0001",
            "grand_total": grand_total,
            "payment_request_type": payment_request_type,
            payment_approval_setup.BASE_GRAND_TOTAL_FIELD: base_grand_total,
            payment_approval_setup.PAYMENT_APPROVAL_LIMIT_FIELD: payment_approval_limit,
            payment_approval_setup.APPROVAL_DUE_AT_FIELD: approval_due_at,
            payment_approval_setup.WORKFLOW_STATE_FIELD: next_state,
        }
        previous_values = frappe._dict(
            {
                **values,
                "owner": previous_owner,
                payment_approval_setup.BASE_GRAND_TOTAL_FIELD: previous_base_grand_total,
                payment_approval_setup.PAYMENT_APPROVAL_LIMIT_FIELD: (previous_payment_approval_limit),
                payment_approval_setup.APPROVAL_DUE_AT_FIELD: previous_approval_due_at,
                payment_approval_setup.WORKFLOW_STATE_FIELD: previous_state,
            }
        )
        payment_request = MagicMock()
        payment_request.flags.ignore_permissions = False
        payment_request.get.side_effect = lambda fieldname, default=None: values.get(fieldname, default)
        payment_request.set.side_effect = lambda fieldname, value: values.__setitem__(fieldname, value)
        payment_request.precision.return_value = 2
        payment_request.get_doc_before_save.return_value = previous_values
        return cast(Document, payment_request)


class TestPaymentEntryApprovalGate(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        rounding_patch = patch.object(
            frappe,
            "get_system_settings",
            return_value="Banker's Rounding (legacy)",
        )
        rounding_patch.start()
        self.addCleanup(rounding_patch.stop)

    def test_receive_and_internal_transfer_keep_standard_submit_path(self) -> None:
        for payment_type in ("Receive", "Internal Transfer"):
            with self.subTest(payment_type=payment_type):
                payment_entry = self._payment_entry([], payment_type=payment_type)
                payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    def test_outgoing_payment_without_allocated_reference_is_rejected(self) -> None:
        payment_entry = self._payment_entry([])

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    def test_outgoing_payment_with_unallocated_amount_is_rejected(self) -> None:
        row = self._reference_row(payment_request="PRQ-0001", allocated_amount=500)
        payment_entry = self._payment_entry([row], unallocated_amount=0.01)

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    def test_every_allocated_row_requires_payment_request(self) -> None:
        row = self._reference_row(payment_request=None, allocated_amount=500)
        payment_entry = self._payment_entry([row])

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval.frappe, "get_precision", return_value=2)
    @patch.object(payment_approval.frappe.db, "get_value")
    def test_wrong_payment_request_attributes_are_rejected(
        self,
        mocked_get_value: MagicMock,
        _mocked_precision: MagicMock,
    ) -> None:
        mismatches = {
            "payment_request_type": "Inward",
            "docstatus": 0,
            payment_approval_setup.WORKFLOW_STATE_FIELD: payment_approval_setup.REJECTED_STATE,
            "company": "Other Company",
            "party_type": "Customer",
            "party": "Other Supplier",
            "reference_doctype": "Purchase Order",
            "reference_name": "PINV-OTHER",
        }
        for fieldname, value in mismatches.items():
            with self.subTest(fieldname=fieldname):
                request = self._approved_request()
                request[fieldname] = value
                mocked_get_value.return_value = request
                row = self._reference_row(payment_request="PRQ-0001", allocated_amount=500)
                payment_entry = self._payment_entry([row])

                with self.assertRaises(frappe.ValidationError):
                    payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval.frappe, "get_precision", return_value=2)
    @patch.object(payment_approval.frappe.db, "get_value")
    def test_payment_requests_are_locked_in_sorted_order_and_multiple_requests_are_allowed(
        self,
        mocked_get_value: MagicMock,
        _mocked_precision: MagicMock,
    ) -> None:
        requests = {
            "PRQ-0001": self._approved_request(outstanding_amount=250),
            "PRQ-0002": self._approved_request(reference_name="PINV-0002", outstanding_amount=250),
        }
        mocked_get_value.side_effect = lambda _dt, name, _fields, **_kwargs: requests[name]
        rows = [
            self._reference_row(
                payment_request="PRQ-0002",
                reference_name="PINV-0002",
                allocated_amount=250,
                idx=1,
            ),
            self._reference_row(
                payment_request="PRQ-0001",
                reference_name="PINV-0001",
                allocated_amount=250,
                idx=2,
            ),
        ]

        payment_approval.validate_payment_entry_before_submit(self._payment_entry(rows), "before_submit")

        self.assertEqual(
            [current_call.args[1] for current_call in mocked_get_value.call_args_list],
            ["PRQ-0001", "PRQ-0002"],
        )
        for current_call in mocked_get_value.call_args_list:
            self.assertTrue(current_call.kwargs["for_update"])

    @patch.object(payment_approval.frappe, "get_precision", return_value=2)
    @patch.object(payment_approval.frappe.db, "get_value")
    def test_aggregate_allocation_per_request_cannot_exceed_outstanding(
        self,
        mocked_get_value: MagicMock,
        _mocked_precision: MagicMock,
    ) -> None:
        mocked_get_value.return_value = self._approved_request(outstanding_amount=50000)
        rows = [
            self._reference_row(payment_request="PRQ-0001", allocated_amount=25000, idx=1),
            self._reference_row(payment_request="PRQ-0001", allocated_amount=25000.01, idx=2),
        ]

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(self._payment_entry(rows), "before_submit")

    @patch.object(payment_approval.frappe, "get_precision", return_value=2)
    @patch.object(payment_approval.frappe.db, "get_value")
    def test_partial_payments_consume_request_outstanding(
        self,
        mocked_get_value: MagicMock,
        _mocked_precision: MagicMock,
    ) -> None:
        row = self._reference_row(payment_request="PRQ-0001", allocated_amount=25000)
        payment_entry = self._payment_entry([row])
        mocked_get_value.side_effect = [
            self._approved_request(outstanding_amount=50000),
            self._approved_request(outstanding_amount=25000),
            self._approved_request(outstanding_amount=0),
        ]

        payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")
        payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")
        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    @patch.object(payment_approval.frappe, "get_precision", return_value=2)
    @patch.object(payment_approval.frappe.db, "get_value")
    def test_customer_refund_allocation_uses_absolute_amount(
        self,
        mocked_get_value: MagicMock,
        _mocked_precision: MagicMock,
    ) -> None:
        mocked_get_value.return_value = self._approved_request(
            party_type="Customer",
            party="CUST-0001",
            reference_doctype="Sales Invoice",
            reference_name="SINV-RETURN-0001",
            outstanding_amount=500,
        )
        row = self._reference_row(
            payment_request="PRQ-0001",
            reference_doctype="Sales Invoice",
            reference_name="SINV-RETURN-0001",
            allocated_amount=-500,
        )
        payment_entry = self._payment_entry(
            [row],
            party_type="Customer",
            party="CUST-0001",
        )

        payment_approval.validate_payment_entry_before_submit(payment_entry, "before_submit")

    def test_no_reference_and_unsupported_party_payments_are_blocked(self) -> None:
        for party_type, reference_doctype in (
            ("Supplier", None),
            ("Employee", "Journal Entry"),
            ("Shareholder", "Journal Entry"),
        ):
            with self.subTest(party_type=party_type):
                rows = (
                    []
                    if reference_doctype is None
                    else [
                        self._reference_row(
                            payment_request=None,
                            reference_doctype=reference_doctype,
                            allocated_amount=500,
                        )
                    ]
                )
                with self.assertRaises(frappe.ValidationError):
                    payment_approval.validate_payment_entry_before_submit(
                        self._payment_entry(rows, party_type=party_type),
                        "before_submit",
                    )

    def _payment_entry(
        self,
        rows: list[Document],
        *,
        payment_type: str = "Pay",
        company: str = "Connect Diagnostics",
        party_type: str = "Supplier",
        party: str = "SUP-0001",
        unallocated_amount: float = 0,
    ) -> Document:
        values: dict[str, Any] = {
            "payment_type": payment_type,
            "company": company,
            "party_type": party_type,
            "party": party,
            "unallocated_amount": unallocated_amount,
            "references": rows,
        }
        payment_entry = MagicMock()
        payment_entry.get.side_effect = lambda fieldname, default=None: values.get(fieldname, default)
        payment_entry.precision.return_value = 2
        return cast(Document, payment_entry)

    def _reference_row(
        self,
        *,
        payment_request: str | None,
        allocated_amount: float,
        reference_doctype: str = "Purchase Invoice",
        reference_name: str = "PINV-0001",
        idx: int = 1,
    ) -> Document:
        values = {
            "payment_request": payment_request,
            "allocated_amount": allocated_amount,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
        }
        row = MagicMock()
        row.idx = idx
        row.get.side_effect = lambda fieldname, default=None: values.get(fieldname, default)
        row.precision.return_value = 2
        return cast(Document, row)

    def _approved_request(
        self,
        *,
        company: str = "Connect Diagnostics",
        party_type: str = "Supplier",
        party: str = "SUP-0001",
        reference_doctype: str = "Purchase Invoice",
        reference_name: str = "PINV-0001",
        outstanding_amount: float = 500,
    ) -> frappe._dict:
        return frappe._dict(
            docstatus=1,
            payment_request_type="Outward",
            company=company,
            party_type=party_type,
            party=party,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            outstanding_amount=outstanding_amount,
            payment_approval_state=payment_approval_setup.APPROVED_STATE,
        )
