# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.serial_batch_bundle import get_batch_nos
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

COMPANY = "_Test Company"
ITEM = "_Test Stock Transfer Approval Item"
BATCH_ITEM = "_Test Stock Transfer Approval Batch Item"
SOURCE = "Stores - _TC"
TARGET = "Finished Goods - _TC"
MAKER = "_test.stock.maker@example.com"
REVIEWER = "_test.stock.reviewer@example.com"
APPROVER = "_test.stock.approver@example.com"
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"


def _bin_qty(item_code: str, warehouse: str) -> float:
    return float(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0)


def _ensure_user(user: str, roles: tuple[str, ...]) -> None:
    if not frappe.db.exists("User", user):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": user,
                "send_welcome_email": 0,
                "user_type": "System User",
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)
    else:
        user_doc = frappe.get_doc("User", user)
        current_roles = {row.role for row in user_doc.roles}
        for role in roles:
            if role not in current_roles:
                user_doc.append("roles", {"role": role})
        user_doc.user_type = "System User"
        user_doc.save(ignore_permissions=True)
    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if employee_name:
        employee = frappe.get_doc("Employee", employee_name)
        employee.status = "Active"
        employee.approval_signature = SIGNATURE
        employee.save(ignore_permissions=True)
        frappe.clear_cache(user=user)
        return
    department = frappe.db.get_value("Department", {"company": COMPANY}, "name")
    employment_type = frappe.db.get_value("Employment Type", {}, "name")
    if not (department and employment_type):
        raise AssertionError("Employee test prerequisites are unavailable")
    frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": user,
            "company": COMPANY,
            "department": department,
            "gender": "Female",
            "date_of_birth": "1990-05-08",
            "date_of_joining": "2020-01-01",
            "status": "Active",
            "employment_type": employment_type,
            "user_id": user,
            "company_email": user,
            "approval_signature": SIGNATURE,
        }
    ).insert(ignore_permissions=True)
    frappe.clear_cache(user=user)


def _ensure_item() -> None:
    if not frappe.db.exists("Item", ITEM):
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        if not item_group:
            raise AssertionError("Item Group test prerequisite is unavailable")
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": ITEM,
                "item_name": ITEM,
                "item_group": item_group,
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)


def _ensure_batch_item() -> None:
    if frappe.db.exists("Item", BATCH_ITEM):
        return
    item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
    if not item_group:
        raise AssertionError("Item Group test prerequisite is unavailable")
    frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": BATCH_ITEM,
            "item_name": BATCH_ITEM,
            "item_group": item_group,
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "batch_number_series": "_TEST-WF-BATCH-.#####",
        }
    ).insert(ignore_permissions=True)


def _draft_transfer(qty: float = 1, item_code: str = ITEM, batch_no: str | None = None) -> StockEntry:
    doc = cast(
        StockEntry,
        make_stock_entry(
            item_code=item_code,
            source=SOURCE,
            target=TARGET,
            qty=qty,
            batch_no=batch_no,
            do_not_save=True,
        ),
    )
    return doc.insert()


class TestStockEntryWorkflowIntegration(IntegrationTestCase):
    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_distinct_actor_workflow_posts_once_and_native_cancel_reverses(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))
        make_stock_entry(item_code=ITEM, target=SOURCE, qty=5, basic_rate=100)
        source_before = _bin_qty(ITEM, SOURCE)
        target_before = _bin_qty(ITEM, TARGET)

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        with self.assertRaises(frappe.ValidationError):
            transfer.submit()
        transfer.reload()
        apply_workflow(transfer, "Send Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("approval_reviewer_user"), REVIEWER)
        self.assertEqual(transfer.get("checked_signature"), SIGNATURE)
        transfer.items[0].qty = 2
        with self.assertRaises(frappe.ValidationError):
            transfer.save()

        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("approval_authorized_user"), APPROVER)
        self.assertEqual(transfer.get("authorized_signature"), SIGNATURE)

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 1)
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Submitted")
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before - 1)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before + 1)
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name, "is_cancelled": 0}),
            2,
        )

        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Submit Stock Transfer")
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name, "is_cancelled": 0}),
            2,
        )

        apply_workflow(transfer, "Cancel Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 2)
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Cancelled")
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_return_resubmit_and_reject_never_post_stock(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        apply_workflow(transfer, "Send Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Return Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Returned")
        self.assertFalse(transfer.get("approval_critical_digest"))
        self.assertFalse(transfer.get("checked_signature"))

        frappe.set_user(MAKER)
        transfer.reload()
        apply_workflow(transfer, "Resubmit Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")

        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Reject Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Rejected")
        self.assertEqual(transfer.docstatus, 0)
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), 0)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_maker_and_unauthorized_user_cannot_review(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        apply_workflow(transfer, "Send Stock Transfer for Review")
        transfer.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Review Stock Transfer")

        frappe.set_user(APPROVER)
        transfer.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Review Stock Transfer")
        self.assertFalse(transfer.get("approval_reviewer_user"))
        self.assertFalse(transfer.get("checked_signature"))

    def test_non_material_transfer_keeps_native_submit_path(self) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()

        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=ITEM, target=SOURCE, qty=1, basic_rate=100),
        )
        receipt.reload()
        self.assertEqual(receipt.purpose, "Material Receipt")
        self.assertEqual(receipt.get("workflow_state"), "Stock Entry Submitted")
        self.assertEqual(receipt.docstatus, 1)
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": receipt.name, "is_cancelled": 0}),
            1,
        )

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_batch_bundle_moves_and_reverses_through_native_posting(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_batch_item()
        serial_batch_enabled = frappe.db.get_single_value(
            "Stock Settings", "enable_serial_and_batch_no_for_item"
        )
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            serial_batch_enabled,
        )
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))
        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=BATCH_ITEM, target=SOURCE, qty=1, basic_rate=100),
        )
        batch_no = next(iter(get_batch_nos(receipt.items[0].serial_and_batch_bundle)))

        frappe.set_user(MAKER)
        transfer = _draft_transfer(item_code=BATCH_ITEM, batch_no=batch_no)
        apply_workflow(transfer, "Send Stock Transfer for Review")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()

        self.assertTrue(transfer.items[0].serial_and_batch_bundle)
        self.assertEqual(set(get_batch_nos(transfer.items[0].serial_and_batch_bundle)), {batch_no})
        self.assertEqual(get_batch_qty(batch_no, SOURCE, BATCH_ITEM), 0)
        self.assertEqual(get_batch_qty(batch_no, TARGET, BATCH_ITEM), 1)

        apply_workflow(transfer, "Cancel Stock Transfer")
        self.assertEqual(get_batch_qty(batch_no, SOURCE, BATCH_ITEM), 1)
        self.assertEqual(get_batch_qty(batch_no, TARGET, BATCH_ITEM), 0)
