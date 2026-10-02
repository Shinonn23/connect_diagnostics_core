# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import repost_item_valuation


class TestRepostItemValuationSetup(UnitTestCase):
    def test_configuration_creates_native_table_field(self) -> None:
        with (
            patch.object(repost_item_valuation.frappe.db, "exists", return_value=False),
            patch.object(repost_item_valuation.frappe.db, "get_value", return_value=None),
            patch.object(repost_item_valuation, "create_custom_fields") as create,
        ):
            repost_item_valuation.ensure_configuration()
        create.assert_called_once_with(
            {repost_item_valuation.DOCTYPE: [repost_item_valuation.FIELD]}, update=True
        )

    def test_incompatible_existing_field_blocks_install(self) -> None:
        with (
            patch.object(repost_item_valuation.frappe.db, "exists", return_value=False),
            patch.object(
                repost_item_valuation.frappe.db,
                "get_value",
                return_value=frappe._dict(fieldtype="Data"),
            ),
            patch.object(repost_item_valuation, "create_custom_fields") as create,
            self.assertRaises(frappe.ValidationError),
        ):
            repost_item_valuation.ensure_configuration()
        create.assert_not_called()

    def test_matching_field_converges(self) -> None:
        with (
            patch.object(repost_item_valuation.frappe.db, "exists", return_value=False),
            patch.object(
                repost_item_valuation.frappe.db,
                "get_value",
                return_value=frappe._dict(repost_item_valuation.FIELD),
            ),
            patch.object(repost_item_valuation, "create_custom_fields") as create,
        ):
            repost_item_valuation.ensure_configuration()
        create.assert_called_once()
