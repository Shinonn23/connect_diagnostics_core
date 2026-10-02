# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as adapter


def _post_credit_note_separately(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    credit_note: str,
    source: str,
    user: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        # Establish an ordinary REPEATABLE READ snapshot before serializing on the source.
        frappe.db.sql("SELECT qty FROM `tabSales Invoice Item` WHERE parent=%s", (source,))
        doc = frappe.get_doc("Sales Invoice", credit_note)
        frappe.local.request = frappe._dict()
        frappe.set_user(user)
        barrier.wait(timeout=15)
        apply_workflow(doc, "Post Sales Invoice Credit")
        frappe.db.commit()  # nosemgrep - publish the independent native Credit Note race result
        return "posted"
    except (frappe.ValidationError, frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.db.rollback()
        return "denied"
    finally:
        frappe.destroy()


class TestSalesInvoiceCreditWorkflowIntegration(IntegrationTestCase):
    def _ledger_snapshot(self, invoice: Document) -> dict[str, list[tuple[object, ...]]]:
        ledger_fields = {
            "GL Entry": ("name", "debit", "credit", "is_cancelled"),
            "Stock Ledger Entry": ("name", "actual_qty", "is_cancelled"),
            "Payment Ledger Entry": ("name", "amount", "delinked"),
        }
        return {
            doctype: sorted(
                tuple(row.get(field) for field in fields)
                for row in frappe.get_all(
                    doctype,
                    filters={"voucher_type": "Sales Invoice", "voucher_no": invoice.name},
                    fields=list(fields),
                )
            )
            for doctype, fields in ledger_fields.items()
        }

    def _approval_snapshot(self, invoice: Document) -> dict[str, object]:
        fields = ("workflow_state", "docstatus", *sorted(adapter.APPROVAL_FIELDS))
        return dict(frappe.db.get_value("Sales Invoice", invoice.name, fields, as_dict=True))

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

    def _fractional_item(self) -> tuple[str, str]:
        suffix = frappe.generate_hash(length=8)
        uom = frappe.get_doc(
            {"doctype": "UOM", "uom_name": f"_Test Credit Unit {suffix}", "must_be_whole_number": 0}
        ).insert(ignore_permissions=True)
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        assert item_group
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": f"_Test Fractional Credit {suffix}",
                "item_name": f"_Test Fractional Credit {suffix}",
                "item_group": item_group,
                "stock_uom": uom.name,
                "is_stock_item": 0,
            }
        ).insert(ignore_permissions=True)
        return str(item.name), str(uom.name)

    def _new_invoice(
        self, customer: str, price_list: str, *, item_code: str = "_Test Item", uom: str | None = None
    ) -> SalesInvoice:
        return cast(
            SalesInvoice,
            frappe.get_doc(
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
                            "item_code": item_code,
                            "uom": uom,
                            "qty": 1,
                            "rate": 100,
                            "price_list_rate": 100,
                            "income_account": "Sales - _TC",
                            "expense_account": "Cost of Goods Sold - _TC",
                            "cost_center": "Main - _TC",
                        }
                    ],
                }
            ),
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

    def _post_credit_note_via_workflow(
        self, credit_note: Document, *, maker_role: str = "Sales User", post: bool = True
    ) -> tuple[Document, str, str, str]:
        maker_roles = (
            (maker_role, "Accounts User", "Item Manager")
            if maker_role == "Sales User"
            else ("Accounts User", "Item Manager")
        )
        maker = self._make_user("maker-credit", maker_roles)
        reviewer = self._make_user(
            "review-credit", ("Sales Manager", "Accounts User", "Stock User", "Item Manager")
        )
        approver = self._make_user("approve-credit", ("Accounts Manager", "Stock User", "Item Manager"))
        executor = (
            self._make_user(
                "execute-credit",
                ("Accounts Manager", "Stock User", "Item Manager"),
            )
            if post
            else ""
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
            if post:
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
        self.assertIn(module + ".validate_approval_fields", events["validate"])
        self.assertIn(module + ".validate_before_submit", events["before_submit"])
        methods = {entry["method"] for entry in hooks.workflow_methods}
        self.assertIn(f"{module}.capture_maker", methods)
        self.assertIn(f"{module}.capture_review", methods)
        self.assertIn(f"{module}.capture_approval", methods)
        self.assertIn(f"{module}.authorize_submit_transition", methods)
        self.assertIn(f"{module}.authorize_cancel_transition", methods)
        self.assertEqual(
            events["before_cancel"],
            [
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_sales_invoice_cancel",
                f"{module}.validate_before_cancel",
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
            ],
        )
        self.assertEqual(events["before_update_after_submit"], f"{module}.validate_after_submit_update")
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
        self.assertEqual(send_roles, {"Sales User", "Accounts User"})
        expected_protected = {
            "Review Sales Invoice Credit": ("Sales Manager", "Connect Sales Invoice Credit Review"),
            "Approve Sales Invoice Credit": (
                "Accounts Manager",
                "Connect Sales Invoice Credit Approve",
            ),
            "Post Sales Invoice Credit": ("Accounts Manager", "Connect Sales Invoice Credit Post"),
        }
        for action, (role, task) in expected_protected.items():
            row = next(item for item in route["transitions"] if item["action"] == action)
            self.assertEqual(row["allowed"], role)
            self.assertEqual(row["allow_self_approval"], 0)
            self.assertEqual(row["condition"], condition)
            self.assertEqual(row["transition_tasks"], task)

        correction = next(
            row
            for row in route["transitions"]
            if row["action"] == "Return Sales Invoice Credit"
            and row["state"] == "Sales Invoice Credit Approved"
        )
        self.assertEqual(correction["next_state"], "Sales Invoice Credit Returned")
        self.assertEqual(correction["allowed"], "Sales Manager")
        self.assertEqual(correction["allow_self_approval"], 0)
        self.assertEqual(correction["transition_tasks"], "Connect Sales Invoice Credit Return")

        cancel = next(
            item for item in route["transitions"] if item["action"] == "Cancel Sales Invoice Credit"
        )
        self.assertEqual(cancel["allowed"], "Sales Manager")
        self.assertEqual(cancel["allow_self_approval"], 0)
        self.assertEqual(cancel["transition_tasks"], "Authorize Sales Invoice Credit Cancel")

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

        self.assertEqual(transitions["Post Sales Invoice Credit"].allowed, "Accounts Manager")
        self.assertEqual(transitions["Cancel Sales Invoice Credit"].allowed, "Sales Manager")
        self.assertEqual(
            transitions["Post Sales Invoice Credit"].transition_tasks,
            "Connect Sales Invoice Credit Post",
        )
        self.assertEqual(
            transitions["Cancel Sales Invoice Credit"].transition_tasks,
            "Authorize Sales Invoice Credit Cancel",
        )

        events = hooks.doc_events["Sales Invoice"]
        module = "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow"
        self.assertEqual(
            events["before_cancel"],
            [
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_sales_invoice_cancel",
                module + ".validate_before_cancel",
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
            ],
        )
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

    def test_saved_credit_note_direct_submit_and_cancel_do_not_post(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        before = self._ledger_snapshot(credit_note)
        before_approval = self._approval_snapshot(credit_note)
        self.assertEqual(before, {"GL Entry": [], "Stock Ledger Entry": []})
        credit_note.set("workflow_state", "Sales Invoice Submitted")
        with self.assertRaises(frappe.ValidationError):
            credit_note.save(ignore_permissions=True)
        credit_note.reload()
        self.assertEqual(self._ledger_snapshot(credit_note), before)
        self.assertEqual(self._approval_snapshot(credit_note), before_approval)
        executor = self._make_user("direct-post-credit", ("Accounts Manager", "Item Manager"))
        manager = self._make_user(
            "direct-cancel-credit", ("Sales Manager", "Accounts Manager", "Item Manager")
        )
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(executor)
            credit_note.set("workflow_state", "Sales Invoice Submitted")
            with self.assertRaises(frappe.ValidationError):
                credit_note.submit()
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request
        self.assertEqual(credit_note.reload().docstatus, 0)
        self.assertEqual(self._ledger_snapshot(credit_note), before)
        self.assertEqual(self._approval_snapshot(credit_note), before_approval)

        credit_note, _, _, _ = self._post_credit_note_via_workflow(credit_note)
        posted = self._ledger_snapshot(credit_note)
        posted_approval = self._approval_snapshot(credit_note)
        self.assertTrue(posted["GL Entry"])
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(manager)
            credit_note.set("workflow_state", "Sales Invoice Cancelled")
            with self.assertRaises(frappe.ValidationError):
                credit_note.cancel()
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request
        self.assertEqual(credit_note.reload().docstatus, 1)
        self.assertEqual(self._ledger_snapshot(credit_note), posted)
        self.assertEqual(self._approval_snapshot(credit_note), posted_approval)

    def test_approved_credit_note_native_posting_mutations_are_denied_before_ledgers(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        self.assertIsNotNone(source.name)
        credit_note = make_return_doc("Sales Invoice", cast(str, source.name)).insert(ignore_permissions=True)
        credit_note, _maker, _reviewer, approver = self._post_credit_note_via_workflow(
            credit_note, post=False
        )
        before = self._ledger_snapshot(credit_note)
        self.assertEqual(before, {"GL Entry": [], "Stock Ledger Entry": [], "Payment Ledger Entry": []})
        mutations = (
            ("debit_to", "Sales - _TC", None),
            ("is_opening", "Yes", None),
            ("additional_discount_account", "Sales - _TC", None),
            ("loyalty_redemption_account", "Sales - _TC", None),
            ("unrealized_profit_loss_account", "Sales - _TC", None),
            ("cost_center", "_FORGED Cost Center", None),
            ("discount_account", "_FORGED Discount Account", "items"),
        )
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(approver)
            frappe.clear_cache(user=approver)
            for field, value, child_table in mutations:
                with self.subTest(field=field):
                    if child_table:
                        credit_note.get(child_table)[0].set(field, value)
                    else:
                        credit_note.set(field, value)
                    with self.assertRaises(frappe.ValidationError):
                        apply_workflow(credit_note, "Post Sales Invoice Credit")
                    credit_note.reload()
                    self.assertEqual(credit_note.docstatus, 0)
                    self.assertEqual(credit_note.get("workflow_state"), "Sales Invoice Credit Approved")
                    self.assertEqual(self._ledger_snapshot(credit_note), before)
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request

    def test_submitted_credit_note_state_update_is_denied_without_ledger_change(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        credit_note, _, _, _ = self._post_credit_note_via_workflow(credit_note)
        posted = self._ledger_snapshot(credit_note)
        posted_approval = self._approval_snapshot(credit_note)

        for forged_state in ("Sales Invoice Credit Approved", "Sales Invoice Cancelled"):
            with self.subTest(forged_state=forged_state):
                credit_note.set("workflow_state", forged_state)
                with self.assertRaises(frappe.ValidationError):
                    credit_note.save(ignore_permissions=True)
                credit_note.reload()
                self.assertEqual(self._approval_snapshot(credit_note), posted_approval)
                self.assertEqual(self._ledger_snapshot(credit_note), posted)

        credit_note.set("po_no", "_Test Credit PO")
        credit_note.save(ignore_permissions=True)
        self.assertEqual(credit_note.reload().get("po_no"), "_Test Credit PO")
        self.assertEqual(self._ledger_snapshot(credit_note), posted)

    def test_submitted_credit_note_account_changes_cannot_repost_gl(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        credit_note, _, _, _ = self._post_credit_note_via_workflow(credit_note)
        posted = self._ledger_snapshot(credit_note)
        posted_approval = self._approval_snapshot(credit_note)
        original_accounts = {
            "income_account": credit_note.get("items")[0].get("income_account"),
            "expense_account": credit_note.get("items")[0].get("expense_account"),
            "additional_discount_account": credit_note.get("additional_discount_account"),
        }
        alternatives = {}
        for key, sibling in (
            ("income_account", "Sales - _TC"),
            ("expense_account", "Cost of Goods Sold - _TC"),
        ):
            parent_account = frappe.db.get_value("Account", sibling, "parent_account")
            assert isinstance(parent_account, str)
            alternatives[key] = (
                frappe.get_doc(
                    {
                        "doctype": "Account",
                        "account_name": f"_Test Credit {key} {frappe.generate_hash(length=8)}",
                        "parent_account": parent_account,
                        "company": "_Test Company",
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )
        alternatives["additional_discount_account"] = alternatives["income_account"]
        account_manager = self._make_user("repost-credit", ("Accounts Manager", "Item Manager"))
        prior_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict()
            frappe.set_user(account_manager)
            frappe.clear_cache(user=account_manager)
            for field, alternative in alternatives.items():
                with self.subTest(field=field):
                    if field == "additional_discount_account":
                        credit_note.set(field, alternative)
                    else:
                        credit_note.get("items")[0].set(field, alternative)
                    with self.assertRaisesRegex(frappe.ValidationError, "accounting facts cannot be changed"):
                        credit_note.save()
                    credit_note.reload()
                    actual = (
                        credit_note.get(field)
                        if field == "additional_discount_account"
                        else credit_note.get("items")[0].get(field)
                    )
                    self.assertEqual(actual, original_accounts[field])
                    self.assertEqual(self._approval_snapshot(credit_note), posted_approval)
                    self.assertEqual(self._ledger_snapshot(credit_note), posted)
        finally:
            frappe.set_user("Administrator")
            if prior_request is None:
                delattr(frappe.local, "request")
            else:
                frappe.local.request = prior_request

    def test_approved_partial_price_credit_posts_native_gl_without_sle(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        item_code, uom = self._fractional_item()
        source = self._new_invoice(customer, price_list, item_code=item_code, uom=uom).insert(
            ignore_permissions=True
        )
        source.submit()
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name)
        credit_note.items[0].qty = -0.4
        credit_note.insert(ignore_permissions=True)

        credit_note, maker, reviewer, approver = self._post_credit_note_via_workflow(credit_note)

        credit_note.reload()
        self.assertEqual(credit_note.docstatus, 1)
        self.assertEqual(credit_note.get("approval_maker_user"), maker)
        self.assertEqual(credit_note.get("approval_reviewer_user"), reviewer)
        self.assertEqual(credit_note.get("approval_authorized_user"), approver)
        self.assertLess(credit_note.get("outstanding_amount"), 0)
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

    def test_concurrent_returns_serialize_current_quantity_and_cleanup_committed_fixtures(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        item_code, uom = self._fractional_item()
        source = self._new_invoice(customer, price_list, item_code=item_code, uom=uom).insert(
            ignore_permissions=True
        )
        source.submit()
        source_name = cast(str, source.name)
        credit_notes: list[str] = []
        actor_users: set[str] = set()
        manager = self._make_user("cancel-raced-credit", ("Sales Manager", "Item Manager"))
        actor_users.add(manager)
        original_tax_settings = frappe.get_single("Thai Tax Settings").as_dict().get("company_accounts")
        winner: str | None = None
        committed = False
        cancel_failure: Exception | None = None
        try:
            for _ in range(2):
                credit_note = make_return_doc("Sales Invoice", source_name)
                credit_note.items[0].qty = -0.6
                credit_note.insert(ignore_permissions=True)
                credit_note, maker, reviewer, approver = self._post_credit_note_via_workflow(
                    credit_note, post=False
                )
                credit_notes.append(str(credit_note.name))
                actor_users.update((maker, reviewer, approver))

            # Worker connections publish these exact source/doc/user fixtures, then clean them all.
            frappe.db.commit()  # nosemgrep - race workers use independent connections
            committed = True
            barrier = threading.Barrier(2)
            site = str(frappe.local.site)
            sites_path = str(frappe.local.sites_path)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _post_credit_note_separately,
                        site,
                        sites_path,
                        barrier,
                        name,
                        source_name,
                        str(frappe.db.get_value("Sales Invoice", name, "approval_authorized_user")),
                    )
                    for name in credit_notes
                ]
                results = [future.result(timeout=30) for future in futures]

            submitted = [
                name for name in credit_notes if frappe.db.get_value("Sales Invoice", name, "docstatus") == 1
            ]
            approved = [
                name
                for name in credit_notes
                if frappe.db.get_value("Sales Invoice", name, "workflow_state")
                == "Sales Invoice Credit Approved"
            ]
            self.assertEqual(sorted(results), ["denied", "posted"])
            self.assertEqual(len(submitted), 1)
            self.assertEqual(len(approved), 1)
            winner = submitted[0]
            loser = approved[0]
            self.assertTrue(self._ledger_snapshot(frappe.get_doc("Sales Invoice", winner))["GL Entry"])
            self.assertTrue(
                frappe.db.exists(
                    "Payment Ledger Entry", {"voucher_type": "Sales Invoice", "voucher_no": winner}
                )
            )
            self.assertEqual(
                self._ledger_snapshot(frappe.get_doc("Sales Invoice", loser)),
                {"GL Entry": [], "Stock Ledger Entry": [], "Payment Ledger Entry": []},
            )
        finally:
            frappe.db.rollback()
            if winner and frappe.db.exists("Sales Invoice", winner):
                frappe.local.request = frappe._dict()
                frappe.set_user(manager)
                try:
                    apply_workflow(frappe.get_doc("Sales Invoice", winner), "Cancel Sales Invoice Credit")
                except Exception as exc:
                    cancel_failure = exc
                finally:
                    frappe.set_user("Administrator")
            frappe.set_user("Administrator")
            for name in reversed(credit_notes):
                if frappe.db.exists("Sales Invoice", name):
                    frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
                for doctype in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
                    frappe.db.delete(doctype, {"voucher_type": "Sales Invoice", "voucher_no": name})
            if frappe.db.exists("Sales Invoice", source_name):
                source.reload()
                if source.docstatus == 1:
                    source.cancel()
                frappe.delete_doc("Sales Invoice", source_name, force=True, ignore_permissions=True)
            for doctype in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
                frappe.db.delete(doctype, {"voucher_type": "Sales Invoice", "voucher_no": source_name})
            employees = frappe.get_all(
                "Employee", filters={"user_id": ("in", list(actor_users))}, pluck="name"
            )
            for employee in employees:
                frappe.delete_doc("Employee", employee, force=True, ignore_permissions=True)
            for user in actor_users:
                if frappe.db.exists("User", user):
                    frappe.delete_doc("User", user, force=True, ignore_permissions=True)
            if frappe.db.exists("Item", item_code):
                frappe.delete_doc("Item", item_code, force=True, ignore_permissions=True)
            if frappe.db.exists("UOM", uom):
                frappe.delete_doc("UOM", uom, force=True, ignore_permissions=True)
            if frappe.db.exists("Customer", customer):
                frappe.delete_doc("Customer", customer, force=True, ignore_permissions=True)
            if frappe.db.exists("Price List", price_list):
                frappe.delete_doc("Price List", price_list, force=True, ignore_permissions=True)
            settings = frappe.get_single("Thai Tax Settings")
            settings.company_accounts = original_tax_settings or []
            settings.save(ignore_permissions=True)
            if committed:
                frappe.db.commit()  # nosemgrep - remove every fixture published for the race workers
            for name in credit_notes:
                self.assertFalse(frappe.db.exists("Sales Invoice", name))
                for doctype in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
                    self.assertEqual(
                        frappe.db.count(doctype, {"voucher_type": "Sales Invoice", "voucher_no": name}), 0
                    )
            self.assertFalse(frappe.db.exists("Sales Invoice", source_name))
            self.assertFalse(frappe.db.exists("Item", item_code))
            self.assertFalse(frappe.db.exists("UOM", uom))
            self.assertFalse(frappe.db.exists("Customer", customer))
            self.assertFalse(frappe.db.exists("Price List", price_list))
            for employee in employees:
                self.assertFalse(frappe.db.exists("Employee", employee))
            for user in actor_users:
                self.assertFalse(frappe.db.exists("User", user))
            if cancel_failure:
                raise AssertionError(
                    "Native workflow cancellation failed during committed fixture cleanup"
                ) from cancel_failure

    def test_accounts_user_only_maker_can_send_credit_for_review(self) -> None:
        customer, price_list = self._prepare_sales_fixture()
        source = self._new_invoice(customer, price_list).insert(ignore_permissions=True)
        source.submit()
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)

        credit_note, maker, _, _ = self._post_credit_note_via_workflow(
            credit_note, maker_role="Accounts User"
        )
        self.assertEqual(credit_note.reload().docstatus, 1)
        self.assertEqual(credit_note.get("approval_maker_user"), maker)

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
        source.set("update_stock", 1)
        source.items[0].warehouse = "_Test Warehouse - _TC"
        source.insert(ignore_permissions=True)
        source.submit()
        assert isinstance(source.name, str)
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
        item_code, uom = self._fractional_item()
        source = self._new_invoice(customer, price_list, item_code=item_code, uom=uom).insert(
            ignore_permissions=True
        )
        source.submit()
        assert isinstance(source.name, str)
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
        assert isinstance(source.name, str)
        credit_note = make_return_doc("Sales Invoice", source.name).insert(ignore_permissions=True)
        maker = self._make_user("return-maker", ("Sales User", "Accounts User", "Item Manager"))
        reviewer = self._make_user(
            "return-reviewer", ("Sales Manager", "Accounts User", "Stock User", "Item Manager")
        )
        approver = self._make_user(
            "return-approver",
            ("Accounts Manager", "Stock User", "Item Manager"),
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
            self.assertEqual(credit_note.get("approval_maker_user"), maker)
            self.assertIsNone(credit_note.get("approval_reviewer_user"))
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
        assert isinstance(source.name, str)
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
            amended.set("amended_from", credit_note.name)
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
