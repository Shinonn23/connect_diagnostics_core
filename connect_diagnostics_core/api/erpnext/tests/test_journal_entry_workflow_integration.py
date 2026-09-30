# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import journal_entry_workflow as workflow

MAKER = "_test_je_maker@example.com"
CHECKER = "_test_je_checker@example.com"
APPROVER = "_test_je_approver@example.com"


class TestJournalEntryWorkflowIntegration(IntegrationTestCase):
    """Exercise the real native Workflow, Journal Entry controller, and GL."""

    def setUp(self) -> None:
        super().setUp()
        if not frappe.db.exists("Workflow", "Connect Journal Entry Approval"):
            self.skipTest("Journal Entry Workflow has not been migrated on this test site")
        department = frappe.db.get_value("Department", {}, ["name", "company"], as_dict=True)
        employment_type = frappe.db.get_value("Employment Type", {}, "name")
        if not department or not employment_type:
            self.skipTest("Employee prerequisites are unavailable")
        self.company = str(department.company)
        self.department = str(department.name)
        self.employment_type = str(employment_type)
        thai_settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == self.company for row in thai_settings.company_accounts):
            thai_settings.append("company_accounts", {"company": self.company})
            thai_settings.save(ignore_permissions=True)
        accounts = frappe.get_all(
            "Account",
            filters={"company": self.company, "is_group": 0, "disabled": 0},
            fields=["name", "root_type", "account_type"],
        )
        self.debit_account = next(
            (
                row.name
                for row in accounts
                if row.root_type == "Asset" and row.account_type not in {"Receivable"}
            ),
            None,
        )
        self.credit_account = next(
            (
                row.name
                for row in accounts
                if row.root_type == "Liability" and row.account_type not in {"Payable"}
            ),
            None,
        )
        if not self.debit_account or not self.credit_account:
            self.skipTest("Two non-party balance-sheet accounts are unavailable")
        self._make_actor(MAKER, "Accounts User", "_Test JE Maker")
        self._make_actor(CHECKER, "Accounts Manager", "_Test JE Checker")
        self._make_actor(APPROVER, "C-Level Approver", "_Test JE Approver")
        self.addCleanup(lambda: frappe.set_user("Administrator"))

    def _make_actor(self, email: str, role: str, first_name: str) -> None:
        frappe.db.delete("Employee", {"user_id": email})
        frappe.db.delete("Has Role", {"parent": email})
        frappe.db.delete("User", {"name": email})
        user = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": first_name,
                    "send_welcome_email": 0,
                    "roles": [{"role": role}],
                }
            ),
        )
        user.insert(ignore_permissions=True)
        employee = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": first_name,
                    "company": self.company,
                    "department": self.department,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active",
                    "employment_type": self.employment_type,
                    "user_id": email,
                    "approval_signature": "data:image/png;base64,c2ln",
                }
            ),
        )
        employee.insert(ignore_permissions=True)
        frappe.get_doc("User", email).add_roles(role)
        frappe.clear_cache(user=email)

    def _new_journal_entry(self) -> Document:
        return cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Journal Entry",
                    "company": self.company,
                    "posting_date": frappe.utils.today(),
                    "voucher_type": "Journal Entry",
                    "user_remark": "_Test Journal Entry approval",
                    "accounts": [
                        {
                            "account": self.debit_account,
                            "debit_in_account_currency": 100,
                            "department": self.department,
                        },
                        {
                            "account": self.credit_account,
                            "credit_in_account_currency": 100,
                            "department": self.department,
                        },
                    ],
                }
            ),
        )

    def test_activation_is_owned_by_serialized_gate(self) -> None:
        self.assertEqual(workflow.APPROVED_STATE, "Journal Entry Approved")
        self.assertIn(workflow.SUBMITTED_STATE, workflow._STATES)
        self.assertFalse(frappe.get_meta("Journal Entry").queue_in_background)

    def test_three_actor_happy_path_posts_and_cancels_native_gl(self) -> None:
        frappe.set_user(MAKER)
        doc = self._new_journal_entry().insert()
        self.assertEqual(doc.get("workflow_state"), "Journal Entry Draft")
        doc = apply_workflow(doc, "Send Journal Entry for Review")
        self.assertEqual(doc.approval_maker_user, MAKER)

        frappe.set_user(CHECKER)
        doc = apply_workflow(doc, "Review Journal Entry")
        self.assertEqual(doc.approval_checker_user, CHECKER)
        self.assertTrue(doc.approval_checker_signature)

        frappe.set_user(APPROVER)
        self.assertIn("C-Level Approver", frappe.get_roles(APPROVER))
        from frappe.permissions import get_doc_permissions, get_role_permissions

        self.assertEqual(get_role_permissions("Journal Entry", APPROVER)["read"], 1)
        self.assertTrue(
            frappe.has_permission("Journal Entry", "read", doc=doc, user=APPROVER),
            get_doc_permissions(doc, APPROVER),
        )
        doc = apply_workflow(doc, "Approve Journal Entry")
        self.assertEqual(doc.approval_approver_user, APPROVER)
        self.assertTrue(doc.approval_approver_signature)

        frappe.set_user(CHECKER)
        doc = apply_workflow(doc, "Submit Journal Entry")
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.workflow_state, workflow.SUBMITTED_STATE)
        self.assertFalse(doc.approval_submit_proof)
        self.assertEqual(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Journal Entry", "voucher_no": doc.name, "is_cancelled": 0},
            ),
            2,
        )

        doc = apply_workflow(doc, "Cancel Journal Entry")
        self.assertEqual(doc.docstatus, 2)
        self.assertEqual(doc.workflow_state, workflow.CANCELLED_STATE)
        self.assertFalse(doc.approval_cancel_proof)

    def test_direct_submit_and_self_review_are_denied_without_gl(self) -> None:
        frappe.set_user(MAKER)
        doc = self._new_journal_entry().insert()
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.ValidationError):
            doc.submit()
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": doc.name})
        )
        doc.reload()
        frappe.get_doc("User", MAKER).add_roles("Accounts Manager")
        frappe.set_user(MAKER)
        doc = apply_workflow(doc, "Send Journal Entry for Review")
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(doc, "Review Journal Entry")

    def test_return_resubmit_reject_and_post_review_mutation(self) -> None:
        frappe.set_user(MAKER)
        returned = apply_workflow(self._new_journal_entry().insert(), "Send Journal Entry for Review")
        frappe.set_user(CHECKER)
        returned = apply_workflow(returned, "Return Journal Entry")
        self.assertEqual(returned.workflow_state, "Journal Entry Returned")
        self.assertFalse(returned.approval_checker_user)
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": returned.name})
        )
        frappe.set_user(MAKER)
        returned = apply_workflow(returned, "Resubmit Journal Entry for Review")
        frappe.set_user(CHECKER)
        reviewed = apply_workflow(returned, "Review Journal Entry")
        reviewed.user_remark = "_Test forbidden mutation after review"
        with self.assertRaises(frappe.ValidationError):
            reviewed.save()

        frappe.set_user(MAKER)
        rejected = apply_workflow(self._new_journal_entry().insert(), "Send Journal Entry for Review")
        frappe.set_user(CHECKER)
        rejected = apply_workflow(rejected, "Review Journal Entry")
        frappe.set_user(APPROVER)
        rejected = apply_workflow(rejected, "Reject Journal Entry")
        self.assertEqual(rejected.workflow_state, "Journal Entry Rejected")
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": rejected.name})
        )
        rejected.user_remark = "_Test rejected mutation"
        with self.assertRaises(frappe.ValidationError):
            rejected.save()
