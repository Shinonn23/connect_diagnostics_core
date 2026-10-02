# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from erpnext.accounts.utils import is_immutable_ledger_enabled
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


class TestJournalEntryWriteOffIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        savepoint = f"je_write_off_{frappe.generate_hash(length=10)}"
        frappe.db.savepoint(savepoint)
        self.addCleanup(lambda: frappe.set_user("Administrator"))
        self.addCleanup(frappe.db.rollback, save_point=savepoint)
        frappe.set_user("Administrator")
        self.company = "_Test Company"
        self.assertTrue(frappe.db.exists("Workflow", "Connect Journal Entry Approval"))
        self.assertTrue(frappe.db.exists("Company", self.company))
        self.department = str(
            frappe.db.get_value("Department", {"company": self.company, "disabled": 0}, "name")
            or frappe.get_doc(
                {
                    "doctype": "Department",
                    "department_name": f"_Test Write Off {frappe.generate_hash(length=8)}",
                    "company": self.company,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.employment_type = str(
            frappe.db.get_value("Employment Type", {}, "name")
            or frappe.get_doc(
                {
                    "doctype": "Employment Type",
                    "employee_type_name": f"_Test Write Off {frappe.generate_hash(length=8)}",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        suffix = frappe.generate_hash(length=10)
        self.maker = self._make_actor(f"writeoff-maker-{suffix}@example.com", "Accounts User", "Maker")
        self.checker = self._make_actor(
            f"writeoff-checker-{suffix}@example.com", "Accounts Manager", "Checker"
        )
        self.approver = self._make_actor(
            f"writeoff-approver-{suffix}@example.com", "C-Level Approver", "Approver"
        )

    def _make_actor(self, email: str, role: str, first_name: str) -> str:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": f"_Test Write Off {first_name}",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"_Test Write Off {first_name}",
                "company": self.company,
                "department": self.department,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "status": "Active",
                "employment_type": self.employment_type,
                "user_id": user.name,
                "approval_signature": "data:image/png;base64,c2ln",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc("User", user.name).add_roles(role)
        frappe.clear_cache(user=user.name)
        return str(user.name)

    def _new_invoice(self, customer: str, price_list: str, amount: float) -> Document:
        invoice = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Sales Invoice",
                    "company": self.company,
                    "customer": customer,
                    "currency": "INR",
                    "conversion_rate": 1,
                    "selling_price_list": price_list,
                    "price_list_currency": "INR",
                    "plc_conversion_rate": 1,
                    "debit_to": "Debtors - _TC",
                    "update_stock": 0,
                    "items": [
                        {
                            "item_code": "_Test Item",
                            "qty": 1,
                            "rate": amount,
                            "price_list_rate": amount,
                            "income_account": "Sales - _TC",
                            "expense_account": "Cost of Goods Sold - _TC",
                            "cost_center": "Main - _TC",
                        }
                    ],
                }
            ).insert(),
        )
        invoice.submit()
        return invoice

    def _approve_and_submit(self, entry: Document) -> Document:
        frappe.set_user(self.maker)
        entry = apply_workflow(entry, "Send Journal Entry for Review")
        frappe.set_user(self.checker)
        entry = apply_workflow(entry, "Review Journal Entry")
        frappe.set_user(self.approver)
        entry = apply_workflow(entry, "Approve Journal Entry")
        frappe.set_user(self.checker)
        return apply_workflow(entry, "Submit Journal Entry")

    def _new_customer_and_price_list(self, suffix: str) -> tuple[str, str]:
        price_list = frappe.get_doc(
            {
                "doctype": "Price List",
                "price_list_name": f"_Test Write Off Selling {suffix}",
                "selling": 1,
                "enabled": 1,
                "currency": "INR",
            }
        ).insert(ignore_permissions=True)
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"_Test Write Off Customer {suffix}",
                "customer_code": f"T-WRITEOFF-{suffix}",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Rest Of The World",
                "default_currency": "INR",
                "default_price_list": price_list.name,
            }
        ).insert(ignore_permissions=True)
        return str(customer.name), str(price_list.name)

    def test_multi_invoice_partial_write_off_and_native_reversal(self) -> None:
        for account in ("Debtors - _TC", "Sales - _TC", "Cost of Goods Sold - _TC"):
            self.assertTrue(frappe.db.exists("Account", account), account)
        suffix = frappe.generate_hash(length=10)
        customer, price_list = self._new_customer_and_price_list(suffix)
        first = self._new_invoice(customer, price_list, 100)
        second = self._new_invoice(customer, price_list, 200)
        entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Journal Entry",
                    "company": self.company,
                    "posting_date": frappe.utils.today(),
                    "voucher_type": "Write Off Entry",
                    "write_off_based_on": "Accounts Receivable",
                    "write_off_amount": 140,
                    "accounts": [
                        {
                            "account": "Cost of Goods Sold - _TC",
                            "debit_in_account_currency": 140,
                            "cost_center": "Main - _TC",
                            "department": self.department,
                        },
                        {
                            "account": "Debtors - _TC",
                            "party_type": "Customer",
                            "party": customer,
                            "credit_in_account_currency": 40,
                            "reference_type": "Sales Invoice",
                            "reference_name": first.name,
                        },
                        {
                            "account": "Debtors - _TC",
                            "party_type": "Customer",
                            "party": customer,
                            "credit_in_account_currency": 100,
                            "reference_type": "Sales Invoice",
                            "reference_name": second.name,
                        },
                    ],
                }
            ),
        ).insert()
        entry = self._approve_and_submit(entry)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", first.name, "outstanding_amount")), 60)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", second.name, "outstanding_amount")), 100)
        for invoice, amount in ((first, -40), (second, -100)):
            entries = frappe.get_all(
                "Payment Ledger Entry",
                filters={
                    "voucher_type": "Journal Entry",
                    "voucher_no": entry.name,
                    "against_voucher_type": "Sales Invoice",
                    "against_voucher_no": invoice.name,
                },
                fields=["name", "amount", "delinked"],
            )
            self.assertEqual(len(entries), 1)
            self.assertEqual(float(entries[0].amount), amount)
            self.assertFalse(entries[0].delinked)
        entry = apply_workflow(entry, "Cancel Journal Entry")
        self.assertEqual(entry.docstatus, 2)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", first.name, "outstanding_amount")), 100)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", second.name, "outstanding_amount")), 200)

    def test_changed_invoice_balance_after_approval_requires_new_review(self) -> None:
        suffix = frappe.generate_hash(length=10)
        customer, price_list = self._new_customer_and_price_list(suffix)
        invoice = self._new_invoice(customer, price_list, 100)
        entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Journal Entry",
                    "company": self.company,
                    "posting_date": frappe.utils.today(),
                    "voucher_type": "Write Off Entry",
                    "write_off_based_on": "Accounts Receivable",
                    "write_off_amount": 40,
                    "accounts": [
                        {"account": "Cost of Goods Sold - _TC", "debit_in_account_currency": 40},
                        {
                            "account": "Debtors - _TC",
                            "party_type": "Customer",
                            "party": customer,
                            "credit_in_account_currency": 40,
                            "reference_type": "Sales Invoice",
                            "reference_name": invoice.name,
                        },
                    ],
                }
            ),
        ).insert()
        frappe.set_user(self.maker)
        entry = apply_workflow(entry, "Send Journal Entry for Review")
        frappe.set_user(self.checker)
        entry = apply_workflow(entry, "Review Journal Entry")
        frappe.set_user(self.approver)
        entry = apply_workflow(entry, "Approve Journal Entry")
        # Simulate a concurrent, already-committed source balance change. This
        # isolates approval snapshot drift while keeping the allocation in range.
        frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 90, update_modified=False)
        frappe.set_user(self.checker)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(entry, "Submit Journal Entry")
        frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 100, update_modified=False)
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name})
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Ledger Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name}
            )
        )

    def test_over_allocation_and_spoofed_generated_fields_are_denied(self) -> None:
        suffix = frappe.generate_hash(length=10)
        customer, price_list = self._new_customer_and_price_list(suffix)
        invoice = self._new_invoice(customer, price_list, 100)
        entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Journal Entry",
                    "company": self.company,
                    "posting_date": frappe.utils.today(),
                    "voucher_type": "Write Off Entry",
                    "write_off_based_on": "Accounts Receivable",
                    "write_off_amount": 100,
                    "accounts": [
                        {"account": "Cost of Goods Sold - _TC", "debit_in_account_currency": 100},
                        {
                            "account": "Debtors - _TC",
                            "party_type": "Customer",
                            "party": customer,
                            "credit_in_account_currency": 100,
                            "reference_type": "Sales Invoice",
                            "reference_name": invoice.name,
                        },
                    ],
                }
            ),
        )
        entry.insert()
        frappe.set_user(self.maker)
        entry = apply_workflow(entry, "Send Journal Entry for Review")
        frappe.set_user(self.checker)
        entry = apply_workflow(entry, "Review Journal Entry")
        frappe.set_user(self.approver)
        entry = apply_workflow(entry, "Approve Journal Entry")
        # A newly committed payment reduces the balance below this allocation.
        frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 90, update_modified=False)
        frappe.set_user(self.checker)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(entry, "Submit Journal Entry")
        frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 100, update_modified=False)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 100)
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name})
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Ledger Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name}
            )
        )

        entry.reload()
        entry.set("is_system_generated", 1)
        entry.set("approval_source_doctype", "Bank Transaction")
        entry.set("approval_source_name", "USER-SPOOFED-SOURCE")
        entry.set("approval_source_action", "bank_reconciliation")
        entry.set("approval_source_proof", "USER-SPOOFED-PROOF")
        with self.assertRaises(frappe.ValidationError):
            workflow._lock_and_validate_ar_sources(entry)

    def test_receivable_write_off_posts_and_restores_native_invoice_balance(self) -> None:
        self.assertTrue(frappe.db.exists("Company", "_Test Company"))
        self.company = "_Test Company"
        for account in ("Debtors - _TC", "Sales - _TC", "Cost of Goods Sold - _TC"):
            self.assertTrue(frappe.db.exists("Account", account), account)
        self.assertTrue(frappe.db.exists("Cost Center", "Main - _TC"))
        self.assertTrue(frappe.db.exists("Item", "_Test Item"))
        thai_settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == self.company for row in thai_settings.company_accounts):
            thai_settings.append("company_accounts", {"company": self.company})
            thai_settings.save(ignore_permissions=True)

        suffix = frappe.generate_hash(length=10)
        price_list = frappe.get_doc(
            {
                "doctype": "Price List",
                "price_list_name": f"_Test Write Off Selling {suffix}",
                "selling": 1,
                "enabled": 1,
                "currency": "INR",
            }
        ).insert(ignore_permissions=True)
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"_Test Write Off Customer {suffix}",
                "customer_code": f"T-WRITEOFF-{suffix}",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Rest Of The World",
                "default_currency": "INR",
                "default_price_list": price_list.name,
            }
        ).insert(ignore_permissions=True)
        invoice = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "company": self.company,
                "customer": customer.name,
                "currency": "INR",
                "conversion_rate": 1,
                "selling_price_list": price_list.name,
                "price_list_currency": "INR",
                "plc_conversion_rate": 1,
                "debit_to": "Debtors - _TC",
                "update_stock": 0,
                "items": [
                    {
                        "item_code": "_Test Item",
                        "qty": 1,
                        "rate": 100,
                        "price_list_rate": 100,
                        "income_account": "Sales - _TC",
                        "expense_account": "Cost of Goods Sold - _TC",
                        "cost_center": "Main - _TC",
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        invoice.submit()
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(float(invoice.outstanding_amount), 100)

        frappe.set_user(self.maker)
        entry = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Journal Entry",
                    "company": self.company,
                    "posting_date": frappe.utils.today(),
                    "voucher_type": "Write Off Entry",
                    "write_off_based_on": "Accounts Receivable",
                    "write_off_amount": 100,
                    "user_remark": f"_Test receivable write off {suffix}",
                    "accounts": [
                        {
                            "account": "Cost of Goods Sold - _TC",
                            "debit_in_account_currency": 100,
                            "cost_center": "Main - _TC",
                            "department": self.department,
                        },
                        {
                            "account": "Debtors - _TC",
                            "party_type": "Customer",
                            "party": customer.name,
                            "credit_in_account_currency": 100,
                            "reference_type": "Sales Invoice",
                            "reference_name": invoice.name,
                            "department": self.department,
                        },
                    ],
                }
            ),
        ).insert()
        self.assertEqual(entry.get("voucher_type"), "Write Off Entry")
        self.assertEqual(entry.get("write_off_based_on"), "Accounts Receivable")
        self.assertEqual(entry.get("accounts")[1].get("reference_name"), invoice.name)
        with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
            entry.submit()
        entry.reload()
        self.assertEqual(entry.docstatus, 0)
        self.assertEqual(entry.get("workflow_state"), "Journal Entry Draft")
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name})
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Ledger Entry", {"voucher_type": "Journal Entry", "voucher_no": entry.name}
            )
        )
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 100)
        entry = apply_workflow(entry, "Send Journal Entry for Review")
        self.assertEqual(entry.approval_maker_user, self.maker)
        frappe.set_user(self.checker)
        entry = apply_workflow(entry, "Review Journal Entry")
        self.assertEqual(entry.approval_checker_user, self.checker)
        self.assertTrue(entry.approval_checker_signature)
        frappe.set_user(self.approver)
        entry = apply_workflow(entry, "Approve Journal Entry")
        self.assertEqual(entry.approval_approver_user, self.approver)
        self.assertTrue(entry.approval_approver_signature)
        self.assertEqual(entry.get("voucher_type"), "Write Off Entry")
        self.assertEqual(entry.get("accounts")[1].get("reference_name"), invoice.name)
        frappe.set_user(self.checker)
        entry = apply_workflow(entry, "Submit Journal Entry")
        self.assertEqual(entry.docstatus, 1)
        posted_gl = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Journal Entry", "voucher_no": entry.name, "is_cancelled": 0},
            fields=["name", "account", "debit", "credit"],
        )
        self.assertEqual(
            sorted((row.account, float(row.debit), float(row.credit)) for row in posted_gl),
            [("Cost of Goods Sold - _TC", 100, 0), ("Debtors - _TC", 0, 100)],
        )
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0)
        ple_filters = {
            "voucher_type": "Journal Entry",
            "voucher_no": entry.name,
            "against_voucher_type": "Sales Invoice",
            "against_voucher_no": invoice.name,
        }
        posted_ple = frappe.get_all(
            "Payment Ledger Entry", filters=ple_filters, fields=["name", "amount", "delinked"]
        )
        self.assertEqual(len(posted_ple), 1)
        self.assertEqual(float(posted_ple[0].amount), -100)
        self.assertFalse(posted_ple[0].delinked)
        entry = apply_workflow(entry, "Cancel Journal Entry")
        self.assertEqual(entry.docstatus, 2)
        self.assertEqual(float(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 100)
        canceled_gl = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Journal Entry", "voucher_no": entry.name},
            fields=["name", "account", "debit", "credit", "is_cancelled"],
        )
        for row in posted_gl:
            self.assertIn(row.name, {item.name for item in canceled_gl})
        for account in ("Cost of Goods Sold - _TC", "Debtors - _TC"):
            self.assertEqual(
                round(
                    sum(
                        float(row.debit) - float(row.credit) for row in canceled_gl if row.account == account
                    ),
                    2,
                ),
                0,
            )
        canceled_ple = frappe.get_all(
            "Payment Ledger Entry", filters=ple_filters, fields=["name", "amount", "delinked"]
        )
        self.assertIn(posted_ple[0].name, {row.name for row in canceled_ple})
        if is_immutable_ledger_enabled():
            self.assertEqual(
                round(
                    sum(float(row.debit) - float(row.credit) for row in canceled_gl if not row.is_cancelled),
                    2,
                ),
                0,
            )
            self.assertEqual(round(sum(float(row.amount) for row in canceled_ple if not row.delinked), 2), 0)
        else:
            self.assertFalse([row for row in canceled_gl if not row.is_cancelled])
            self.assertFalse([row for row in canceled_ple if not row.delinked])
