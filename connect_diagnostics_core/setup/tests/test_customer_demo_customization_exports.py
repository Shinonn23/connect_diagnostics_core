# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

from frappe.tests import UnitTestCase

CUSTOM_DIRECTORY = Path(__file__).resolve().parents[2] / "connect_diagnostics_core" / "custom"


def load_export(doctype: str) -> dict[str, object]:
    return json.loads((CUSTOM_DIRECTORY / f"{doctype}.json").read_text())


class TestCustomerDemoCustomizationExports(UnitTestCase):
    def test_demo_fields_are_exported_on_their_own_doctypes(self) -> None:
        request_fields = {
            field["fieldname"]: field for field in load_export("material_request")["custom_fields"]
        }
        request_item_fields = {
            field["fieldname"]: field for field in load_export("material_request_item")["custom_fields"]
        }
        asset_movement_fields = {
            field["fieldname"]: field for field in load_export("asset_movement")["custom_fields"]
        }
        capitalization_fields = {
            field["fieldname"]: field for field in load_export("asset_capitalization")["custom_fields"]
        }

        self.assertEqual(request_fields["demo_customer"]["options"], "Customer")
        self.assertEqual(request_fields["demo_source_location"]["options"], "Location")
        self.assertEqual(request_fields["demo_target_location"]["options"], "Location")
        self.assertNotIn("demo_source_warehouse", request_item_fields)
        self.assertFalse(request_item_fields)
        self.assertEqual(
            asset_movement_fields["demo_return_for_material_request"]["options"],
            "Material Request",
        )
        self.assertEqual(capitalization_fields["demo_material_request"]["options"], "Material Request")

    def test_hidden_demo_status_fields_do_not_block_asset_transfer_requests(self) -> None:
        fields = {field["fieldname"]: field for field in load_export("material_request")["custom_fields"]}
        for fieldname in (
            "demo_section",
            "demo_column_break",
            "demo_status",
            "demo_hold_reason",
            "demo_candidates",
        ):
            with self.subTest(fieldname=fieldname):
                self.assertIsNone(fields[fieldname]["mandatory_depends_on"])

        self.assertEqual(
            fields["demo_column_break"]["depends_on"],
            'eval:doc.material_request_type == "Customer Demo"',
        )
        self.assertEqual(
            fields["asset_source_location"]["depends_on"],
            'eval:doc.material_request_type == "Asset Transfer"',
        )

    def test_location_party_link_and_stock_item_mapping_are_configured(self) -> None:
        location_fields = {field["fieldname"]: field for field in load_export("location")["custom_fields"]}
        item_fields = {field["fieldname"]: field for field in load_export("item")["custom_fields"]}

        self.assertEqual(location_fields["custom_party_type"]["options"], "Customer\nSupplier")
        self.assertEqual(location_fields["custom_party_name"]["fieldtype"], "Dynamic Link")
        self.assertEqual(location_fields["custom_party_name"]["options"], "custom_party_type")
        self.assertEqual(
            location_fields["custom_party_name"]["mandatory_depends_on"],
            "eval:doc.custom_party_type",
        )
        self.assertEqual(item_fields["demo_stock_item"]["options"], "Item")
        self.assertIn('"is_stock_item"', item_fields["demo_stock_item"]["link_filters"])
