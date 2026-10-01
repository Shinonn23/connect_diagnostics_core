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
        operation = next(
            row for row in fields["Journal Entry"] if row["fieldname"] == "approval_operation_id"
        )
        self.assertEqual(operation["unique"], 1)

        stock_fields = {row["fieldname"]: row for row in fields["Stock Entry"]}
        self.assertEqual(stock_fields["approval_reviewer_user"]["options"], "User")
        self.assertEqual(stock_fields["approval_authorized_user"]["options"], "User")
        self.assertTrue(stock_fields["approval_critical_digest"]["read_only"])

        for rows in fields.values():
            for row in rows:
                fieldname = str(row["fieldname"])
                self.assertFalse(fieldname.startswith("custom_"))

    def test_asset_movement_approval_fields_are_hidden_read_only_and_on_submit(self) -> None:
        rows = {row["fieldname"]: row for row in workflow_fields.CUSTOM_FIELDS["Asset Movement"]}
        for fieldname, fieldtype, options in (
            ("approval_maker_user", "Link", "User"),
            ("approval_reviewer_user", "Link", "User"),
            ("approval_approver_user", "Link", "User"),
            ("approval_critical_digest", "Data", None),
            ("checked_by", "Link", "Employee"),
            ("checked_at", "Datetime", None),
            ("checked_signature", "Signature", None),
            ("authorized_by", "Link", "Employee"),
            ("authorized_at", "Datetime", None),
            ("authorized_signature", "Signature", None),
        ):
            row = rows[fieldname]
            self.assertEqual(row["fieldtype"], fieldtype)
            self.assertTrue(row["hidden"])
            self.assertTrue(row["read_only"])
            self.assertTrue(row["allow_on_submit"])
            self.assertTrue(row["no_copy"])
            self.assertTrue(row["is_system_generated"])
            if options:
                self.assertEqual(row["options"], options)

        self.assertTrue(rows["checked_by"]["ignore_user_permissions"])
        self.assertTrue(rows["authorized_by"]["ignore_user_permissions"])
