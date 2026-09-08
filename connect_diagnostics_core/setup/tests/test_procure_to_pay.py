# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import procure_to_pay


class TestProcureToPayPropertySetters(UnitTestCase):
    def test_demo_and_loan_are_separate_usage_options(self) -> None:
        usage = next(
            field
            for field in procure_to_pay.CUSTOM_FIELDS["Material Request"]
            if field["fieldname"] == "request_usage"
        )

        options = str(usage["options"]).splitlines()
        self.assertIn("Customer Demo", options)
        self.assertIn("Customer Loan", options)
        self.assertNotIn("Customer Demo / Loan", options)

    def test_fulfillment_cost_fields_are_accounts_permission_level(self) -> None:
        fields = procure_to_pay.CUSTOM_FIELDS["Material Request Item"]

        self.assertEqual(
            {field["fieldname"] for field in fields},
            {"fulfillment_route", "allocated_asset", "unit_cost_ex_vat", "cost_source"},
        )
        self.assertTrue(all(field["allow_on_submit"] == 1 for field in fields))
        self.assertTrue(all(field["permlevel"] == 1 for field in fields))

    def test_purchase_reason_keeps_fieldname_with_new_label(self) -> None:
        field = next(
            field
            for field in procure_to_pay.CUSTOM_FIELDS["Material Request"]
            if field["fieldname"] == "purchase_reason"
        )

        self.assertEqual(field["label"], "Request Reason")

    def test_purchase_order_item_list_columns_are_code_managed(self) -> None:
        self.assertEqual(
            procure_to_pay.PROPERTY_SETTERS["Purchase Order Item"],
            [
                ("item_name", "in_list_view", "1", "Check"),
            ],
        )
