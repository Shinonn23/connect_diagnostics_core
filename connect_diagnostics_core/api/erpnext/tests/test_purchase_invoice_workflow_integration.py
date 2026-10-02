# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""End-to-end proof for the temporary native Purchase Invoice workflow."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import purchase_invoice_workflow


class TestPurchaseInvoiceWorkflowIntegration(IntegrationTestCase):
    """Exercise the configured route against real ERPNext documents."""

    workflow_name = "Connect Purchase Invoice Blueprint"

    def _cleanup_committed_item(self, name: str) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        frappe.set_user("Administrator")
        if frappe.db.exists("Item", name):
            frappe.delete_doc("Item", name, ignore_permissions=True)
            # The isolated Item fixture was committed to prove cross-session current reads.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self.assertFalse(frappe.db.exists("Item", name))

    def _finalize_committed_source_race(
        self,
        po: str,
        pr: str,
        pi: str,
        item: str,
        actors: tuple[str, str, str],
        stock_bin: dict[str, str],
        stock_baseline: float,
        submitted_sle: set[str],
        submitted_gl: set[str],
        evidence_file: str,
        evidence_url: str,
    ) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        frappe.set_user("Administrator")
        if frappe.db.exists("Purchase Invoice", pi):
            frappe.delete_doc("Purchase Invoice", pi, ignore_permissions=True)
        if frappe.db.get_value("Purchase Receipt", pr, "docstatus") == 1:
            frappe.get_doc("Purchase Receipt", pr).cancel()
        if frappe.db.get_value("Purchase Order", po, "docstatus") == 1:
            with self._as_user(actors[1]):
                apply_workflow(frappe.get_doc("Purchase Order", po), "Cancel Purchase Order")
        # Retain native canceled documents, stock and accounting history, actors,
        # and evidence as one uniquely named forensic fixture.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self.assertFalse(frappe.db.exists("Purchase Invoice", pi))
        self.assertEqual(frappe.db.get_value("Purchase Receipt", pr, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Purchase Order", po, "docstatus"), 2)
        self.assertTrue(frappe.db.exists("Item", item))
        self.assertTrue(all(frappe.db.exists("User", actor) for actor in actors))
        self.assertTrue(all(frappe.db.exists("Employee", {"user_id": actor}) for actor in actors[1:]))
        self.assertEqual(
            frappe.db.get_value(
                "File",
                evidence_file,
                ["file_url", "attached_to_doctype", "attached_to_name", "attached_to_field"],
            ),
            (
                evidence_url,
                "Purchase Order",
                po,
                "supplier_selection_evidence",
            ),
        )
        self.assertAlmostEqual(
            float(frappe.db.get_value("Bin", stock_bin, "actual_qty") or 0), stock_baseline
        )
        sle = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_type": "Purchase Receipt", "voucher_no": pr},
            fields=["name", "actual_qty"],
        )
        self.assertTrue(submitted_sle)
        self.assertTrue(submitted_sle.issubset({row.name for row in sle}))
        self.assertAlmostEqual(sum(float(row.actual_qty) for row in sle), 0)
        gl = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Purchase Receipt", "voucher_no": pr},
            fields=["name", "account", "debit", "credit"],
        )
        self.assertTrue(submitted_gl.issubset({row.name for row in gl}))
        for account in {row.account for row in gl}:
            self.assertAlmostEqual(
                sum(float(row.debit) - float(row.credit) for row in gl if row.account == account),
                0,
            )
        for doctype, name in (("Purchase Order", po), ("Purchase Receipt", pr), ("Purchase Invoice", pi)):
            self.assertFalse(
                frappe.db.exists(
                    "Workflow Action",
                    {"reference_doctype": doctype, "reference_name": name, "status": "Open"},
                )
            )

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
        settings.append("company_accounts", {"company": company})
        settings.save(ignore_permissions=True)

    def _source_documents(self, maker: str, reviewer: str, approver: str) -> tuple[str, str, str]:
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
        goods = frappe.get_doc("Item", item)
        expense_account = frappe.db.get_value(
            "Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name"
        )
        if not expense_account:
            self.skipTest("A leaf Expense account is required for the service Purchase Invoice row")
        self.service_item = (
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": f"_Test PI Service {frappe.generate_hash(length=12)}",
                    "item_group": goods.item_group,
                    "stock_uom": goods.stock_uom,
                    "is_stock_item": 0,
                    "is_fixed_asset": 0,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        with self._as_user(maker):
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
                        },
                        {
                            "item_code": self.service_item,
                            "qty": 1,
                            "rate": 50,
                            "schedule_date": frappe.utils.today(),
                        },
                    ],
                }
            ).insert()
            evidence = frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": f"_test_pi_po_selection_{frappe.generate_hash(length=12)}.txt",
                    "content": b"Direct supplier selection for native invoice source",
                    "is_private": 1,
                    "attached_to_doctype": "Purchase Order",
                    "attached_to_name": po.name,
                    "attached_to_field": "supplier_selection_evidence",
                }
            ).insert(ignore_permissions=True)
            po.supplier_selection_reason = "Direct supplier selection for invoice source"
            po.supplier_selection_evidence = evidence.file_url
            po.save()
            po = apply_workflow(po, "Submit Purchase Order for Review")
        with self._as_user(reviewer):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Review Purchase Order")
        with self._as_user(approver):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Approve Purchase Order")
        with self._as_user(reviewer):
            po = apply_workflow(frappe.get_doc("Purchase Order", po.name), "Post Purchase Order")
        self.assertEqual(po.docstatus, 1)
        self.source_stock_bin = {"item_code": item, "warehouse": warehouse}
        self.source_stock_before_receipt = float(
            frappe.db.get_value("Bin", self.source_stock_bin, "actual_qty") or 0
        )
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
                        },
                        {
                            "item_code": self.service_item,
                            "qty": 1,
                            "rate": 50,
                            "expense_account": expense_account,
                            "purchase_order": po.name,
                            "po_detail": po.items[1].name,
                        },
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
        maker = self._user("maker", ["Accounts User", "Purchase User"])
        reviewer = self._user("reviewer", ["Accounts User", "Purchase Manager", "Purchase User"])
        approver = self._user(
            "approver", ["Accounts User", "Accounts Manager", "C-Level Approver", "Purchase User"]
        )
        self._employee(reviewer)
        self._employee(approver)
        _po, _pr, name = self._source_documents(maker, reviewer, approver)
        service_row = next(
            row
            for row in frappe.get_doc("Purchase Invoice", name).items
            if row.item_code == self.service_item
        )
        self.assertFalse(service_row.purchase_receipt)
        self.assertFalse(service_row.pr_detail)
        for field, value, expected in (
            ("purchase_receipt", None, "require a Purchase Receipt"),
            ("po_detail", "OTHER-PO-ITEM", "selected order"),
            ("pr_detail", "OTHER-PR-ITEM", "must match"),
        ):
            altered = frappe.get_doc("Purchase Invoice", name)
            altered.items[0].set(field, value)
            with self.assertRaisesRegex(frappe.ValidationError, expected):
                purchase_invoice_workflow._require_sources(altered)
            self.assertEqual(frappe.db.get_value("Purchase Invoice", name, "docstatus"), 0)
            self.assertFalse(
                frappe.db.exists("GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": name})
            )
        altered = frappe.get_doc("Purchase Invoice", name)
        next(row for row in altered.items if row.item_code == self.service_item).set("pr_detail", "PRI-OTHER")
        with self.assertRaisesRegex(frappe.ValidationError, "both header and item"):
            purchase_invoice_workflow._require_sources(altered)

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

    def test_stale_service_snapshot_cannot_waive_new_stock_receipt_requirement(self) -> None:
        previous_user = frappe.session.user
        self.addCleanup(frappe.set_user, previous_user)
        frappe.set_user("Administrator")
        template = frappe.get_doc("Item", "_Test Item")
        name = f"_Test PI Classification {frappe.generate_hash(length=12)}"
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": name,
                "item_group": template.item_group,
                "stock_uom": template.stock_uom,
                "is_stock_item": 0,
                "is_fixed_asset": 0,
            }
        ).insert()
        self.addCleanup(self._cleanup_committed_item, str(item.name))
        # Make the service Item visible in a second MariaDB session.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Item", name, "is_stock_item"), 0)
        with self.primary_connection():
            current = frappe.get_doc("Item", name)
            current.is_stock_item = 1
            current.save()
            # Preserve the old repeatable-read snapshot in the second session.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        candidate = Document(
            {
                "doctype": "Purchase Invoice",
                "items": [{"item_code": name, "purchase_order": "PO-ANY", "po_detail": "POI-ANY"}],
            }
        )
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Item", name, "is_stock_item"), 0)
            with self.assertRaisesRegex(frappe.ValidationError, "require a Purchase Receipt"):
                purchase_invoice_workflow._require_sources(candidate)
            frappe.db.rollback()

    def test_cancelled_po_and_pr_cannot_pass_stale_submitted_snapshots(self) -> None:
        self._company()
        maker = self._user(f"maker_{frappe.generate_hash(length=12)}", ["Accounts User", "Purchase User"])
        reviewer = self._user(
            f"reviewer_{frappe.generate_hash(length=12)}",
            ["Accounts User", "Purchase Manager", "Purchase User"],
        )
        approver = self._user(
            f"approver_{frappe.generate_hash(length=12)}",
            ["Accounts User", "Accounts Manager", "C-Level Approver", "Purchase User"],
        )
        self._employee(reviewer)
        self._employee(approver)
        po, pr, pi = self._source_documents(maker, reviewer, approver)
        source = frappe.get_doc("Purchase Invoice", pi)
        stock_row = next(row.as_dict() for row in source.items if row.item_code != self.service_item)
        service_row = next(row.as_dict() for row in source.items if row.item_code == self.service_item)
        stock_bin = self.source_stock_bin
        stock_baseline = self.source_stock_before_receipt
        submitted_sle = set(
            frappe.get_all(
                "Stock Ledger Entry",
                filters={"voucher_type": "Purchase Receipt", "voucher_no": pr},
                pluck="name",
            )
        )
        submitted_gl = set(
            frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Purchase Receipt", "voucher_no": pr},
                pluck="name",
            )
        )
        self.assertTrue(submitted_sle)
        evidence_url = str(frappe.db.get_value("Purchase Order", po, "supplier_selection_evidence"))
        evidence_file = frappe.db.get_value(
            "File",
            {
                "file_url": evidence_url,
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": po,
                "attached_to_field": "supplier_selection_evidence",
            },
            "name",
        )
        self.assertTrue(evidence_file)
        frappe.set_user("Administrator")
        frappe.delete_doc("Purchase Invoice", pi, ignore_permissions=True)
        self.addCleanup(
            self._finalize_committed_source_race,
            po,
            pr,
            pi,
            self.service_item,
            (maker, reviewer, approver),
            stock_bin,
            stock_baseline,
            submitted_sle,
            submitted_gl,
            str(evidence_file),
            evidence_url,
        )
        # Publish only the UUID-owned native fixture, then preserve an earlier
        # repeatable-read snapshot in the second connection.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Purchase Order", po, "docstatus"), 1)
            self.assertEqual(frappe.db.get_value("Purchase Receipt", pr, "docstatus"), 1)
        stock_row_source = frappe.get_doc("Purchase Receipt", pr).items[0]
        stock_bin = {"item_code": stock_row_source.item_code, "warehouse": stock_row_source.warehouse}
        stock_before_cancel = float(frappe.db.get_value("Bin", stock_bin, "actual_qty") or 0)
        self.assertAlmostEqual(stock_before_cancel, stock_baseline + 1)
        with self.primary_connection():
            frappe.get_doc("Purchase Receipt", pr).cancel()
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self.assertAlmostEqual(
            float(frappe.db.get_value("Bin", stock_bin, "actual_qty") or 0), stock_before_cancel - 1
        )
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Purchase Receipt", pr, "docstatus"), 1)
            candidate = Document({"doctype": "Purchase Invoice", "items": [stock_row]})
            with self.assertRaisesRegex(frappe.ValidationError, "remain submitted"):
                purchase_invoice_workflow._require_sources(candidate)
        with self.primary_connection():
            with self._as_user(reviewer):
                apply_workflow(frappe.get_doc("Purchase Order", po), "Cancel Purchase Order")
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Purchase Order", po, "docstatus"), 1)
            candidate = Document({"doctype": "Purchase Invoice", "items": [service_row]})
            with self.assertRaisesRegex(frappe.ValidationError, "remain submitted"):
                purchase_invoice_workflow._require_sources(candidate)
            frappe.db.rollback()
