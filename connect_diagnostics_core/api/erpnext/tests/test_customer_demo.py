# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import customer_demo


def make_document(doctype: str, **values: object) -> Document:
    return cast(Document, frappe._dict({"doctype": doctype, **values}))


class TestCustomerDemoQuantityPolicy(UnitTestCase):
    def test_accepts_only_one_to_one_whole_stock_uom_quantities(self) -> None:
        valid_row = make_document(
            "Material Request Item",
            qty=2,
            stock_qty=2,
            uom="Each",
            stock_uom="Each",
            conversion_factor=1,
        )

        customer_demo._validate_demo_item_quantity(valid_row, "FA-1")

    def test_rejects_fractional_or_converted_asset_quantities(self) -> None:
        invalid_rows = (
            make_document(
                "Material Request Item",
                qty=0.5,
                stock_qty=1,
                uom="Box",
                stock_uom="Each",
                conversion_factor=2,
            ),
            make_document(
                "Material Request Item", qty=1, stock_qty=2, uom="Each", stock_uom="Each", conversion_factor=2
            ),
            make_document(
                "Material Request Item",
                qty=1,
                stock_qty=1.5,
                uom="Each",
                stock_uom="Each",
                conversion_factor=1,
            ),
            make_document(
                "Material Request Item",
                qty=1.5,
                stock_qty=1.5,
                uom="Each",
                stock_uom="Each",
                conversion_factor=1,
            ),
        )

        for row in invalid_rows:
            with self.subTest(row=row.as_dict()):
                with self.assertRaises(frappe.ValidationError):
                    customer_demo._validate_demo_item_quantity(row, "FA-1")


class TestCustomerDemoFulfillmentMath(UnitTestCase):
    def test_capitalization_does_not_duplicate_sent_ready_claimed_or_capitalized_units(self) -> None:
        needed = customer_demo._required_capitalization_units(
            target_qty=4,
            sent_qty=1,
            available_assets={"ASSET-2"},
            capitalized_assets={"ASSET-3"},
            away_claim_assets={"ASSET-4"},
        )

        self.assertEqual(needed, 0)

    def test_capitalization_counts_only_the_unrepresented_shortfall(self) -> None:
        needed = customer_demo._required_capitalization_units(
            target_qty=6,
            sent_qty=1,
            available_assets={"ASSET-2", "ASSET-3"},
            capitalized_assets={"ASSET-3", "ASSET-4"},
            away_claim_assets={"ASSET-5"},
        )

        self.assertEqual(needed, 1)

    def test_hold_requires_exactly_one_candidate_per_unfulfilled_unit(self) -> None:
        request = make_document(
            "Material Request",
            items=[
                make_document("Material Request Item", name="MR-ITEM-1", item_code="FA-1"),
                make_document("Material Request Item", name="MR-ITEM-2", item_code="FA-2"),
            ],
        )
        candidates = [
            {"material_request_item": "MR-ITEM-1", "asset": "ASSET-1"},
            {"material_request_item": "MR-ITEM-1", "asset": "ASSET-2"},
            {"material_request_item": "MR-ITEM-2", "asset": "ASSET-3"},
        ]

        with patch.object(customer_demo, "_remaining_demo_units", side_effect=[2, 1]):
            customer_demo._validate_hold_candidate_counts(request, candidates)

    def test_hold_rejects_insufficient_candidate_count(self) -> None:
        request = make_document(
            "Material Request",
            items=[make_document("Material Request Item", name="MR-ITEM-1", item_code="FA-1")],
        )

        with (
            patch.object(customer_demo, "_remaining_demo_units", return_value=2),
            self.assertRaises(frappe.ValidationError),
        ):
            customer_demo._validate_hold_candidate_counts(
                request,
                [{"material_request_item": "MR-ITEM-1", "asset": "ASSET-1"}],
            )

    def test_hold_rejects_excess_candidate_count(self) -> None:
        request = make_document(
            "Material Request",
            items=[make_document("Material Request Item", name="MR-ITEM-1", item_code="FA-1")],
        )

        with (
            patch.object(customer_demo, "_remaining_demo_units", return_value=1),
            self.assertRaises(frappe.ValidationError),
        ):
            customer_demo._validate_hold_candidate_counts(
                request,
                [
                    {"material_request_item": "MR-ITEM-1", "asset": "ASSET-1"},
                    {"material_request_item": "MR-ITEM-1", "asset": "ASSET-2"},
                ],
            )


