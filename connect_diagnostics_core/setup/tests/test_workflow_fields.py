# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import workflow_fields


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

    def test_workflow_fields_are_setup_managed_without_custom_prefix(self) -> None:
        fields = workflow_fields.CUSTOM_FIELDS

        self.assertEqual(
            {row["fieldname"] for row in fields["Asset Movement"]},
            {
                "workflow_state",
                "approval_maker_user",
                "approval_reviewer_user",
                "approval_authorized_user",
                "approval_critical_digest",
            },
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Payment Entry"]},
            {
                "workflow_state",
                "approval_maker_user",
                "approval_reviewer_user",
                "approval_authorized_user",
                "approval_critical_digest",
            },
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Stock Entry"]},
            {
                "workflow_state",
                "freeze_exception",
                "freeze_exception_reason",
                "freeze_exception_reconciliation_scope",
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
