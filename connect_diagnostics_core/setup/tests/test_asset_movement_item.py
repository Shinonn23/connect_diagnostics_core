# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import asset_movement_item as setup


class TestAssetMovementItemSetup(UnitTestCase):
    def test_fresh_and_identical_configuration_converge(self) -> None:
        for existing in (None, *[frappe._dict(field) for field in setup.FIELDS]):
            with self.subTest(existing=existing):

                def lookup(doctype: str, filters: dict[str, str], *args: object, **kwargs: object) -> object:
                    del doctype, args, kwargs
                    return existing if existing and filters["fieldname"] == existing.fieldname else None

                with (
                    patch.object(setup.frappe.db, "exists", return_value=False),
                    patch.object(setup.frappe.db, "get_value", side_effect=lookup),
                    patch.object(setup.frappe.db, "table_exists", return_value=False),
                    patch.object(setup, "create_custom_fields") as create,
                    patch.object(setup.frappe.db, "add_index") as add_index,
                ):
                    setup.apply_configuration()
                    create.assert_called_once_with({setup.DOCTYPE: setup.FIELDS}, update=True)
                    add_index.assert_called_once_with(setup.DOCTYPE, ["asset", "parent"], setup.HISTORY_INDEX)

    def test_any_collision_stops_before_metadata_writes(self) -> None:
        for native in (False, True):
            with (
                self.subTest(native=native),
                patch.object(setup.frappe.db, "exists", return_value=native),
                patch.object(setup.frappe.db, "get_value", return_value=frappe._dict(fieldtype="Data")),
                patch.object(setup.frappe.db, "table_exists", return_value=False),
                patch.object(setup, "create_custom_fields") as create,
                patch.object(setup.frappe.db, "add_index") as add_index,
                self.assertRaises(frappe.ValidationError),
            ):
                setup.apply_configuration()
            create.assert_not_called()
            add_index.assert_not_called()

    def test_wrong_history_index_shape_stops_before_field_or_index_writes(self) -> None:
        wrong = [frappe._dict(Key_name=setup.HISTORY_INDEX, Seq_in_index=1, Column_name="parent")]
        with (
            patch.object(setup.frappe.db, "table_exists", return_value=True),
            patch.object(setup.frappe.db, "sql", return_value=wrong),
            patch.object(setup, "create_custom_fields") as create,
            patch.object(setup.frappe.db, "add_index") as add_index,
            self.assertRaises(frappe.ValidationError),
        ):
            setup.apply_configuration()
        create.assert_not_called()
        add_index.assert_not_called()

    def test_evidence_is_readonly_nullable_and_not_copied(self) -> None:
        fields = {field["fieldname"]: field for field in setup.FIELDS}
        self.assertEqual(fields["installation_customer"]["fieldtype"], "Link")
        self.assertEqual(fields["installation_customer"]["options"], "Customer")
        self.assertEqual(fields["installation_previous_customer"]["read_only"], 1)
        self.assertEqual(fields["installation_previous_customer"]["allow_on_submit"], 0)
        self.assertEqual(fields["receiver_user"]["read_only"], 0)
        self.assertEqual(fields["receiver_user"]["allow_on_submit"], 0)
        self.assertEqual(fields["receiver_user"]["ignore_user_permissions"], 0)
        for name in ("accepted_by", "accepted_at"):
            self.assertEqual(fields[name]["read_only"], 1)
            self.assertEqual(fields[name]["allow_on_submit"], 1)
        for field in fields.values():
            self.assertEqual(field["reqd"], 0)
            self.assertEqual(field["no_copy"], 1)
