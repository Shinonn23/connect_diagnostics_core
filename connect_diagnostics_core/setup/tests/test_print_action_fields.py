# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_action_fields


class TestPrintActionFields(UnitTestCase):
    def test_purchase_order_review_and_approval_require_distinct_signed_actions(self) -> None:
        actions = {action.key: action for action in print_action_fields.PRINT_ACTIONS["Purchase Order"]}

        self.assertEqual(set(actions), {"submit", "ordered", "checked", "authorized"})
        for action_key in ("submit", "ordered"):
            self.assertFalse(actions[action_key].required_signature)
            self.assertFalse(actions[action_key].protected)
        for action_key in ("checked", "authorized"):
            self.assertTrue(actions[action_key].required_signature)
            self.assertTrue(actions[action_key].protected)

    def test_material_request_and_capitalization_keep_only_authorized_snapshot(self) -> None:
        for doctype in ("Material Request", "Asset Capitalization"):
            self.assertEqual(
                [action.key for action in print_action_fields.PRINT_ACTIONS[doctype]],
                ["authorized"],
            )

    def test_purchase_invoice_has_checked_and_authorized_snapshots(self) -> None:
        self.assertEqual(
            [action.key for action in print_action_fields.PRINT_ACTIONS["Purchase Invoice"]],
            ["checked", "authorized"],
        )
        fields = {
            field["fieldname"]: field for field in print_action_fields.CUSTOM_FIELDS["Purchase Invoice"]
        }
        self.assertEqual(fields["checked_by"]["ignore_user_permissions"], 1)
        self.assertEqual(fields["authorized_by"]["ignore_user_permissions"], 1)

    def test_action_definitions_have_hidden_employee_and_datetime_fields(self) -> None:
        for doctype, actions in print_action_fields.PRINT_ACTIONS.items():
            fields = {field["fieldname"]: field for field in print_action_fields.CUSTOM_FIELDS[doctype]}
            self.assertEqual(len(fields), len(actions) * 3, doctype)
            for action in actions:
                employee = fields[action.employee_field]
                timestamp = fields[action.datetime_field]
                signature = fields[action.signature_field]
                with self.subTest(doctype=doctype, action=action.key):
                    self.assertEqual(employee["fieldtype"], "Link")
                    self.assertEqual(employee["options"], "Employee")
                    self.assertEqual(employee["ignore_user_permissions"], 1)
                    self.assertEqual(timestamp["fieldtype"], "Datetime")
                    self.assertEqual(signature["fieldtype"], "Signature")
                    for field in (employee, timestamp, signature):
                        self.assertEqual(field["hidden"], 1)
                        self.assertEqual(field["read_only"], 1)
                        self.assertEqual(field["allow_on_submit"], 1)
                        self.assertEqual(field["no_copy"], 1)

    def test_action_fieldnames_are_unique_per_doctype(self) -> None:
        for doctype, fields in print_action_fields.CUSTOM_FIELDS.items():
            fieldnames = [field["fieldname"] for field in fields]
            self.assertEqual(len(fieldnames), len(set(fieldnames)), doctype)

    @patch.object(print_action_fields.frappe, "clear_cache")
    @patch.object(print_action_fields, "make_property_setter")
    @patch.object(print_action_fields, "create_custom_fields")
    def test_configuration_is_applied_idempotently_by_the_lifecycle_hook(
        self,
        create_custom_fields,
        make_property_setter,
        clear_cache,
    ) -> None:
        print_action_fields.apply_configuration()

        create_custom_fields.assert_called_once_with(
            print_action_fields.CUSTOM_FIELDS,
            ignore_validate=True,
        )
        self.assertEqual(
            make_property_setter.call_args_list,
            [
                call(
                    doctype,
                    None,
                    "default_print_format",
                    print_format,
                    "Data",
                    for_doctype=True,
                    validate_fields_for_doctype=False,
                )
                for doctype, print_format in print_action_fields.DEFAULT_PRINT_FORMATS.items()
            ],
        )
        self.assertEqual(
            clear_cache.call_args_list,
            [call(doctype=doctype) for doctype in print_action_fields.DEFAULT_PRINT_FORMATS],
        )
