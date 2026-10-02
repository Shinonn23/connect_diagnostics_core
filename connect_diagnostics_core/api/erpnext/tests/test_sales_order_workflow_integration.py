# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native Sales Order Workflow checks against the installed canonical route."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder, make_delivery_note, make_sales_invoice
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from connect_diagnostics_core.api.erpnext import auto_invoice_generation, sales_order_workflow
from connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline import _task_rows, workflow_shape
from connect_diagnostics_core.setup import quotation as quotation_setup

WORKFLOW = "Connect Sales Order Blueprint"
ROLES = ("Sales User", "Sales Manager", "Accounts Manager")
APPROVAL_FIELDS = (
    "approval_revision",
    "approval_digest",
    "approval_maker_user",
    "approval_maker_at",
    "approval_reviewer_user",
    "approval_reviewer_at",
    "approval_approver_user",
    "approval_approver_at",
    "checked_by",
    "checked_at",
    "checked_signature",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
)
TASKS = {
    "Connect Sales Order Capture Maker": ["Connect Sales Order Capture Maker"],
    "Connect Sales Order Capture Review": [
        "Capture Print Action: Checked",
        "Connect Sales Order Capture Review",
    ],
    "Connect Sales Order Capture Approval": [
        "Capture Print Action: Authorized",
        "Connect Sales Order Capture Approval",
    ],
    "Connect Sales Order Clear Approval": ["Connect Sales Order Clear Approval"],
    "Connect Sales Order Submit Execution": ["Connect Sales Order Submit Execution"],
    "Connect Sales Order Cancel Execution": ["Connect Sales Order Cancel Execution"],
}


