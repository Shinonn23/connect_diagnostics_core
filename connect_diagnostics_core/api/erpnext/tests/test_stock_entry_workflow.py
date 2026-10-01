# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_entry_workflow


class TestStockEntryWorkflow(UnitTestCase):
    def test_direct_transfer_requires_approval(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Draft",
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.validate_before_submit(doc)
        throw.assert_called_once()

    def test_direct_transfer_can_submit_after_approval(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Submitted",
            }
        )
        with patch.object(stock_entry_workflow.frappe, "throw") as throw:
            stock_entry_workflow.authorize_submit_execution(doc)
            stock_entry_workflow.validate_before_submit(doc)
        throw.assert_not_called()

    def test_transit_and_other_purposes_are_not_route(self) -> None:
        self.assertFalse(
            stock_entry_workflow.is_direct_transfer(
                frappe.get_doc(
                    {"doctype": "Stock Entry", "purpose": "Material Transfer", "add_to_transit": 1}
                )
            )
        )
        self.assertFalse(
            stock_entry_workflow.is_direct_transfer(
                frappe.get_doc({"doctype": "Stock Entry", "purpose": "Material Issue"})
            )
        )
