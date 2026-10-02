# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import asset_installation as setup


class TestAssetInstallationSetup(UnitTestCase):
    def test_native_customer_settings_are_idempotent(self) -> None:
        with (
            patch.object(
                setup.frappe.db,
                "get_value",
                side_effect=lambda doctype, *args, **kwargs: "NATIVE" if doctype == "DocField" else None,
            ),
            patch.object(setup.frappe.db, "exists", return_value=False),
            patch.object(setup, "make_property_setter") as setter,
            patch.object(setup.frappe, "clear_cache"),
        ):
            setup.apply_configuration()
        self.assertEqual(setter.call_count, len(setup.PROPERTIES))
        self.assertEqual(
            {call.args[2] for call in setter.call_args_list}, {name for name, _, _ in setup.PROPERTIES}
        )

    def test_collision_prevents_all_writes(self) -> None:
        with (
            patch.object(
                setup.frappe.db,
                "get_value",
                side_effect=["NATIVE", frappe._dict(value="0", property_type="Check")],
            ),
            patch.object(setup, "make_property_setter") as setter,
            self.assertRaises(frappe.ValidationError),
        ):
            setup.apply_configuration()
        setter.assert_not_called()
