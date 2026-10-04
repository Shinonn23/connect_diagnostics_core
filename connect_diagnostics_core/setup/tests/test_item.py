# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

from frappe.tests import UnitTestCase

ITEM_CUSTOMIZATION = Path(__file__).resolve().parents[2] / "connect_diagnostics_core" / "custom" / "item.json"


class TestItemCustomizationExport(UnitTestCase):
    def test_item_custom_fields_and_layout_are_exported_together(self) -> None:
        data = json.loads(ITEM_CUSTOMIZATION.read_text())
        fields = {field["fieldname"]: field for field in data["custom_fields"]}
        field_order_setters = [
            setter
            for setter in data["property_setters"]
            if setter["doctype_or_field"] == "DocType" and setter["property"] == "field_order"
        ]

        self.assertEqual(data["doctype"], "Item")
        self.assertEqual(len(field_order_setters), 1)
        field_order = json.loads(field_order_setters[0]["value"])
        self.assertIn("demo_conversion_section", field_order)
        self.assertIn("demo_stock_item", field_order)
        self.assertLess(field_order.index("demo_conversion_section"), field_order.index("demo_stock_item"))
        self.assertEqual(fields["demo_stock_item"]["fieldtype"], "Link")
        self.assertEqual(fields["demo_stock_item"]["options"], "Item")
        self.assertFalse(
            any(fieldname.startswith("demo_") and "warehouse" in fieldname for fieldname in fields),
            "Customer Demo source Warehouse belongs to the Material Request item row, not Item.",
        )

    def test_existing_item_fields_remain_in_the_single_export(self) -> None:
        data = json.loads(ITEM_CUSTOMIZATION.read_text())
        fieldnames = {field["fieldname"] for field in data["custom_fields"]}

        self.assertTrue(
            {
                "dksh_tab",
                "is_medical_device",
                "medical_device_regulatory_section",
                "current_medical_device_registration",
                "shelf_life_section",
                "withholding_tax_type",
                "withholding_tax_type_pay_supplier",
                "withholding_tax_type_pay_individual",
            }.issubset(fieldnames)
        )
