# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_entry_workflow


class TestStockEntryWorkflow(UnitTestCase):
    def test_direct_transfer_requires_approved_workflow_state(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
                "workflow_state": "Stock Transfer Draft",
            }
        )

        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_before_submit(doc)

        throw.assert_called_once()

    def test_direct_transfer_can_submit_after_normal_or_exception_approval(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
                "workflow_state": "Stock Transfer Submitted",
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_before_submit(doc)
        throw.assert_not_called()

    def test_exception_requires_native_completed_review(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-EXCEPTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Urgent controlled movement",
            }
        )
        with patch.object(stock_entry_workflow.frappe.db, "exists", return_value=False):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_completed_reject_evidence_is_not_posting_authorization(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-REJECTED-EXCEPTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Rejected history must not authorize posting",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_native_execution_task_is_required_after_approval_evidence(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NATIVE-EXECUTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Native execution task proof",
                "custom_freeze_exception_reconciliation_scope": "[]",
            }
        )
        with patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True):
            with patch.object(stock_entry_workflow.frappe, "throw") as throw:
                stock_entry_workflow.authorize_freeze_exception_execution(doc)
            throw.assert_not_called()
            self.assertTrue(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_scope_rejects_new_freeze_before_execute(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NEW-FREEZE",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "New Freeze must not be bypassed",
                "custom_freeze_exception_reconciliation_scope": "[]",
            }
        )
        current_freeze = [
            {
                "item_code": "ITEM-A",
                "reconciliation": "SR-B",
                "warehouse": "WH-1",
                "modified": "2026-09-18 10:00:00",
            }
        ]
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.object(
                stock_entry_workflow,
                "_has_native_execution_provenance",
                return_value=True,
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.get_active_freeze_scope",
                return_value=current_freeze,
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_stale_completed_history_cannot_authorize_after_resubmit(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-STALE-RESUBMIT",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Old approval must not be reused",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_prior_history_and_spoofed_state_do_not_authorize_changed_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-SPOOFED-ROUTE",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
                "workflow_state": "Emergency Stock Movement Submitted",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Transit must not use direct exception",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(
                stock_entry_workflow.frappe.flags,
                {"freeze_exception_execution": {"doctype": doc.doctype, "name": doc.name}},
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_requires_reason_and_direct_route(self) -> None:
        missing_reason = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Stock Transfer Draft",
                "custom_freeze_exception": 1,
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_workflow(missing_reason)
        throw.assert_called_once()

        transit = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "workflow_state": "Stock Transfer Draft",
                "custom_freeze_exception": 1,
                "custom_freeze_exception_reason": "Urgent controlled movement",
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_workflow(transit)
        throw.assert_called_once()

    def test_transit_outbound_and_receipt_are_not_direct_route(self) -> None:
        outbound = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
            }
        )
        receipt = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": "STE-OUT",
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(outbound))
        self.assertFalse(stock_entry_workflow.is_direct_transfer(receipt))

    def test_other_stock_entry_purposes_are_not_direct_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Issue",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(doc))
