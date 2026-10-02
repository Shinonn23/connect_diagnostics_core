# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.sales_order_workflow import SNAPSHOT_FIELDS
from connect_diagnostics_core.setup import print_action_fields, workflow_fields


class TestWorkflowFields(UnitTestCase):
    def test_all_approved_routes_have_hidden_immutable_approval_fields(self) -> None:
        expected = {
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "approval_critical_digest",
        }
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
            fields = {str(row["fieldname"]): row for row in workflow_fields.CUSTOM_FIELDS[doctype]}
            self.assertTrue(expected <= fields.keys(), doctype)
            for fieldname in expected:
                self.assertEqual(fields[fieldname]["hidden"], 1)
                self.assertEqual(fields[fieldname]["read_only"], 1)
                self.assertEqual(fields[fieldname]["allow_on_submit"], 1)
                self.assertEqual(fields[fieldname]["no_copy"], 1)
                self.assertEqual(fields[fieldname]["is_system_generated"], 1)
                if fields[fieldname]["fieldtype"] == "Link":
                    self.assertEqual(fields[fieldname]["ignore_user_permissions"], 1)

    def test_all_field_definitions_are_unique_and_workflow_states_are_protected(self) -> None:
        for doctype, rows in workflow_fields.CUSTOM_FIELDS.items():
            names = [str(row["fieldname"]) for row in rows]
            self.assertEqual(len(names), len(set(names)), doctype)
            state = next(row for row in rows if row["fieldname"] == "workflow_state")
            for key in (
                "hidden",
                "read_only",
                "allow_on_submit",
                "no_copy",
                "is_system_generated",
                "ignore_user_permissions",
            ):
                self.assertEqual(state[key], 1, (doctype, key))

    def test_workflow_fields_are_setup_managed_without_custom_prefix(self) -> None:
        fields = workflow_fields.CUSTOM_FIELDS
        self.assertEqual(set(fields), set(workflow_fields.TARGET_DOCTYPES))
        shared = {
            "workflow_state",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "approval_critical_digest",
        }
        for rows in fields.values():
            self.assertTrue(shared <= {str(row["fieldname"]) for row in rows})

        self.assertTrue(shared <= {row["fieldname"] for row in fields["Asset Movement"]})
        self.assertEqual(
            {row["fieldname"] for row in fields["Payment Entry"]},
            {
                "workflow_state",
                "approval_maker_user",
                "approval_reviewer_user",
                "approval_authorized_user",
                "approval_critical_digest",
                "approval_digest",
                "approval_maker_at",
                "approval_checker_user",
                "approval_checker_at",
                "approval_approver_user",
                "approval_approver_at",
                "approval_submit_actor",
                "approval_cancel_actor",
            },
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Purchase Invoice"]},
            {
                "workflow_state",
                "trial_policy_warning",
                "approval_critical_digest",
                "approval_maker_user",
                "approval_reviewer_user",
                "approval_authorized_user",
            },
        )
        purchase_invoice_fields = {str(row["fieldname"]): row for row in fields["Purchase Invoice"]}
        self.assertIn("TEST POLICY ONLY", str(purchase_invoice_fields["trial_policy_warning"]["default"]))
        for fieldname in ("approval_reviewer_user", "approval_authorized_user"):
            self.assertEqual(purchase_invoice_fields[fieldname]["fieldtype"], "Link")
            self.assertEqual(purchase_invoice_fields[fieldname]["options"], "User")
            self.assertEqual(purchase_invoice_fields[fieldname]["ignore_user_permissions"], 1)
        self.assertEqual(
            {row["fieldname"] for row in fields["Stock Entry"]},
            {
                "freeze_exception",
                "freeze_exception_reason",
                "freeze_exception_reconciliation_scope",
                "workflow_state",
                "approval_maker_user",
                "approval_reviewer_user",
                "approval_authorized_user",
                "approval_critical_digest",
            },
        )

        for rows in fields.values():
            for row in rows:
                fieldname = str(row["fieldname"])
                self.assertFalse(fieldname.startswith("custom_"))

    def test_payroll_actor_links_ignore_employee_user_permission_filters(self) -> None:
        fields = {str(row["fieldname"]): row for row in workflow_fields.CUSTOM_FIELDS["Payroll Entry"]}
        for fieldname in (
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
        ):
            self.assertEqual(fields[fieldname]["ignore_user_permissions"], 1)
        print_fields = {
            str(row["fieldname"]): row for row in print_action_fields.CUSTOM_FIELDS["Payroll Entry"]
        }
        for fieldname in ("checked_by", "authorized_by"):
            self.assertEqual(print_fields[fieldname]["ignore_user_permissions"], 1)

    def test_payroll_output_authority_is_protected_and_separate_from_input(self) -> None:
        fields = {str(row["fieldname"]): row for row in workflow_fields.CUSTOM_FIELDS["Payroll Entry"]}
        expected = {
            "output_reviewed_by": "Link",
            "output_reviewed_at": "Datetime",
            "output_review_signature": "Data",
            "output_review_digest": "Data",
            "output_review_version": "Data",
            "output_review_revision": "Int",
        }
        self.assertEqual({name for name in fields if name.startswith("output_")}, set(expected))
        for fieldname, fieldtype in expected.items():
            definition = fields[fieldname]
            self.assertEqual(definition["fieldtype"], fieldtype)
            for key in ("hidden", "read_only", "allow_on_submit", "no_copy", "is_system_generated"):
                self.assertEqual(definition[key], 1, (fieldname, key))
            self.assertFalse(definition.get("default"))
            self.assertFalse(definition.get("reqd"))
        self.assertEqual(fields["output_reviewed_by"]["options"], "User")
        self.assertEqual(fields["output_reviewed_by"]["ignore_user_permissions"], 1)

    def test_shared_print_snapshot_definitions_agree_with_workflow_fields(self) -> None:
        for doctype, workflow_rows in workflow_fields.CUSTOM_FIELDS.items():
            print_fields = {
                str(row["fieldname"]): row for row in print_action_fields.CUSTOM_FIELDS.get(doctype, [])
            }
            for definition in workflow_rows:
                fieldname = str(definition["fieldname"])
                if fieldname not in print_fields:
                    continue
                other = print_fields[fieldname]
                for key in definition.keys() | other.keys():
                    self.assertEqual(
                        definition.get(key) or None,
                        other.get(key) or None,
                        (doctype, fieldname, key),
                    )

    def test_sales_billing_authority_matches_native_signature_and_is_locked_after_submit(self) -> None:
        fields = {str(row["fieldname"]): row for row in workflow_fields.CUSTOM_FIELDS["Sales Order"]}
        expected = {
            "billing_authority_revision": ("Data", None),
            "billing_authority_digest": ("Data", None),
            "billing_authorized_by": ("Link", "User"),
            "billing_authorized_at": ("Datetime", None),
            "billing_authorized_signature": ("Signature", None),
            "billing_authority_source_state": ("Data", None),
            "billing_receivable_account": ("Link", "Account"),
        }
        self.assertEqual({name for name in fields if name.startswith("billing_")}, set(expected))
        for name, (fieldtype, options) in expected.items():
            field = fields[name]
            self.assertEqual(field["fieldtype"], fieldtype)
            self.assertEqual(field.get("options"), options)
            self.assertEqual(field["hidden"], int(name != "billing_receivable_account"))
            self.assertEqual(field["read_only"], 1)
            self.assertEqual(field["no_copy"], 1)
            self.assertFalse(field.get("allow_on_submit"))
            self.assertFalse(field.get("default"))
            self.assertFalse(field.get("reqd"))

    def test_sales_order_runtime_approval_evidence_has_code_managed_schema(self) -> None:
        fields = {str(row["fieldname"]): row for row in workflow_fields.CUSTOM_FIELDS["Sales Order"]}
        expected_types = {
            "approval_revision": "Data",
            "approval_digest": "Data",
            "approval_maker_at": "Datetime",
            "approval_reviewer_at": "Datetime",
            "approval_approver_user": "Link",
            "approval_approver_at": "Datetime",
        }
        self.assertTrue({key for key in SNAPSHOT_FIELDS if key.startswith("approval_")} <= fields.keys())
        for fieldname, fieldtype in expected_types.items():
            definition = fields[fieldname]
            self.assertEqual(definition["fieldtype"], fieldtype)
            for key in ("hidden", "read_only", "allow_on_submit", "no_copy", "is_system_generated"):
                self.assertEqual(definition[key], 1, (fieldname, key))
            self.assertFalse(definition.get("reqd"))
            self.assertFalse(definition.get("default"))
        self.assertEqual(fields["approval_approver_user"]["options"], "User")
        self.assertEqual(fields["approval_approver_user"]["ignore_user_permissions"], 1)
