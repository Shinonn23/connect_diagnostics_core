# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import (
    PurchaseOrder,
    make_purchase_invoice,
    make_purchase_receipt,
)
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from connect_diagnostics_core.api.erpnext.purchase_order_workflow import get_commitment_digest

COMPANY = "_Test Company"
ITEM = "_Test Item"
WAREHOUSE = "_Test Warehouse - _TC"
MAKER = "_test.po.maker@example.com"
REVIEWER = "_test.po.reviewer@example.com"
APPROVER = "_test.po.approver@example.com"
UNAUTHORIZED = "_test.po.unauthorized@example.com"
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"


def _ordered_qty() -> float:
    return float(
        frappe.db.get_value(
            "Bin",
            {"item_code": ITEM, "warehouse": WAREHOUSE},
            "ordered_qty",
        )
        or 0
    )


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


def _draft_order() -> PurchaseOrder:
    order = cast(PurchaseOrder, frappe.new_doc("Purchase Order"))
    order.company = COMPANY
    order.supplier = "_Test Supplier"
    order.schedule_date = add_days(nowdate(), 1)
    order.currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
    order.append(
        "items",
        {
            "item_code": ITEM,
            "warehouse": WAREHOUSE,
            "qty": 2,
            "rate": 100,
            "schedule_date": add_days(nowdate(), 1),
        },
    )
    order.set_missing_values()
    return order.insert()


def _prepare_users() -> None:
    frappe.set_user("Administrator")
    _ensure_user(MAKER, ("Purchase User",))
    _ensure_user(REVIEWER, ("Purchase User", "Purchase Manager"))
    _ensure_user(APPROVER, ("Purchase User", "C-Level Approver"))
    _ensure_user(UNAUTHORIZED, ("Purchase User",))


class TestPurchaseOrderWorkflowIntegration(IntegrationTestCase):
    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_distinct_actor_workflow_submits_once_maps_downstream_and_cancels(
        self, _send_workflow_action_email: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        ordered_before = _ordered_qty()

        frappe.set_user(MAKER)
        order = _draft_order()
        with self.assertRaises(frappe.ValidationError):
            order.submit()
        order.reload()
        apply_workflow(order, "Submit Purchase Order for Review")

        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        order.reload()
        self.assertEqual(order.get("approval_reviewer_user"), REVIEWER)
        self.assertEqual(order.get("checked_signature"), SIGNATURE)
        self.assertEqual(order.get("approval_critical_digest"), get_commitment_digest(order))
        order.items[0].rate = 125
        with self.assertRaises(frappe.ValidationError):
            order.save()

        frappe.set_user(APPROVER)
        order.reload()
        apply_workflow(order, "Approve Purchase Order")
        order.reload()
        self.assertEqual(order.get("approval_authorized_user"), APPROVER)
        self.assertEqual(order.get("authorized_signature"), SIGNATURE)
        self.assertEqual(order.get("approval_critical_digest"), get_commitment_digest(order))

        frappe.set_user(REVIEWER)
        frappe.db.set_value("Purchase Order", order.name, "owner", APPROVER, update_modified=False)
        order.reload()
        frappe.db.savepoint("po_invalid_owner_post")
        try:
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(order, "Post Purchase Order")
        finally:
            frappe.db.rollback(save_point="po_invalid_owner_post")
        frappe.db.set_value("Purchase Order", order.name, "owner", MAKER, update_modified=False)
        order.reload()
        self.assertEqual(order.get("approval_critical_digest"), get_commitment_digest(order))
        apply_workflow(order, "Post Purchase Order")
        order.reload()
        self.assertEqual(order.docstatus, 1)
        self.assertEqual(order.get("workflow_state"), "Purchase Order Submitted")
        self.assertEqual(_ordered_qty(), ordered_before + 2)

        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Post Purchase Order")
        self.assertEqual(_ordered_qty(), ordered_before + 2)

        frappe.set_user("Administrator")
        receipt = make_purchase_receipt(order.name)
        invoice = make_purchase_invoice(order.name)
        self.assertEqual(receipt.items[0].purchase_order, order.name)
        self.assertEqual(invoice.items[0].purchase_order, order.name)
        self.assertEqual(receipt.items[0].qty, 2)
        self.assertEqual(invoice.items[0].qty, 2)

        frappe.set_user(REVIEWER)
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            order.cancel()
        order.reload()
        apply_workflow(order, "Cancel Purchase Order")
        order.reload()
        self.assertEqual(order.docstatus, 2)
        self.assertEqual(order.get("workflow_state"), "Purchase Order Cancelled")
        self.assertEqual(_ordered_qty(), ordered_before)

        frappe.set_user(MAKER)
        amended = cast(PurchaseOrder, frappe.copy_doc(order, ignore_no_copy=False))
        amended.docstatus = 0
        for child in amended.get_all_children():
            child.docstatus = 0
        amended.amended_from = order.name
        amended.insert()
        self.assertEqual(amended.docstatus, 0)
        self.assertEqual(amended.get("workflow_state"), "Purchase Order Draft")
        self.assertFalse(amended.get("approval_critical_digest"))
        self.assertFalse(amended.get("approval_authorized_user"))

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_return_and_reject_never_submit(self, _send_workflow_action_email: object) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()

        frappe.set_user(MAKER)
        order = _draft_order()
        apply_workflow(order, "Submit Purchase Order for Review")

        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        frappe.set_user(APPROVER)
        order.reload()
        apply_workflow(order, "Return Purchase Order")
        order.reload()
        self.assertEqual(order.get("workflow_state"), "Purchase Order Draft")
        self.assertFalse(order.get("approval_critical_digest"))
        self.assertFalse(order.get("checked_signature"))

        frappe.set_user(MAKER)
        apply_workflow(order, "Submit Purchase Order for Review")
        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        frappe.set_user(APPROVER)
        order.reload()
        apply_workflow(order, "Reject Purchase Order")
        order.reload()
        self.assertEqual(order.get("workflow_state"), "Purchase Order Rejected")
        self.assertEqual(order.docstatus, 0)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_maker_and_unauthorized_actor_cannot_collapse_stages(
        self, _send_workflow_action_email: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()

        frappe.set_user(MAKER)
        order = _draft_order()
        apply_workflow(order, "Submit Purchase Order for Review")
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Purchase Order")

        frappe.set_user(UNAUTHORIZED)
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Purchase Order")
