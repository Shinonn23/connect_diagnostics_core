# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import workflow_fields


class TestWorkflowFields(UnitTestCase):
    def test_purchase_order_has_revision_bound_approval_fields(self) -> None:
        fields = {field["fieldname"]: field for field in workflow_fields.CUSTOM_FIELDS["Purchase Order"]}

        self.assertEqual(
            set(fields),
            {
                "workflow_state",
                "approval_critical_digest",
                "approval_digest_version",
                "approval_reviewer_user",
                "approval_authorized_user",
            },
        )
        for fieldname in (
            "approval_critical_digest",
            "approval_digest_version",
            "approval_reviewer_user",
            "approval_authorized_user",
        ):
            self.assertEqual(fields[fieldname]["read_only"], 1)
            self.assertEqual(fields[fieldname]["no_copy"], 1)

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
            {row["fieldname"] for row in fields["Purchase Invoice"]},
            {
                "workflow_state",
                "trial_policy_warning",
                "approval_critical_digest",
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
