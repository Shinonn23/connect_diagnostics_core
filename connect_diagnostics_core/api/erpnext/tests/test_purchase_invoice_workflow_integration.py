# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""End-to-end proof for the temporary native Purchase Invoice workflow."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import purchase_invoice_workflow
from connect_diagnostics_core.api.erpnext.tests.test_purchase_order_workflow_integration import (
    APPROVER as PO_APPROVER,
)
from connect_diagnostics_core.api.erpnext.tests.test_purchase_order_workflow_integration import (
    MAKER as PO_MAKER,
)
from connect_diagnostics_core.api.erpnext.tests.test_purchase_order_workflow_integration import (
    REVIEWER as PO_REVIEWER,
)
from connect_diagnostics_core.api.erpnext.tests.test_purchase_order_workflow_integration import (
    _prepare_users as prepare_po_users,
)


class TestPurchaseInvoiceWorkflowIntegration(IntegrationTestCase):
    """Exercise the configured route against real ERPNext documents."""

    workflow_name = "Connect Purchase Invoice Blueprint"

    def setUp(self) -> None:
        super().setUp()
        missing = [
            role
            for role in ("Accounts User", "Purchase Manager", "Accounts Manager")
            if not frappe.db.exists("Role", role)
        ]
        if missing or not frappe.db.exists("Workflow", self.workflow_name):
            self.skipTest(
                "Purchase Invoice workflow precondition is not migrated: "
                + ", ".join(missing or [self.workflow_name])
            )

    def _user(self, suffix: str, roles: list[str]) -> str:
        email = f"_test_pi_{suffix}@example.com"
        if not frappe.db.exists("User", email):
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": f"PI {suffix}",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "roles": [{"doctype": "Has Role", "role": role} for role in roles],
                }
            )
            user.insert(ignore_permissions=True)
        frappe.get_doc("User", email).add_roles(*roles)
        return email

    def _employee(self, user: str) -> str:
        name = f"_Test PI Employee {user.split('@', 1)[0][-8:]}"
        if not frappe.db.exists("Employee", {"user_id": user}):
            employee = frappe.get_doc(
                {
                    "doctype": "Employee",
                    "employee_name": name,
                    "first_name": name,
                    "company": self.company,
                    "user_id": user,
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2026-01-01",
                    "employment_type": "Full-time",
                    "status": "Active",
                    "gender": "Other",
                    "approval_signature": "data:image/png;base64,dGVzdA==",
                }
            )
            employee.insert(ignore_permissions=True)
        return str(frappe.db.get_value("Employee", {"user_id": user}, "name"))

    def _company(self) -> str:
        company = (
            "_Test Company"
            if frappe.db.exists("Company", "_Test Company")
            else frappe.db.get_value("Company", {}, "name")
        )
        if not company:
            self.skipTest("No Company exists on local.test for ERPNext transaction tests")
        self.company = str(company)
        return self.company

    def _ensure_transactional_thai_tax_settings(self, company: str) -> None:
        settings = frappe.get_single("Thai Tax Settings")
        if any(row.company == company for row in settings.company_accounts):
            return
        tax_account = frappe.db.get_value(
            "Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name"
        )
        if not tax_account:
            self.skipTest(f"A leaf Tax account is required for {company}")
        settings.append(
            "company_accounts",
            {
                "company": company,
                "sales_tax_account": tax_account,
                "purchase_tax_account": tax_account,
            },
        )
        settings.save(ignore_permissions=True)

    def _source_documents(self, maker: str) -> tuple[str, str, str]:
        company = self._company()
        self._ensure_transactional_thai_tax_settings(company)
        supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 0}, "name")
        item = (
            "_Test Item"
            if frappe.db.exists("Item", "_Test Item")
            else frappe.db.get_value("Item", {}, "name")
        )
        warehouse = (
            "_Test Warehouse - _TC"
            if company == "_Test Company" and frappe.db.exists("Warehouse", "_Test Warehouse - _TC")
            else frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name")
        )
        if not supplier or not item or not warehouse:
            self.skipTest("Supplier, Item, and company Warehouse are required ERPNext test fixtures")
        prepare_po_users()
        with self._as_user(PO_MAKER):
            po = frappe.get_doc(
                {
                    "doctype": "Purchase Order",
                    "company": company,
                    "supplier": supplier,
                    "schedule_date": frappe.utils.today(),
                    "items": [
                        {
                            "item_code": item,
                            "qty": 1,
                            "rate": 100,
                            "warehouse": warehouse,
                            "schedule_date": frappe.utils.today(),
                        }
                    ],
                }
            ).insert(ignore_permissions=True)
            po = apply_workflow(po, "Submit Purchase Order for Review")
        with self._as_user(PO_REVIEWER):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Review Purchase Order")
        with self._as_user(PO_APPROVER):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Approve Purchase Order")
        with self._as_user(PO_REVIEWER):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Post Purchase Order")
        pr = frappe.get_doc(
            {
                "doctype": "Purchase Receipt",
                "company": company,
                "supplier": supplier,
                "items": [
                    {
                        "item_code": item,
                        "qty": 1,
                        "rate": 100,
                        "warehouse": warehouse,
                        "purchase_order": po.name,
                        "purchase_order_item": po.items[0].name,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        pr.submit()
        with self._as_user(maker):
            pi = frappe.get_doc(
                {
                    "doctype": "Purchase Invoice",
                    "company": company,
                    "supplier": supplier,
                    "bill_no": f"_TEST_PI_{frappe.generate_hash(length=8)}",
                    "items": [
                        {
                            "item_code": item,
                            "qty": 1,
                            "rate": 100,
                            "purchase_order": po.name,
                            "po_detail": po.items[0].name,
                            "purchase_receipt": pr.name,
                            "pr_detail": pr.items[0].name,
                        }
                    ],
                }
            ).insert(ignore_permissions=True)
        return po.name, pr.name, pi.name

    @contextmanager
    def _as_user(self, user: str) -> Iterator[None]:
        previous = frappe.session.user
        frappe.set_user(user)
        try:
            yield
        finally:
            frappe.set_user(previous)

    def test_native_purchase_invoice_route_posts_and_cancels(self) -> None:
        self._company()
        maker = self._user("maker", ["Accounts User"])
        reviewer = self._user("reviewer", ["Accounts User", "Purchase Manager"])
        approver = self._user("approver", ["Accounts User", "Accounts Manager"])
        self._employee(reviewer)
        self._employee(approver)
        _po, _pr, name = self._source_documents(maker)

        with self._as_user(approver):
            with self.assertRaises(frappe.ValidationError):
                frappe.get_doc("Purchase Invoice", name).submit()

        with self._as_user(maker):
            pi = apply_workflow(
                frappe.get_doc("Purchase Invoice", name), "Submit Purchase Invoice for Review"
            )
        self.assertEqual(pi.workflow_state, "Purchase Invoice Pending Source Verification")
        with self._as_user(reviewer):
            pi = apply_workflow(frappe.get_doc("Purchase Invoice", name), "Verify Purchase Invoice Source")
        reviewed = frappe.get_doc("Purchase Invoice", name)
        self.assertEqual(
            reviewed.approval_critical_digest,
            purchase_invoice_workflow.get_approval_digest(reviewed),
        )
        with self._as_user(approver):
            self.assertIn("Accounts User", frappe.get_roles())
            self.assertIn("Accounts Manager", frappe.get_roles())
            self.assertTrue(frappe.has_permission("Purchase Invoice", "read"))
            approver_doc = frappe.get_doc("Purchase Invoice", name)
            self.assertTrue(approver_doc.has_permission("read"))
            pi = apply_workflow(approver_doc, "Approve Purchase Invoice")
            pi = apply_workflow(frappe.get_doc("Purchase Invoice", name), "Post Purchase Invoice")
        self.assertEqual(pi.docstatus, 1)
        self.assertEqual(pi.workflow_state, "Purchase Invoice Submitted")
        self.assertTrue(
            frappe.db.exists("GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": name})
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Entry Reference",
                {"reference_doctype": "Purchase Invoice", "reference_name": name},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "Workflow Action",
                {"reference_name": name, "status": "Open", "workflow_name": ["like", "%Payment%"]},
            )
        )

        with self._as_user(approver):
            cancelled = apply_workflow(frappe.get_doc("Purchase Invoice", name), "Cancel Purchase Invoice")
        self.assertEqual(cancelled.docstatus, 2)
        self.assertEqual(cancelled.workflow_state, "Purchase Invoice Cancelled")
        self.assertTrue(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": name, "is_cancelled": 1}
            )
        )
