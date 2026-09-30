# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.equipment_model_mapping_review.equipment_model_mapping_review import (
    _build_rows,
    _columns,
    execute,
)


class TestEquipmentModelMappingReview(UnitTestCase):
    @patch.object(frappe, "only_for", side_effect=frappe.PermissionError)
    def test_requires_system_manager_server_side(self, _only_for) -> None:
        with self.assertRaises(frappe.PermissionError):
            execute()

    def test_columns_match_the_admin_mapping_review_contract(self) -> None:
        self.assertEqual(
            [column["fieldname"] for column in _columns()],
            [
                "stock_item",
                "proposed_equipment_model",
                "fixed_asset_item",
                "allow_demo",
                "allow_stock_to_asset_conversion",
                "asset_category",
                "mapping_status",
            ],
        )

    def test_rows_show_mapped_disabled_invalid_and_unmapped_without_inference(self) -> None:
        stock_a = frappe._dict(
            name="STOCK-A", is_stock_item=1, is_fixed_asset=0, disabled=0, asset_category=None
        )
        stock_b = frappe._dict(
            name="STOCK-B", is_stock_item=1, is_fixed_asset=0, disabled=0, asset_category=None
        )
        fixed_a = frappe._dict(
            name="ASSET-A", is_stock_item=0, is_fixed_asset=1, disabled=0, asset_category="Computers"
        )
        fixed_b = frappe._dict(
            name="ASSET-B", is_stock_item=0, is_fixed_asset=1, disabled=0, asset_category="Computers"
        )
        invalid_fixed = frappe._dict(
            name="ASSET-INVALID",
            is_stock_item=1,
            is_fixed_asset=1,
            disabled=0,
            asset_category="Computers",
        )
        models = [
            frappe._dict(
                name="MODEL-A",
                stock_item="STOCK-A",
                fixed_asset_item="ASSET-A",
                allow_demo=1,
                allow_stock_to_asset_conversion=1,
                default_asset_category=None,
                disabled=0,
            ),
            frappe._dict(
                name="MODEL-DISABLED",
                stock_item="STOCK-DISABLED",
                fixed_asset_item="ASSET-DISABLED",
                allow_demo=0,
                allow_stock_to_asset_conversion=0,
                default_asset_category=None,
                disabled=1,
            ),
            frappe._dict(
                name="MODEL-INVALID",
                stock_item="STOCK-INVALID",
                fixed_asset_item="ASSET-INVALID",
                allow_demo=1,
                allow_stock_to_asset_conversion=0,
                default_asset_category=None,
                disabled=0,
            ),
        ]
        items: dict[str, frappe._dict] = {
            str(row.name): row for row in [stock_a, stock_b, fixed_a, fixed_b, invalid_fixed]
        }

        rows = _build_rows(models, items, [stock_a, stock_b], [fixed_a, fixed_b])
        statuses = {row["proposed_equipment_model"]: row["mapping_status"] for row in rows}

        self.assertEqual(statuses["MODEL-A"], "Mapped")
        self.assertEqual(statuses["MODEL-DISABLED"], "Disabled Model")
        self.assertEqual(statuses["MODEL-INVALID"], "Invalid Mapping")
        self.assertIn(
            {
                "stock_item": "STOCK-B",
                "proposed_equipment_model": None,
                "fixed_asset_item": None,
                "allow_demo": 0,
                "allow_stock_to_asset_conversion": 0,
                "asset_category": None,
                "mapping_status": "Unmapped Stock Item",
            },
            rows,
        )
        self.assertTrue(
            any(
                row["fixed_asset_item"] == "ASSET-B"
                and row["mapping_status"] == "Unmapped Fixed Asset Item"
                and not row["proposed_equipment_model"]
                for row in rows
            )
        )
