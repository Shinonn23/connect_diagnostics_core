# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import item, purchase_invoice_item, sales_invoice_item


class TestThaiWithholdingFields(UnitTestCase):
    def test_item_fields_match_erpnext_thailand_contract(self) -> None:
        fields = {field["fieldname"]: field for field in item.CUSTOM_FIELDS["Item"]}

        self.assertEqual(fields["withholding_tax_type"]["options"], "Withholding Tax Type")
        self.assertEqual(
            fields["withholding_tax_type_pay_supplier"]["options"],
            "Withholding Tax Type",
        )
        self.assertEqual(
            fields["withholding_tax_type_pay_individual"]["options"],
            "Withholding Tax Type",
        )

    def test_invoice_item_fields_fetch_thai_withholding_type_from_item(self) -> None:
        sales_fields = {
            field["fieldname"]: field for field in sales_invoice_item.CUSTOM_FIELDS["Sales Invoice Item"]
        }
        purchase_fields = {
            field["fieldname"]: field
            for field in purchase_invoice_item.CUSTOM_FIELDS["Purchase Invoice Item"]
        }

        self.assertEqual(
            sales_fields["withholding_tax_type"]["fetch_from"],
            "item_code.withholding_tax_type",
        )
        self.assertEqual(
            purchase_fields["withholding_tax_type"]["fetch_from"],
            "item_code.withholding_tax_type_pay_supplier",
        )
        self.assertEqual(sales_fields["withholding_tax_type"]["read_only"], 1)
        self.assertEqual(purchase_fields["withholding_tax_type"]["read_only"], 1)
