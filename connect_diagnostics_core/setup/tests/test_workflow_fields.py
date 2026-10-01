# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import workflow_fields


class TestWorkflowFields(UnitTestCase):
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
                "approval_approver_user",
                "approval_critical_digest",
                "checked_by",
                "checked_at",
                "checked_signature",
                "authorized_by",
                "authorized_at",
                "authorized_signature",
            },
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Payment Entry"]},
            {"workflow_state"},
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Stock Entry"]},
            {
                "freeze_exception",
                "freeze_exception_reason",
                "freeze_exception_reconciliation_scope",
                "approval_critical_digest",
                "approval_reviewer_user",
                "approval_authorized_user",
            },
        )
        self.assertEqual(
            {row["fieldname"] for row in fields["Sales Order"]},
            {
                "approval_revision",
                "approval_digest",
                "approval_maker_user",
                "approval_maker_at",
                "approval_reviewer_user",
                "approval_reviewer_at",
                "approval_approver_user",
                "approval_approver_at",
            },
        )

        for rows in fields.values():
            for row in rows:
                fieldname = str(row["fieldname"])
                self.assertFalse(fieldname.startswith("custom_"))

    def test_sales_order_approval_fields_are_hidden_read_only_and_no_copy(self) -> None:
        for field in workflow_fields.CUSTOM_FIELDS["Sales Order"]:
            self.assertEqual(field["hidden"], 1)
            self.assertEqual(field["read_only"], 1)
            self.assertEqual(field["no_copy"], 1)
