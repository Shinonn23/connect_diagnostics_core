# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    remove_obsolete_property_setter_fixture_values,
    rollback_remove_obsolete_property_setter_fixture_values,
)

TEST_SETTERS = (
    ("Driver", "naming_series", "default", "DV.YY-BE.MM.####", "Text"),
    ("Purchase Order Item", "required_by", "in_list_view", "0", "Check"),
)


class TestRemoveObsoletePropertySetterFixtureValues(UnitTestCase):
    @patch.object(remove_obsolete_property_setter_fixture_values.frappe.db, "commit")
    @patch.object(remove_obsolete_property_setter_fixture_values.frappe, "clear_cache")
    @patch.object(remove_obsolete_property_setter_fixture_values.frappe, "delete_doc")
    @patch.object(remove_obsolete_property_setter_fixture_values.frappe.db, "exists")
    def test_execute_deletes_only_matching_legacy_values(
        self,
        exists,
        delete_doc,
        clear_cache,
        commit,
    ) -> None:
        exists.side_effect = ["Driver-naming_series-default", None]

        with patch.object(
            remove_obsolete_property_setter_fixture_values,
            "OBSOLETE_PROPERTY_SETTERS",
            TEST_SETTERS,
        ):
            remove_obsolete_property_setter_fixture_values.execute()

        self.assertEqual(
            exists.call_args_list,
            [
                call(
                    "Property Setter",
                    {
                        "doc_type": doctype,
                        "field_name": fieldname,
                        "property": property_name,
                        "value": value,
                    },
                )
                for doctype, fieldname, property_name, value, _property_type in TEST_SETTERS
            ],
        )
        delete_doc.assert_called_once_with(
            "Property Setter",
            "Driver-naming_series-default",
            ignore_permissions=True,
            force=True,
        )
        clear_cache.assert_called_once_with(doctype="Driver")
        commit.assert_called_once_with()

    @patch.object(rollback_remove_obsolete_property_setter_fixture_values.frappe.db, "commit")
    @patch.object(rollback_remove_obsolete_property_setter_fixture_values.frappe, "clear_cache")
    @patch.object(rollback_remove_obsolete_property_setter_fixture_values, "make_property_setter")
    def test_rollback_restores_removed_values(self, make_property_setter, clear_cache, commit) -> None:
        with patch.object(
            rollback_remove_obsolete_property_setter_fixture_values,
            "OBSOLETE_PROPERTY_SETTERS",
            TEST_SETTERS,
        ):
            rollback_remove_obsolete_property_setter_fixture_values.execute()

        self.assertEqual(
            make_property_setter.call_args_list,
            [
                call(
                    doctype,
                    fieldname,
                    property_name,
                    value,
                    property_type,
                    validate_fields_for_doctype=False,
                    is_system_generated=False,
                )
                for doctype, fieldname, property_name, value, property_type in TEST_SETTERS
            ],
        )
        self.assertCountEqual(
            clear_cache.call_args_list,
            [call(doctype="Driver"), call(doctype="Purchase Order Item")],
        )
        commit.assert_called_once_with()
