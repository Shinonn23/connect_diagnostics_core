# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as adapter


class TestSalesInvoiceCreditWorkflowIntegration(IntegrationTestCase):
    def _prepare_sales_fixture(self) -> tuple[str, str]:
        suffix = frappe.generate_hash(length=8)
        settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == "_Test Company" for row in settings.company_accounts):
            settings.append(
                "company_accounts",
                {
                    "company": "_Test Company",
                    "sales_tax_account": "_Test Account VAT - _TC",
                    "purchase_tax_account": "_Test Account VAT - _TC",
                },
            )
            settings.save(ignore_permissions=True)
        price_list = frappe.get_doc(
            {
                "doctype": "Price List",
                "price_list_name": f"_Test Credit Selling {suffix}",
                "selling": 1,
                "enabled": 1,
                "currency": "INR",
            }
        ).insert(ignore_permissions=True)
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"_Test Credit Customer {suffix}",
                "customer_code": f"T-CREDIT-{suffix}",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Rest Of The World",
                "default_currency": "INR",
                "default_price_list": price_list.name,
            }
        ).insert(ignore_permissions=True)
        return customer.name, price_list.name

    def _new_invoice(self, customer: str, price_list: str) -> Document:
        return frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "company": "_Test Company",
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
                        "rate": 100,
                        "price_list_rate": 100,
                        "income_account": "Sales - _TC",
                        "expense_account": "Cost of Goods Sold - _TC",
                        "cost_center": "Main - _TC",
                    }
                ],
            }
        )

    def _make_user(self, label: str, roles: tuple[str, ...]) -> str:
        email = f"{label}-{frappe.generate_hash(length=8)}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": label,
                "enabled": 1,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
        user.add_roles(*roles)
        return user.name

    def _make_employee(self, label: str, user: str) -> str:
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": label,
                    "employee_name": label,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": today(),
                    "company": "_Test Company",
                    "status": "Active",
                    "employment_type": "Full-time",
                    "user_id": user,
                    "approval_signature": "/files/test-approval-signature.png",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _post_credit_note_via_workflow(self, credit_note: Document) -> tuple[Document, str, str, str]:
        maker = self._make_user("maker-credit", ("Sales User", "Accounts User", "Item Manager"))
        reviewer = self._make_user(
            "review-credit", ("Sales Manager", "Accounts User", "Stock User", "Item Manager")
        )
        approver = self._make_user(
            "approve-credit", ("C-Level Approver", "Accounts User", "Stock User", "Item Manager")
        )
        executor = self._make_user(
            "execute-credit",
            ("Sales Manager", "Accounts Manager", "Stock User", "Item Manager"),
        )
        self._make_employee("review-credit", reviewer)
        self._make_employee("approve-credit", approver)

        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(maker)
            frappe.clear_cache(user=maker)
            credit_note = apply_workflow(credit_note, "Send Sales Invoice Credit for Review")
            frappe.set_user(reviewer)
            frappe.clear_cache(user=reviewer)
            credit_note = apply_workflow(credit_note, "Review Sales Invoice Credit")
            frappe.set_user(approver)
            frappe.clear_cache(user=approver)
            credit_note = apply_workflow(credit_note, "Approve Sales Invoice Credit")
            frappe.set_user(executor)
            frappe.clear_cache(user=executor)
            credit_note = apply_workflow(credit_note, "Post Sales Invoice Credit")
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request
        return credit_note, maker, reviewer, approver

    def test_hooks_register_lifecycle_guards_and_tasks(self) -> None:
        events = hooks.doc_events["Sales Invoice"]
        module = "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow"
        self.assertIn(module + ".validate_approval_fields", [events["validate"]])
        self.assertIn(module + ".validate_before_submit", events["before_submit"])
        methods = {entry["method"] for entry in hooks.workflow_methods}
        self.assertIn(f"{module}.capture_maker", methods)
        self.assertIn(f"{module}.capture_review", methods)
        self.assertIn(f"{module}.capture_approval", methods)
        self.assertIn(f"{module}.authorize_submit_transition", methods)
        self.assertIn(f"{module}.authorize_cancel_transition", methods)
        self.assertEqual(events["before_cancel"], f"{module}.validate_before_cancel")
        for method in methods:
            if method.startswith(module):
                self.assertTrue(callable(frappe.get_attr(method)))

    def test_fixture_matches_the_approved_actor_route(self) -> None:
        root = Path(__file__).parents[4]
        workflows = json.loads((root / "connect_diagnostics_core" / "fixtures" / "workflow.json").read_text())
        route = next(row for row in workflows if row["document_type"] == "Sales Invoice")
        transitions = {
            (
                row["state"],
                row["action"],
                row["next_state"],
                row["allowed"],
                row["allow_self_approval"],
                row.get("transition_tasks", ""),
            )
            for row in route["transitions"]
        }
        condition = "doc.is_return and doc.return_against"
        self.assertIn(
            (
                "Sales Invoice Draft",
                "Send Sales Invoice Credit for Review",
                "Sales Invoice Credit Pending Review",
                "Sales User",
                1,
                "Connect Sales Invoice Credit Send",
            ),
            transitions,
        )
        send_roles = {row[3] for row in transitions if row[1] == "Send Sales Invoice Credit for Review"}
        self.assertEqual(send_roles, {"Sales User"})
        expected_protected = {
            "Review Sales Invoice Credit": ("Sales Manager", "Connect Sales Invoice Credit Review"),
            "Approve Sales Invoice Credit": (
                "C-Level Approver",
                "Connect Sales Invoice Credit Approve",
            ),
            "Post Sales Invoice Credit": ("Sales Manager", "Connect Sales Invoice Credit Post"),
        }
        for action, (role, task) in expected_protected.items():
            row = next(item for item in route["transitions"] if item["action"] == action)
            self.assertEqual(row["allowed"], role)
            self.assertEqual(row["allow_self_approval"], 0)
            self.assertEqual(row["condition"], condition)
            self.assertEqual(row["transition_tasks"], task)

        cancel = next(
            item for item in route["transitions"] if item["action"] == "Cancel Sales Invoice Credit"
        )
        self.assertEqual(cancel["allowed"], "Sales Manager")
        self.assertEqual(cancel["allow_self_approval"], 0)
        self.assertEqual(cancel["transition_tasks"], "Connect Sales Invoice Credit Cancel")

    def test_ordinary_invoice_is_outside_route(self) -> None:
        doc = Document(
            {
                "doctype": "Sales Invoice",
                "name": "NEW-SI",
                "is_return": 0,
                "return_against": None,
            }
        )
        self.assertFalse(adapter.is_credit_note(doc))

    def test_installed_workflow_preserves_native_post_and_cancel_ownership(self) -> None:
        workflow = frappe.get_doc("Workflow", "Connect Sales Invoice Credit Blueprint")
        self.assertEqual(workflow.document_type, "Sales Invoice")
        transitions = {row.action: row for row in workflow.transitions}

        self.assertEqual(transitions["Post Sales Invoice Credit"].allowed, "Sales Manager")
        self.assertEqual(transitions["Cancel Sales Invoice Credit"].allowed, "Sales Manager")
        self.assertEqual(
            transitions["Post Sales Invoice Credit"].transition_tasks,
            "Connect Sales Invoice Credit Post",
        )
        self.assertEqual(
            transitions["Cancel Sales Invoice Credit"].transition_tasks,
            "Connect Sales Invoice Credit Cancel",
        )

        events = hooks.doc_events["Sales Invoice"]
        module = "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow"
        self.assertEqual(events["before_cancel"], module + ".validate_before_cancel")
        methods = {entry["method"] for entry in hooks.workflow_methods}
        self.assertIn(module + ".authorize_submit_transition", methods)
        self.assertIn(module + ".authorize_cancel_transition", methods)

    def test_ordinary_invoice_can_submit_and_cancel_with_native_gl(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        invoice = self._new_invoice(customer, price_list).insert(ignore_permissions=True)

        invoice.submit()
        self.assertEqual(invoice.docstatus, 1)
        self.assertGreater(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0},
            ),
            0,
        )
        self.assertEqual(
            frappe.db.count(
                "Stock Ledger Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0},
            ),
            0,
        )

        invoice.cancel()
        self.assertEqual(invoice.docstatus, 2)
        self.assertEqual(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0},
            ),
            0,
        )

    def test_approved_partial_price_credit_posts_native_gl_without_sle(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        credit_note = make_return_doc("Sales Invoice", source.name)
        credit_note.items[0].qty = -0.4
        credit_note.insert(ignore_permissions=True)

        credit_note, maker, reviewer, approver = self._post_credit_note_via_workflow(credit_note)

        credit_note.reload()
        self.assertEqual(credit_note.docstatus, 1)
        self.assertEqual(credit_note.approval_maker_user, maker)
        self.assertEqual(credit_note.approval_reviewer_user, reviewer)
        self.assertEqual(credit_note.approval_authorized_user, approver)
        self.assertLess(credit_note.outstanding_amount, 0)
        self.assertGreater(
            frappe.db.count(
                "GL Entry",
                {
                    "voucher_type": "Sales Invoice",
                    "voucher_no": credit_note.name,
                    "is_cancelled": 0,
                },
            ),
            0,
        )
        self.assertEqual(
            frappe.db.count(
                "Stock Ledger Entry",
                {
                    "voucher_type": "Sales Invoice",
                    "voucher_no": credit_note.name,
                    "is_cancelled": 0,
                },
            ),
            0,
        )

    def test_approved_physical_return_posts_native_inward_sle(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        receipt = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": "_Test Company",
                "to_warehouse": "_Test Warehouse - _TC",
                "items": [
                    {
                        "item_code": "_Test Item",
                        "t_warehouse": "_Test Warehouse - _TC",
                        "qty": 5,
                        "basic_rate": 50,
                        "expense_account": "Stock Adjustment - _TC",
                        "cost_center": "Main - _TC",
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        receipt.submit()

        source = self._new_invoice(customer, price_list)
        source.update_stock = 1
        source.items[0].warehouse = "_Test Warehouse - _TC"
        source.insert(ignore_permissions=True)
        source.submit()
        credit_note = make_return_doc("Sales Invoice", source.name)
        credit_note.insert(ignore_permissions=True)

        credit_note, _, _, _ = self._post_credit_note_via_workflow(credit_note)
        credit_note.reload()
        self.assertEqual(credit_note.docstatus, 1)
        ledger_rows = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Sales Invoice",
                "voucher_no": credit_note.name,
                "is_cancelled": 0,
            },
            fields=["actual_qty"],
        )
        self.assertTrue(ledger_rows)
        self.assertGreater(sum(row.actual_qty for row in ledger_rows), 0)
        self.assertGreater(
            frappe.db.count(
                "GL Entry",
                {
                    "voucher_type": "Sales Invoice",
                    "voucher_no": credit_note.name,
                    "is_cancelled": 0,
                },
            ),
            0,
        )

    def test_native_cumulative_return_limit_rejects_over_credit(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        first_credit = make_return_doc("Sales Invoice", source.name)
        first_credit.items[0].qty = -0.6
        first_credit.insert(ignore_permissions=True)
        first_credit, _, _, _ = self._post_credit_note_via_workflow(first_credit)
        self.assertEqual(first_credit.docstatus, 1)

        excessive_credit = make_return_doc("Sales Invoice", source.name)
        excessive_credit.items[0].qty = -0.5
        with self.assertRaises(frappe.ValidationError):
            excessive_credit.insert(ignore_permissions=True)
        self.assertEqual(
            frappe.db.count(
                "GL Entry",
                {
                    "voucher_type": "Sales Invoice",
                    "voucher_no": excessive_credit.name,
                    "is_cancelled": 0,
                },
            ),
            0,
        )

    def test_return_resubmit_and_reject_never_post_accounting_effects(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        maker = self._make_user("return-maker", ("Sales User", "Accounts User", "Item Manager"))
        reviewer = self._make_user(
            "return-reviewer", ("Sales Manager", "Accounts User", "Stock User", "Item Manager")
        )
        approver = self._make_user(
            "return-approver",
            ("C-Level Approver", "Accounts User", "Stock User", "Item Manager"),
        )
        self._make_employee("return-reviewer", reviewer)
        self._make_employee("return-approver", approver)
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(maker)
            frappe.clear_cache(user=maker)
            credit_note = apply_workflow(credit_note, "Send Sales Invoice Credit for Review")
            frappe.set_user(reviewer)
            frappe.clear_cache(user=reviewer)
            credit_note = apply_workflow(credit_note, "Return Sales Invoice Credit")
            credit_note.reload()
            self.assertEqual(credit_note.docstatus, 0)
            self.assertEqual(credit_note.approval_maker_user, maker)
            self.assertIsNone(credit_note.approval_reviewer_user)
            self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": credit_note.name}), 0)
            self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": credit_note.name}), 0)
            frappe.set_user(maker)
            frappe.clear_cache(user=maker)
            credit_note = apply_workflow(credit_note, "Resubmit Sales Invoice Credit for Review")
            frappe.set_user(reviewer)
            frappe.clear_cache(user=reviewer)
            credit_note = apply_workflow(credit_note, "Review Sales Invoice Credit")
            frappe.set_user(approver)
            frappe.clear_cache(user=approver)
            credit_note = apply_workflow(credit_note, "Reject Sales Invoice Credit")
            credit_note.reload()
            self.assertEqual(credit_note.docstatus, 0)
            self.assertEqual(credit_note.workflow_state, "Sales Invoice Credit Returned")
            self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": credit_note.name}), 0)
            self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": credit_note.name}), 0)
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request

    def test_posted_credit_cancel_reverses_and_amendment_requires_fresh_approval(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        credit_note, _, _, _ = self._post_credit_note_via_workflow(credit_note)
        credit_note.reload()
        manager = self._make_user(
            "cancel-manager",
            ("Sales Manager", "Accounts Manager", "Stock User", "Item Manager"),
        )
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(manager)
            frappe.clear_cache(user=manager)
            credit_note = apply_workflow(credit_note, "Cancel Sales Invoice Credit")
            credit_note.reload()
            self.assertEqual(credit_note.docstatus, 2)
            self.assertEqual(
                frappe.db.count("GL Entry", {"voucher_no": credit_note.name, "is_cancelled": 0}), 0
            )
            amended = frappe.copy_doc(credit_note)
            amended.docstatus = 0
            amended.amended_from = credit_note.name
            amended.insert()
            self.assertEqual(amended.docstatus, 0)
            with self.assertRaises(frappe.ValidationError):
                amended.submit()
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request
