# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import customer_credit_request, procure_to_pay, supplier, workflow
from connect_diagnostics_core.api.erpnext.supplier import before_submit_bank_change_request
from connect_diagnostics_core.setup import procure_to_pay as p2p


class TestWorkflowBypass(UnitTestCase):
    def test_inactive_workflow_sets_final_state(self) -> None:
        document = MagicMock(doctype="Purchase Receipt")

        with patch.object(workflow.frappe.db, "get_value", side_effect=[None, "Workflow"]):
            bypassed = workflow.finalize_if_workflow_inactive(
                document,
                "p2p_workflow_state",
                p2p.RECEIPT_ACCEPTED,
            )

        self.assertTrue(bypassed)
        document.set.assert_called_once_with("p2p_workflow_state", p2p.RECEIPT_ACCEPTED)

    def test_active_workflow_does_not_set_final_state(self) -> None:
        document = MagicMock(doctype="Purchase Receipt")

        with patch.object(workflow.frappe.db, "get_value", return_value="Workflow"):
            bypassed = workflow.finalize_if_workflow_inactive(
                document,
                "p2p_workflow_state",
                p2p.RECEIPT_ACCEPTED,
            )

        self.assertFalse(bypassed)
        document.set.assert_not_called()

    def test_missing_workflow_fails_closed(self) -> None:
        with patch.object(workflow.frappe.db, "get_value", return_value=None):
            with self.assertRaises(frappe.ValidationError):
                workflow.finalize_if_workflow_inactive(
                    MagicMock(doctype="Purchase Receipt"),
                    "p2p_workflow_state",
                    p2p.RECEIPT_ACCEPTED,
                )

    def test_purchase_receipt_submit_hook_bypasses_inactive_workflow(self) -> None:
        document = MagicMock(doctype="Purchase Receipt")

        with patch.object(procure_to_pay, "finalize_if_workflow_inactive") as finalize:
            procure_to_pay.validate_before_submit(document)

        finalize.assert_called_once_with(
            document,
            "p2p_workflow_state",
            p2p.RECEIPT_ACCEPTED,
        )

    def test_purchase_invoice_exception_gate_skipped_when_workflow_inactive(self) -> None:
        document = MagicMock(doctype="Purchase Invoice")

        with (
            patch.object(procure_to_pay, "finalize_if_workflow_inactive", return_value=True),
            patch.object(procure_to_pay, "_validate_purchase_invoice_exception") as exception_gate,
        ):
            procure_to_pay.validate_before_submit(document)

        exception_gate.assert_not_called()

    def test_purchase_invoice_exception_gate_enforced_when_workflow_active(self) -> None:
        document = MagicMock(doctype="Purchase Invoice")

        with (
            patch.object(procure_to_pay, "finalize_if_workflow_inactive", return_value=False),
            patch.object(procure_to_pay, "_validate_purchase_invoice_exception") as exception_gate,
        ):
            procure_to_pay.validate_before_submit(document)

        exception_gate.assert_called_once_with(document)

    def test_purchase_order_exception_gate_skipped_when_workflow_inactive(self) -> None:
        document = MagicMock(doctype="Purchase Order")

        with (
            patch.object(procure_to_pay, "finalize_if_workflow_inactive", return_value=True),
            patch.object(procure_to_pay, "_validate_purchase_order_exception") as exception_gate,
        ):
            procure_to_pay.validate_before_submit(document)

        exception_gate.assert_not_called()

    def test_purchase_order_exception_gate_enforced_when_workflow_active(self) -> None:
        document = MagicMock(doctype="Purchase Order")

        with (
            patch.object(procure_to_pay, "finalize_if_workflow_inactive", return_value=False),
            patch.object(procure_to_pay, "_validate_purchase_order_exception") as exception_gate,
        ):
            procure_to_pay.validate_before_submit(document)

        exception_gate.assert_called_once_with(document)

    def test_supplier_submit_bypasses_inactive_workflow(self) -> None:
        document = MagicMock(doctype="Supplier")

        with (
            patch.object(supplier, "finalize_if_workflow_inactive") as finalize,
            patch.object(supplier, "_has_verified_bank_account", return_value=True),
        ):
            supplier.before_submit(document)

        finalize.assert_called_once_with(document, "supplier_onboarding_state", p2p.SUPPLIER_ACTIVE)
        document.set.assert_called_once_with("disabled", 0)

    def test_bank_change_submit_bypasses_inactive_workflow(self) -> None:
        document = MagicMock(doctype="Supplier Bank Change Request")
        document.get.return_value = None

        with patch.object(supplier, "finalize_if_workflow_inactive") as finalize:
            finalize.return_value = True
            before_submit_bank_change_request(document)

        finalize.assert_called_once_with(document, "bank_change_request_state", p2p.BANK_VERIFIED)
        self.assertEqual(document.set.call_count, 4)

    def test_customer_credit_submit_bypasses_inactive_workflow(self) -> None:
        document = MagicMock(doctype="Customer Credit Request")

        with patch.object(customer_credit_request, "finalize_if_workflow_inactive") as finalize:
            customer_credit_request.before_submit(document)

        finalize.assert_called_once_with(
            document,
            "credit_request_state",
            customer_credit_request.customer_onboarding.CREDIT_REQUEST_APPROVED_STATE,
        )
        document.set.assert_any_call("approved_by", customer_credit_request.frappe.session.user)
