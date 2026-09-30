# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import workflow_fields


class TestWorkflowFields(UnitTestCase):
    def test_workflow_fields_are_setup_managed_without_custom_prefix(self) -> None:
        fields = workflow_fields.CUSTOM_FIELDS

        self.assertEqual(
            {row["fieldname"] for row in fields["Asset Movement"]},
            {"workflow_state"},
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Payment Entry"]},
            {"workflow_state"},
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
                "workflow_state",
                "freeze_exception",
                "freeze_exception_reason",
                "freeze_exception_reconciliation_scope",
            },
        )

        for rows in fields.values():
            for row in rows:
                fieldname = str(row["fieldname"])
                self.assertFalse(fieldname.startswith("custom_"))
