# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
from __future__ import annotations

from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import stock_entry_workflow


class TestStockEntryWorkflowIntegration(IntegrationTestCase):
    def test_route_is_direct_material_transfer_only(self) -> None:
        self.assertEqual(stock_entry_workflow.DIRECT_TRANSFER_PURPOSE, "Material Transfer")
        self.assertEqual(stock_entry_workflow.APPROVED_STATE, "Stock Transfer Submitted")