class TestSalesOrderWorkflowIntegration(IntegrationTestCase):
    """Each test owns only temporary business rows inside a DB savepoint."""

    def _preflight(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")
        fixture = Path(frappe.get_app_path("connect_diagnostics_core", "fixtures", "workflow.json"))
        expected = next(row for row in json.loads(fixture.read_text()) if row.get("name") == WORKFLOW)
        active = frappe.get_all(
            "Workflow", filters={"document_type": "Sales Order", "is_active": 1}, pluck="name"
        )
        self.assertEqual(active, [WORKFLOW], "Canonical Sales Order Workflow is not installed")
        actual = frappe.get_doc("Workflow", WORKFLOW)
        self.assertEqual(workflow_shape(actual), workflow_shape(expected))
        method_rows = frappe.get_hooks("workflow_methods")
        methods = {str(row["name"]): str(row["method"]) for row in method_rows}
        self.assertEqual(len(method_rows), len(methods), "Duplicate Workflow callback names")
        for group, callbacks in TASKS.items():
            self.assertTrue(
                frappe.db.exists("Workflow Transition Tasks", group), f"Missing task group {group}"
            )
            rows = _task_rows(frappe.get_doc("Workflow Transition Tasks", group))
            self.assertEqual(
                rows,
                [{"task": callback, "link": None, "enabled": 1, "asynchronous": 0} for callback in callbacks],
            )
            for callback in callbacks:
                self.assertIn(callback, methods, f"Missing Workflow callback {callback}")
                self.assertTrue(callable(frappe.get_attr(methods[callback])))
        for fieldname in APPROVAL_FIELDS:
            self.assertTrue(frappe.get_meta("Sales Order").has_field(fieldname), f"Missing {fieldname}")
        self.assertTrue(
            frappe.get_meta("Employee").has_field("approval_signature"),
            "Missing Employee approval_signature",
        )
        for role in (*ROLES, "Accounts User"):
            self.assertTrue(frappe.db.exists("Role", role), f"Missing role {role}")

    def _masters(self) -> None:
        required = (
            ("Company", "_Test Company"),
            ("Item", "_Test Item"),
            ("Warehouse", "_Test Warehouse - _TC"),
            ("Department", "_Test Department - _TC"),
            ("Employment Type", "Full-time"),
            ("Customer Group", "_Test Customer Group"),
            ("Territory", "_Test Territory"),
        )
        for doctype, name in required:
            self.assertTrue(frappe.db.exists(doctype, name), f"Missing native test master: {doctype}")
        self.company = "_Test Company"
        self.item = "_Test Item"
        self.warehouse = "_Test Warehouse - _TC"
        self.currency = frappe.db.get_value("Company", self.company, "default_currency")
        self.price_list = frappe.db.get_value(
            "Price List", {"enabled": 1, "selling": 1, "currency": self.currency}, "name"
        )
        self.assertTrue(self.currency and self.price_list, "Missing company currency or selling Price List")
        self.income_account = frappe.db.get_value(
            "Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name"
        )
        self.cost_center = frappe.db.get_value(
            "Cost Center", {"company": self.company, "is_group": 0}, "name"
        )
        self.assertTrue(self.income_account and self.cost_center, "Missing approved row accounts")

    def setUp(self) -> None:
        super().setUp()
        self._preflight()
        self._masters()
        self._old_user = frappe.session.user
        self._old_request = getattr(frappe.local, "request", None)
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        self._old_grants = list(grants) if grants is not None else None
        self._old_submit_flag = getattr(frappe.flags, "sales_order_submission", None)
        self._old_cancel_flag = getattr(frappe.flags, "connect_sales_order_cancellation", None)
        self._savepoint = f"so_native_{uuid4().hex}"
        frappe.db.savepoint(self._savepoint)
        try:
            frappe.local.request = frappe._dict(method="POST")
            self._create_people_and_customer()
        except Exception:
            self._restore()
            raise

    def _restore(self) -> None:
        try:
            frappe.db.rollback(save_point=self._savepoint)
        finally:
            frappe.set_user(self._old_user)
            frappe.local.request = self._old_request
            if self._old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = self._old_grants
            frappe.flags.sales_order_submission = self._old_submit_flag
            frappe.flags.connect_sales_order_cancellation = self._old_cancel_flag
            for user in getattr(self, "users", ()):
                frappe.clear_cache(user=user)
            frappe.clear_cache(doctype="Sales Order")

    def tearDown(self) -> None:
        try:
            self._restore()
        finally:
            super().tearDown()

    def _create_people_and_customer(self) -> None:
        suffix = uuid4().hex[:12]
        self.users: list[str] = []
        self.employees: list[str] = []
        frappe.set_user("Administrator")
        for role, label in zip(ROLES, ("Maker", "Reviewer", "Approver"), strict=True):
            email = f"_test_so_{label.lower()}_{suffix}@example.invalid"
            # Manager roles do not inherit native Item read. These functional
            # base roles supply Item read without granting Stock transactions
            # or the Sales Manager execution role to the financial approver.
            roles = [role]
            if label == "Reviewer":
                roles.append("Sales User")
            elif label == "Approver":
                roles.append("Accounts User")
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": f"_Test SO {label}",
                    "send_welcome_email": 0,
                    "roles": [{"role": assigned} for assigned in roles],
                }
            ).insert(ignore_permissions=True)
            self.users.append(user.name)
            employee = frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"_Test SO {label}",
                    "company": self.company,
                    "department": "_Test Department - _TC",
                    "employment_type": "Full-time",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active",
                    "user_id": user.name,
                    "approval_signature": f"test-signature-{suffix}-{label.lower()}",
                }
            ).insert(ignore_permissions=True)
            self.employees.append(employee.name)
        self.customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_code": f"_TEST-SO-{suffix}",
                "customer_name": f"_Test SO Customer {suffix}",
                "customer_type": "Company",
                "customer_group": "_Test Customer Group",
                "territory": "_Test Territory",
            }
        ).insert(ignore_permissions=True)

    def _order(self, *, rate: int = 50000, customer: str | None = None) -> SalesOrder:
        frappe.set_user(self.users[0])
        return cast(
            SalesOrder,
            frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "customer": customer or self.customer.name,
                    "company": self.company,
                    "currency": self.currency,
                    "selling_price_list": self.price_list,
                    "price_list_currency": self.currency,
                    "plc_conversion_rate": 1,
                    "transaction_date": today(),
                    "delivery_date": add_days(today(), 10),
                    "items": [
                        {
                            "item_code": self.item,
                            "warehouse": self.warehouse,
                            "qty": 1,
                            "rate": rate,
                            "income_account": self.income_account,
                            "cost_center": self.cost_center,
                        }
                    ],
                }
            ).insert(ignore_permissions=True),
        )

    def _send(self, order: SalesOrder) -> SalesOrder:
        frappe.set_user(self.users[0])
        return cast(SalesOrder, apply_workflow(order, "Send Sales Order for Review"))

    def _service_item(self) -> str:
        suffix = uuid4().hex[:12]
        frappe.set_user("Administrator")
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": f"_TEST-SO-SERVICE-{suffix}",
                "item_name": f"_Test SO Service {suffix}",
                "item_group": frappe.db.get_value("Item", self.item, "item_group"),
                "stock_uom": frappe.db.get_value("Item", self.item, "stock_uom"),
                "is_stock_item": 0,
                "is_sales_item": 1,
            }
        ).insert(ignore_permissions=True)
        return str(item.name)

    def _actual_tax_account(self) -> str:
        suffix = uuid4().hex[:12]
        parent = frappe.db.get_value(
            "Account", {"company": self.company, "root_type": "Liability", "is_group": 1}, "name"
        )
        self.assertTrue(parent)
        frappe.set_user("Administrator")
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"_Test SO Auto Tax {suffix}",
                "company": self.company,
                "parent_account": parent,
                "account_type": "Tax",
                "root_type": "Liability",
                "is_group": 0,
                "account_currency": self.currency,
            }
        ).insert(ignore_permissions=True)
        return str(account.name)

    def _review(self, order: SalesOrder) -> SalesOrder:
        frappe.set_user(self.users[1])
        return cast(SalesOrder, apply_workflow(order, "Review Sales Order"))

    def _approve(self, order: SalesOrder) -> SalesOrder:
        frappe.set_user(self.users[2])
        return cast(SalesOrder, apply_workflow(order, "Approve Sales Order"))

    def _post(self, order: SalesOrder) -> SalesOrder:
        order = self._approve(self._review(self._send(order)))
        frappe.set_user(self.users[1])
        return cast(SalesOrder, apply_workflow(order, "Submit Sales Order"))

    def test_direct_submit_and_state_spoof_are_denied(self) -> None:
        order = self._order()
        with self.assertRaises(frappe.ValidationError):
            order.submit()
        order.reload()
        order.set("workflow_state", "Sales Order Approved")
        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True)

    def test_wrong_role_is_denied(self) -> None:
        order = self._order()
        frappe.set_user(self.users[2])
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Send Sales Order for Review")
        order.reload()
        order = self._send(order)
        frappe.set_user(self.users[0])
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Sales Order")

    def test_maker_with_reviewer_role_cannot_self_review(self) -> None:
        order = self._send(self._order())
        frappe.set_user("Administrator")
        maker = frappe.get_doc("User", self.users[0])
        maker.append("roles", {"role": "Sales Manager"})
        maker.save(ignore_permissions=True)
        frappe.clear_cache(user=self.users[0])
        frappe.set_user(self.users[0])
        self.assertIn("Sales Manager", frappe.get_roles(self.users[0]))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Sales Order")
        self.assertEqual(
            frappe.db.get_value("Sales Order", order.name, "workflow_state"), "Sales Order Pending Review"
        )

    def test_spoofed_approval_evidence_cannot_enter_review(self) -> None:
        order = self._order()
        order.set("approval_maker_user", self.users[0])
        frappe.set_user(self.users[0])
        with self.assertRaises(frappe.ValidationError):
            order.save()
            apply_workflow(order, "Send Sales Order for Review")
        self.assertEqual(
            frappe.db.get_value("Sales Order", order.name, "workflow_state"), "Sales Order Draft"
        )

    def test_signed_review_approval_and_native_post(self) -> None:
        order = self._order()
        order = self._send(order)
        self.assertEqual(order.get("approval_maker_user"), self.users[0])
        order = self._review(order)
        self.assertEqual(order.get("approval_reviewer_user"), self.users[1])
        self.assertTrue(
            order.get("checked_by") and order.get("checked_at") and order.get("checked_signature")
        )
        order = self._approve(order)
        self.assertEqual(order.get("approval_approver_user"), self.users[2])
        self.assertEqual(
            order.get("billing_authority_revision"), sales_order_workflow.BILLING_AUTHORITY_REVISION
        )
        self.assertEqual(order.get("billing_authorized_by"), self.users[2])
        self.assertEqual(
            order.get("billing_authority_digest"), sales_order_workflow.billing_authority_digest(order)
        )
        self.assertTrue(
            order.get("authorized_by") and order.get("authorized_at") and order.get("authorized_signature")
        )
        frappe.set_user(self.users[1])
        order = cast(SalesOrder, apply_workflow(order, "Submit Sales Order"))
        self.assertEqual((order.docstatus, order.get("workflow_state")), (1, "Sales Order Submitted"))
        self.assertIsNone(getattr(frappe.flags, "sales_order_submission", None))

    def test_sealed_billing_authority_rejects_direct_field_tampering(self) -> None:
        order = self._approve(self._review(self._send(self._order())))
        original = order.get("billing_authority_digest")
        frappe.set_user(self.users[1])
        order.set("billing_authority_digest", "forged")
        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Sales Order", order.name, "billing_authority_digest"), original)

    def test_service_order_generates_and_submits_one_native_invoice(self) -> None:
        service = self._service_item()
        frappe.set_user(self.users[0])
        order = cast(
            SalesOrder,
            frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "customer": self.customer.name,
                    "company": self.company,
                    "currency": self.currency,
                    "selling_price_list": self.price_list,
                    "price_list_currency": self.currency,
                    "plc_conversion_rate": 1,
                    "transaction_date": today(),
                    "delivery_date": add_days(today(), 10),
                    "items": [
                        {
                            "item_code": service,
                            "qty": 1,
                            "rate": 50000,
                            "income_account": self.income_account,
                            "cost_center": self.cost_center,
                        }
                    ],
                }
            ).insert(ignore_permissions=True),
        )
        approved = self._approve(self._review(self._send(order)))
        self.assertFalse(
            frappe.db.exists(auto_invoice_generation.RUN_DOCTYPE, {"source_name": approved.name})
        )
        frappe.set_user(self.users[1])
        with patch.object(auto_invoice_generation, "_queue") as queue:
            posted = cast(SalesOrder, apply_workflow(approved, "Submit Sales Order"))
        run_name = frappe.db.get_value(
            auto_invoice_generation.RUN_DOCTYPE,
            {"source_doctype": "Sales Order", "source_name": posted.name, "group_kind": "SO Service"},
            "name",
        )
        self.assertTrue(run_name)
        queue.assert_called_once_with(run_name)
        run = auto_invoice_generation._lock_run(str(run_name))
        invoice_name = auto_invoice_generation._generate(run)
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(invoice.get("connect_invoice_generation_run"), run_name)
        self.assertEqual(len(invoice.items), 1)
        self.assertEqual(invoice.items[0].sales_order, posted.name)
        self.assertEqual(invoice.items[0].so_detail, posted.items[0].name)
        self.assertGreater(
            frappe.db.count("GL Entry", {"voucher_type": "Sales Invoice", "voucher_no": invoice_name}),
            0,
        )
        run.reload()
        run.set("last_error", "forged-client-progress")
        with self.assertRaises(frappe.PermissionError):
            run.save(ignore_permissions=True)

    def test_native_mapper_partial_actual_tax_is_denied_before_invoice_or_gl(self) -> None:
        service = self._service_item()
        tax_account = self._actual_tax_account()
        order = self._order()
        order.append(
            "items",
            {
                "item_code": service,
                "qty": 1,
                "rate": 50000,
                "income_account": self.income_account,
                "cost_center": self.cost_center,
            },
        )
        order.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": tax_account,
                "description": "_Test fixed charge",
                "tax_amount": 100,
            },
        )
        order.save(ignore_permissions=True)
        with patch.object(auto_invoice_generation, "_queue"):
            posted = self._post(order)
        service_row = next(row for row in posted.items if row.item_code == service)
        frappe.set_user("Administrator")
        native = make_sales_invoice(posted.name, args={"filtered_children": [service_row.name]})
        self.assertEqual(len(native.items), 1)
        self.assertEqual(float(native.taxes[0].tax_amount), 100.0)
        run_name = frappe.db.get_value(
            auto_invoice_generation.RUN_DOCTYPE,
            {"source_doctype": "Sales Order", "source_name": posted.name, "group_kind": "SO Service"},
            "name",
        )
        self.assertTrue(run_name)
        gl_before = frappe.db.count("GL Entry", {"voucher_type": "Sales Invoice", "company": self.company})
        frappe.set_user(self.users[1])
        with self.assertRaises(frappe.ValidationError):
            auto_invoice_generation._generate(auto_invoice_generation._lock_run(str(run_name)))
        self.assertFalse(frappe.db.exists("Sales Invoice", {"connect_invoice_generation_run": run_name}))
        self.assertEqual(
            frappe.db.count("GL Entry", {"voucher_type": "Sales Invoice", "company": self.company}),
            gl_before,
        )

    def test_whole_source_actual_tax_generates_submitted_invoice(self) -> None:
        service = self._service_item()
        tax_account = self._actual_tax_account()
        order = self._order()
        order.set(
            "items",
            [
                {
                    "item_code": service,
                    "qty": 1,
                    "rate": 50000,
                    "income_account": self.income_account,
                    "cost_center": self.cost_center,
                }
            ],
        )
        order.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": tax_account,
                "description": "_Test whole-source fixed charge",
                "tax_amount": 100,
            },
        )
        order.save(ignore_permissions=True)
        with patch.object(auto_invoice_generation, "_queue"):
            posted = self._post(order)
        run_name = frappe.db.get_value(
            auto_invoice_generation.RUN_DOCTYPE,
            {"source_doctype": "Sales Order", "source_name": posted.name, "group_kind": "SO Service"},
            "name",
        )
        self.assertTrue(run_name)
        frappe.set_user(self.users[1])
        invoice_name = auto_invoice_generation._generate(auto_invoice_generation._lock_run(str(run_name)))
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(len(invoice.items), 1)
        self.assertEqual(float(invoice.taxes[0].tax_amount), 100.0)
        self.assertGreater(
            frappe.db.count("GL Entry", {"voucher_type": "Sales Invoice", "voucher_no": invoice_name}),
            0,
        )

    def test_partial_percentage_discount_recalculates_on_generated_invoice(self) -> None:
        service = self._service_item()
        order = self._order()
        order.append(
            "items",
            {
                "item_code": service,
                "qty": 1,
                "rate": 50000,
                "income_account": self.income_account,
                "cost_center": self.cost_center,
            },
        )
        order.set("additional_discount_percentage", 10)
        order.save(ignore_permissions=True)
        self.assertEqual(float(order.discount_amount), 10000.0)
        with patch.object(auto_invoice_generation, "_queue"):
            posted = self._post(order)
        run_name = frappe.db.get_value(
            auto_invoice_generation.RUN_DOCTYPE,
            {"source_doctype": "Sales Order", "source_name": posted.name, "group_kind": "SO Service"},
            "name",
        )
        self.assertTrue(run_name)
        frappe.set_user(self.users[1])
        invoice_name = auto_invoice_generation._generate(auto_invoice_generation._lock_run(str(run_name)))
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(float(invoice.additional_discount_percentage), 10.0)
        self.assertEqual(float(invoice.discount_amount), 5000.0)

    def test_financial_approver_cannot_execute_submit_transition(self) -> None:
        order = self._approve(self._review(self._send(self._order())))
        frappe.set_user(self.users[2])
        self.assertNotIn("Sales Manager", frappe.get_roles(self.users[2]))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Submit Sales Order")
        self.assertEqual(frappe.db.get_value("Sales Order", order.name, "docstatus"), 0)

    def test_missing_reviewer_signature_denies_transition(self) -> None:
        order = self._send(self._order())
        frappe.set_user("Administrator")
        frappe.db.set_value("Employee", self.employees[1], "approval_signature", None)
        frappe.set_user(self.users[1])
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Sales Order")
        self.assertEqual(frappe.db.get_value("Sales Order", order.name, "docstatus"), 0)

    def test_missing_approver_signature_denies_transition(self) -> None:
        order = self._review(self._send(self._order()))
        frappe.set_user("Administrator")
        frappe.db.set_value("Employee", self.employees[2], "approval_signature", None)
        frappe.set_user(self.users[2])
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Approve Sales Order")
        self.assertEqual(frappe.db.get_value("Sales Order", order.name, "docstatus"), 0)

    def test_business_item_mutation_after_review_is_denied(self) -> None:
        order = self._review(self._send(self._order()))
        order.items[0].qty += 1
        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True)

    def test_return_resubmit_and_reject_never_post(self) -> None:
        order = self._send(self._order())
        reserved_before = frappe.db.get_value(
            "Bin", {"item_code": self.item, "warehouse": self.warehouse}, "reserved_qty"
        )
        frappe.set_user(self.users[1])
        order = cast(SalesOrder, apply_workflow(order, "Return Sales Order"))
        self.assertEqual((order.docstatus, order.get("workflow_state")), (0, "Sales Order Returned"))
        self.assertFalse(order.get("approval_digest"))
        self.assertEqual(
            frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.warehouse}, "reserved_qty"),
            reserved_before,
        )
        frappe.set_user(self.users[0])
        order = cast(SalesOrder, apply_workflow(order, "Resubmit Sales Order for Review"))
        order = self._review(order)
        frappe.set_user(self.users[2])
        order = cast(SalesOrder, apply_workflow(order, "Reject Sales Order"))
        self.assertEqual((order.docstatus, order.get("workflow_state")), (0, "Sales Order Rejected"))
        self.assertFalse(order.get("approval_digest"))
        self.assertEqual(
            frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.warehouse}, "reserved_qty"),
            reserved_before,
        )
        self.assertEqual(
            frappe.db.count(
                "Stock Reservation Entry", {"voucher_type": "Sales Order", "voucher_no": order.name}
            ),
            0,
        )

    def test_return_requires_full_reapproval(self) -> None:
        order = self._review(self._send(self._order()))
        frappe.set_user(self.users[2])
        order = cast(SalesOrder, apply_workflow(order, "Return Sales Order"))
        self.assertFalse(order.get("approval_digest"))
        order.items[0].qty = 2
        frappe.set_user(self.users[0])
        order.save(ignore_permissions=True)
        order = cast(SalesOrder, apply_workflow(order, "Resubmit Sales Order for Review"))
        order = self._review(order)
        order = self._approve(order)
        frappe.set_user(self.users[1])
        posted = cast(SalesOrder, apply_workflow(order, "Submit Sales Order"))
        self.assertEqual(posted.docstatus, 1)

    def test_direct_cancel_denied_native_cancel_succeeds(self) -> None:
        order = self._post(self._order())
        frappe.set_user(self.users[1])
        with self.assertRaises(frappe.ValidationError):
            order.cancel()
        order.reload()
        cancelled = cast(SalesOrder, apply_workflow(order, "Cancel Sales Order"))
        self.assertEqual((cancelled.docstatus, cancelled.get("workflow_state")), (2, "Sales Order Cancelled"))

    def test_post_execution_marker_is_one_use(self) -> None:
        posted = self._post(self._order())
        self.assertIsNone(getattr(frappe.flags, "sales_order_submission", None))
        approved = self._approve(self._review(self._send(self._order())))
        frappe.set_user(self.users[1])
        with self.assertRaises(frappe.ValidationError):
            approved.submit()
        self.assertEqual(frappe.db.get_value("Sales Order", approved.name, "docstatus"), 0)
        replay = self._order()
        for fieldname in APPROVAL_FIELDS:
            replay.set(fieldname, posted.get(fieldname))
        replay.set("workflow_state", "Sales Order Submitted")
        frappe.set_user(self.users[1])
        with self.assertRaises(frappe.ValidationError):
            sales_order_workflow.authorize_sales_order_submission(replay)

    def test_discount_uses_same_approval_route(self) -> None:
        order = self._order()
        order.items[0].discount_percentage = 15
        order.save(ignore_permissions=True)
        self.assertEqual(self._post(order).docstatus, 1)

    def test_native_customer_hold_denies_order(self) -> None:
        frappe.set_user("Administrator")
        self.customer.disabled = 1
        self.customer.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            self._order()

    def test_credit_limit_uses_native_inputs(self) -> None:
        frappe.set_user("Administrator")
        self.customer.append("credit_limits", {"company": self.company, "credit_limit": 100000})
        self.customer.save(ignore_permissions=True)
        old_controller = frappe.db.get_single_value("Accounts Settings", "credit_controller")
        from erpnext.selling.doctype.customer.customer import check_credit_limit

        try:
            frappe.db.set_single_value("Accounts Settings", "credit_controller", "Accounts Manager")
            frappe.set_user(self.users[0])
            with self.assertRaises(frappe.ValidationError):
                check_credit_limit(self.customer.name, self.company, extra_amount=120000)
            frappe.set_user(self.users[2])
            check_credit_limit(self.customer.name, self.company, extra_amount=120000)
        finally:
            frappe.db.set_single_value("Accounts Settings", "credit_controller", old_controller)
        order = self._order()
        self.assertEqual(sales_order_workflow._credit_inputs(order)["customer_credit_limit"], 100000)

    def test_native_quotation_mapping_enters_route(self) -> None:
        from erpnext.selling.doctype.quotation.quotation import make_sales_order

        frappe.set_user("Administrator")
        quotation = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": self.customer.name,
                "customer": self.customer.name,
                "company": self.company,
                "currency": self.currency,
                "selling_price_list": self.price_list,
                "transaction_date": today(),
                "valid_till": add_days(today(), 30),
                "quotation_signatory_type": quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
                "quotation_delivery_terms": "Test delivery terms",
                "items": [
                    {
                        "item_code": self.item,
                        "qty": 1,
                        "rate": 50000,
                        "income_account": self.income_account,
                        "cost_center": self.cost_center,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        quotation.submit()
        mapped = make_sales_order(quotation.name)
        mapped.set("delivery_date", add_days(today(), 10))
        mapped.items[0].warehouse = self.warehouse
        frappe.set_user(self.users[0])
        order = cast(SalesOrder, mapped.insert(ignore_permissions=True))
        self.assertEqual(order.items[0].prevdoc_docname, quotation.name)
        self.assertEqual(self._post(order).docstatus, 1)

    def test_amendment_requires_fresh_evidence(self) -> None:
        posted = self._post(self._order())
        frappe.set_user(self.users[1])
        cancelled = cast(SalesOrder, apply_workflow(posted, "Cancel Sales Order"))
        amended = cast(SalesOrder, frappe.copy_doc(cancelled, ignore_no_copy=False))
        amended.docstatus = 0
        amended.set("workflow_state", "Sales Order Draft")
        amended.set("amended_from", cancelled.name)
        amended.set("delivery_date", add_days(today(), 10))
        for item in amended.items:
            item.delivery_date = amended.delivery_date
        for fieldname in APPROVAL_FIELDS:
            amended.set(fieldname, None)
        frappe.set_user(self.users[0])
        amended.insert(ignore_permissions=True)
        self.assertFalse(amended.get("approval_digest"))
        amended = self._send(amended)
        self.assertEqual(amended.get("workflow_state"), "Sales Order Pending Review")

    def test_downstream_mappers_require_submitted_order(self) -> None:
        order = self._order()
        # Use an actor with target-document create permission so a rejection
        # proves the source docstatus gate rather than a mapper permission gap.
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.ValidationError):
            make_delivery_note(order.name)
        with self.assertRaises(frappe.ValidationError):
            make_sales_invoice(order.name)
        posted = self._post(order)
        frappe.set_user("Administrator")
        delivery = make_delivery_note(posted.name)
        invoice = make_sales_invoice(posted.name)
        self.assertEqual(delivery.items[0].against_sales_order, posted.name)
        self.assertEqual(invoice.items[0].sales_order, posted.name)
