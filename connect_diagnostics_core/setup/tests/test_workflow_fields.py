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

        stock_fields = {str(row["fieldname"]) for row in fields["Stock Entry"]}
        self.assertFalse(
            {
                "freeze_exception",
                "freeze_exception_reason",
                "freeze_exception_reconciliation_scope",
            }
            & stock_fields
        )
        operation = next(
            row for row in fields["Journal Entry"] if row["fieldname"] == "approval_operation_id"
        )
        self.assertEqual(operation["unique"], 1)

        for rows in fields.values():
            for row in rows:
                fieldname = str(row["fieldname"])
                self.assertFalse(fieldname.startswith("custom_"))
                self.assertTrue(row["hidden"])
                self.assertTrue(row["allow_on_submit"])
                self.assertTrue(row["no_copy"])
