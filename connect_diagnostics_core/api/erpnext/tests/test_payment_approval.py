# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payment_approval
from connect_diagnostics_core.setup import payment_approval as setup


class TestPaymentRequestApproval(UnitTestCase):
    def test_inactive_workflow_finalizes_outward_request_before_submit(self) -> None:
        document = MagicMock()
        document.get.side_effect = lambda fieldname: {
            "payment_request_type": "Outward",
            "company": "Connect Diagnostics",
            "currency": "THB",
            "reference_doctype": "Purchase Order",
            "reference_name": "PO-0001",
        }.get(fieldname)

        with (
            patch.object(payment_approval, "_get_previous_doc", return_value=None),
            patch.object(payment_approval, "_validate_payment_request_fields"),
            patch.object(payment_approval, "_validate_verified_supplier_bank"),
            patch.object(
                payment_approval.frappe.db, "get_value", side_effect=[None, "Payment Request Approval"]
            ),
        ):
            payment_approval.validate_payment_request_before_submit(document, "before_submit")

        document.set.assert_called_once_with(setup.WORKFLOW_STATE_FIELD, setup.APPROVED_STATE)

    def test_payment_entry_requires_reference_and_evidence(self) -> None:
        document = MagicMock()
        document.get.side_effect = lambda fieldname: {"payment_type": "Pay"}.get(fieldname)

        with self.assertRaises(frappe.ValidationError):
            payment_approval.validate_payment_entry_before_submit(document, "before_submit")

    def test_payment_request_locking_uses_sorted_request_names(self) -> None:
        document = MagicMock()
        document.get.side_effect = lambda fieldname: {
            "payment_type": "Pay",
            "reference_no": "REF-1",
            "reference_date": "2026-08-03",
            "unallocated_amount": 0,
        }.get(fieldname)
        document.precision.return_value = 2
        first = MagicMock(payment_request="PR-2", idx=1)
        second = MagicMock(payment_request="PR-1", idx=2)
        first.get.side_effect = lambda fieldname: {"payment_request": "PR-2", "allocated_amount": 10}.get(
            fieldname
        )
        second.get.side_effect = lambda fieldname: {"payment_request": "PR-1", "allocated_amount": 10}.get(
            fieldname
        )
        first.precision.return_value = 2
        second.precision.return_value = 2

        with (
            patch.object(payment_approval.frappe.db, "exists", return_value=True),
            patch.object(payment_approval, "_get_allocated_reference_rows", return_value=[first, second]),
            patch.object(payment_approval, "_lock_payment_requests", return_value={}) as locked,
        ):
            with self.assertRaises(KeyError):
                payment_approval.validate_payment_entry_before_submit(document, "before_submit")

        locked.assert_called_once_with(("PR-1", "PR-2"))
