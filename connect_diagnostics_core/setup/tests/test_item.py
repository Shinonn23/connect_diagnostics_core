# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import item


class TestRelocatedAfterAnchor(UnitTestCase):
    def test_moves_the_fields_directly_after_the_anchor(self) -> None:
        current_order = [
            "has_serial_no",
            "min_remaining_shelf_life",
            "serial_no_series",
            "shelf_life_section",
            "variants_section",
        ]

        reordered = item._relocated_after_anchor(
            current_order, item._SHELF_LIFE_FIELDS, item._SHELF_LIFE_ANCHOR
        )

        self.assertEqual(
            reordered,
            [
                "has_serial_no",
                "serial_no_series",
                "shelf_life_section",
                "min_remaining_shelf_life",
                "variants_section",
            ],
        )

    def test_is_idempotent_once_already_ordered(self) -> None:
        already_ordered = [
            "has_serial_no",
            "serial_no_series",
            "shelf_life_section",
            "min_remaining_shelf_life",
            "variants_section",
        ]

        self.assertEqual(
            item._relocated_after_anchor(already_ordered, item._SHELF_LIFE_FIELDS, item._SHELF_LIFE_ANCHOR),
            already_ordered,
        )


class TestEnsureConfigurationShelfLifeReorder(UnitTestCase):
    def _meta_with(self, fieldnames: list[str]) -> MagicMock:
        meta = MagicMock()
        meta.fields = [MagicMock(fieldname=fieldname) for fieldname in fieldnames]
        return meta

    def test_skips_reorder_when_a_shelf_life_field_is_missing(self) -> None:
        meta = self._meta_with(["has_serial_no", "serial_no_series", "variants_section"])
        with (
            patch.object(item.frappe, "get_meta", return_value=meta),
            patch.object(item, "_set_field_order") as mocked_set_field_order,
        ):
            item.ensure_configuration()

        mocked_set_field_order.assert_not_called()

    def test_relocates_shelf_life_fields_when_nested_in_serial_nos_batches(self) -> None:
        meta = self._meta_with(
            [
                "has_serial_no",
                "min_remaining_shelf_life",
                "serial_no_series",
                "shelf_life_section",
                "variants_section",
            ]
        )
        with (
            patch.object(item.frappe, "get_meta", return_value=meta),
            patch.object(item, "_set_field_order") as mocked_set_field_order,
        ):
            item.ensure_configuration()

        mocked_set_field_order.assert_called_once_with(
            "Item",
            [
                "has_serial_no",
                "serial_no_series",
                "shelf_life_section",
                "min_remaining_shelf_life",
                "variants_section",
            ],
        )