class TestCustomerDemoCandidateEligibility(UnitTestCase):
    def test_depreciated_asset_can_become_ready_at_source_location(self) -> None:
        asset = frappe._dict(
            docstatus=1,
            status="Fully Depreciated",
            company="CO-1",
            item_code="FA-1",
            location="LOC-SOURCE",
        )
        request = make_document("Material Request", company="CO-1", demo_source_location="LOC-SOURCE")

        with patch.object(customer_demo.frappe.db, "get_value", return_value=asset):
            available = customer_demo._is_available_claim_asset(request, None, "ASSET-1")

        self.assertTrue(available)

    def test_capitalized_asset_is_never_available_for_a_demo(self) -> None:
        asset = frappe._dict(
            docstatus=1,
            status="Capitalized",
            company="CO-1",
            item_code="FA-1",
            location="LOC-SOURCE",
        )
        request = make_document("Material Request", company="CO-1", demo_source_location="LOC-SOURCE")

        with patch.object(customer_demo.frappe.db, "get_value", return_value=asset):
            available = customer_demo._is_available_claim_asset(request, None, "ASSET-1")

        self.assertFalse(available)

    def test_return_to_wrong_location_is_rejected(self) -> None:
        request = make_document(
            "Material Request",
            name="MR-OLD",
            docstatus=1,
            material_request_type="Customer Demo",
            company="CO-1",
            demo_customer="CUSTOMER-1",
            demo_source_location="LOC-SOURCE",
            demo_target_location="LOC-CUSTOMER",
        )
        movement = make_document(
            "Asset Movement",
            demo_return_for_material_request="MR-OLD",
            reference_doctype=None,
            company="CO-1",
            purpose="Transfer",
            assets=[
                make_document(
                    "Asset Movement Item",
                    asset="ASSET-1",
                    source_location="LOC-CUSTOMER",
                    target_location="LOC-WRONG",
                )
            ],
        )
        asset = frappe._dict(
            docstatus=1,
            status="Fully Depreciated",
            company="CO-1",
            location="LOC-CUSTOMER",
        )

        with (
            patch.object(customer_demo.frappe, "has_permission"),
            patch.object(customer_demo.frappe, "get_doc", return_value=request),
            patch.object(customer_demo.frappe.db, "get_value", side_effect=[asset, None]),
            patch.object(customer_demo, "_validate_demo_outbound_provenance"),
            self.assertRaises(frappe.ValidationError),
        ):
            customer_demo.validate_customer_demo_return_movement(movement)

    def test_movement_must_include_returned_exact_candidate(self) -> None:
        request_item = make_document("Material Request Item", name="MR-ITEM-1", item_code="FA-1", stock_qty=1)
        request = make_document(
            "Material Request",
            name="MR-1",
            docstatus=1,
            material_request_type="Customer Demo",
            company="CO-1",
            demo_status="Ready",
            demo_source_location="LOC-SOURCE",
            demo_target_location="LOC-CUSTOMER",
            items=[request_item],
        )
        movement = make_document(
            "Asset Movement",
            company="CO-1",
            purpose="Transfer",
            assets=[
                make_document(
                    "Asset Movement Item",
                    asset="ASSET-OTHER",
                    source_location="LOC-SOURCE",
                    target_location="LOC-CUSTOMER",
                )
            ],
        )
        eligible_asset = frappe._dict(
            item_code="FA-1",
            company="CO-1",
            docstatus=1,
            status="Partially Depreciated",
            location="LOC-SOURCE",
        )

        def get_value(doctype: str, name: str, fieldname: object, **kwargs: object) -> object:
            if doctype == "Asset":
                return eligible_asset
            return None

        with (
            patch.object(customer_demo.frappe, "has_permission"),
            patch.object(customer_demo.frappe.db, "get_value", side_effect=get_value),
            patch.object(customer_demo.frappe.db, "sql", return_value=[]),
            patch.object(
                customer_demo.frappe, "get_all", return_value=[frappe._dict(asset="ASSET-CANDIDATE")]
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            customer_demo.validate_customer_demo_asset_movement_reference(movement, request)
