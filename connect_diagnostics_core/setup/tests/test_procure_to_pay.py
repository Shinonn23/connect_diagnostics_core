# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import procure_to_pay


class TestProcureToPaySetup(UnitTestCase):
    def test_purchase_order_item_list_columns_are_code_managed(self) -> None:
        self.assertEqual(
            procure_to_pay.PROPERTY_SETTERS["Purchase Order Item"],
            [
                ("item_name", "in_list_view", "1", "Check"),
            ],
        )
