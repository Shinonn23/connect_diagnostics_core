# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_action_fields


class TestPrintActionFields(UnitTestCase):
    def test_registry_source_has_unique_doctype_keys(self) -> None:
        tree = ast.parse(Path(print_action_fields.__file__).read_text())
        registry = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "PRINT_ACTIONS"
        )
        assert isinstance(registry, ast.Dict)
        names = [key.value for key in registry.keys if isinstance(key, ast.Constant)]
        self.assertEqual(len(names), len(set(names)))

    def test_protected_actions_require_signature(self) -> None:
        for doctype in (
            "Sales Invoice",
            "Payment Entry",
            "Sales Order",
            "Purchase Order",
            "Purchase Invoice",
            "Payroll Entry",
            "Material Request",
            "Stock Reconciliation",
            "Asset Movement",
            "Journal Entry",
            "Stock Entry",
        ):
            actions = {action.key: action for action in print_action_fields.PRINT_ACTIONS[doctype]}
            with self.subTest(doctype=doctype):
                self.assertTrue(actions["authorized"].protected)
                self.assertTrue(actions["authorized"].required_signature)
        for doctype in ("Stock Entry", "Stock Reconciliation", "Purchase Order", "Payment Entry"):
            action = next(
                action for action in print_action_fields.PRINT_ACTIONS[doctype] if action.key == "checked"
            )
            self.assertTrue(action.protected)
            self.assertTrue(action.required_signature)

    def test_stock_reconciliation_uses_existing_signed_fields(self) -> None:
        actions = print_action_fields.PRINT_ACTIONS["Stock Reconciliation"]
        self.assertEqual(
            [
                (action.key, action.employee_field, action.datetime_field, action.signature_field)
                for action in actions
            ],
            [
                ("checked", "checked_by", "checked_at", "checked_signature"),
                ("authorized", "authorized_by", "authorized_at", "authorized_signature"),
            ],
        )
        self.assertTrue(all(action.protected and action.required_signature for action in actions))
        self.assertTrue(all(action.ignore_employee_user_permissions for action in actions))
        fields = {
            str(field["fieldname"]): field
            for field in print_action_fields.CUSTOM_FIELDS["Stock Reconciliation"]
        }
        for prefix in ("checked", "authorized"):
            self.assertEqual(fields[f"{prefix}_by"]["ignore_user_permissions"], 1)
            for suffix in ("by", "at", "signature"):
                self.assertTrue(fields[f"{prefix}_{suffix}"]["read_only"])
                self.assertTrue(fields[f"{prefix}_{suffix}"]["no_copy"])

    def test_payment_entry_signed_evidence_uses_immutable_employee_links(self) -> None:
        fields = {
            str(field["fieldname"]): field for field in print_action_fields.CUSTOM_FIELDS["Payment Entry"]
        }
        for prefix in ("checked", "authorized"):
            self.assertEqual(fields[f"{prefix}_by"]["ignore_user_permissions"], 1)
            for suffix in ("by", "at", "signature"):
                field = fields[f"{prefix}_{suffix}"]
                self.assertTrue(field["read_only"])
                self.assertTrue(field["no_copy"])

    def test_approved_routes_have_signed_review_and_authorization_snapshots(self) -> None:
        for doctype in (
            "Stock Entry",
            "Stock Reconciliation",
            "Asset Movement",
            "Journal Entry",
            "Sales Order",
            "Sales Invoice",
            "Purchase Order",
            "Purchase Invoice",
            "Payment Entry",
            "Payroll Entry",
        ):
            actions = {action.key for action in print_action_fields.PRINT_ACTIONS[doctype]}
            self.assertIn("checked", actions, doctype)
            self.assertIn("authorized", actions, doctype)

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

    def test_sales_order_actor_evidence_does_not_filter_business_scope_by_employee(self) -> None:
        fields = {
            str(field["fieldname"]): field for field in print_action_fields.CUSTOM_FIELDS["Sales Order"]
        }
        for fieldname in ("submit_by", "prepared_by", "checked_by", "authorized_by"):
            field = fields[fieldname]
            self.assertEqual(field["fieldtype"], "Link")
            self.assertEqual(field["options"], "Employee")
            self.assertEqual(field["ignore_user_permissions"], 1)
            for flag in ("hidden", "read_only", "allow_on_submit", "no_copy", "is_system_generated"):
                self.assertEqual(field[flag], 1, (fieldname, flag))

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
                    self.assertEqual(
                        employee.get("ignore_user_permissions"),
                        1 if (doctype == "Payroll Entry" or action.ignore_employee_user_permissions) else 0,
                    )
                    self.assertEqual(timestamp["fieldtype"], "Datetime")
                    self.assertEqual(signature["fieldtype"], "Signature")
                    for field in (employee, timestamp, signature):
                        self.assertEqual(field["hidden"], 1)
                        self.assertEqual(field["read_only"], 1)
                        self.assertEqual(field["allow_on_submit"], 1)
                        self.assertEqual(field["no_copy"], 1)

    def test_all_employee_audit_fields_ignore_actor_scope_and_permission_defaults(self) -> None:
        for doctype, actions in print_action_fields.PRINT_ACTIONS.items():
            fields = {field["fieldname"]: field for field in print_action_fields.CUSTOM_FIELDS[doctype]}
            for action in actions:
                self.assertEqual(fields[action.employee_field]["ignore_user_permissions"], 1, doctype)

    def test_explicit_employee_scope_opt_out_is_convergent_for_targeted_rollback(self) -> None:
        action = print_action_fields.PrintAction(
            "checked",
            "checked_by",
            "checked_at",
            "checked_signature",
            ignore_employee_user_permissions=False,
        )
        employee, timestamp, signature = print_action_fields._fields_for_action(action)
        self.assertEqual(employee["ignore_user_permissions"], 0)
        self.assertEqual(employee["options"], "Employee")
        self.assertNotIn("ignore_user_permissions", timestamp)
        self.assertNotIn("ignore_user_permissions", signature)

    def test_action_fieldnames_are_unique_per_doctype(self) -> None:
        for doctype, fields in print_action_fields.CUSTOM_FIELDS.items():
            fieldnames = [field["fieldname"] for field in fields]
            self.assertEqual(len(fieldnames), len(set(fieldnames)), doctype)

    def test_payroll_employee_snapshots_ignore_employee_user_permission_filters(self) -> None:
        fields = {
            str(field["fieldname"]): field for field in print_action_fields.CUSTOM_FIELDS["Payroll Entry"]
        }
        self.assertEqual(fields["checked_by"]["ignore_user_permissions"], 1)
        self.assertEqual(fields["authorized_by"]["ignore_user_permissions"], 1)

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
