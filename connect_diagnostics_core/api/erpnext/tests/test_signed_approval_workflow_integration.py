# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext.print_actions import capture_print_action

COMPANY = "_Test Company"
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"
MAKER = "_test.tsk600.maker@example.com"
SALES_APPROVER = "_test.tsk600.sales.approver@example.com"
PURCHASE_APPROVER = "_test.tsk600.purchase.approver@example.com"


def _ensure_user_and_employee(user: str, role: str, *, signature: str = SIGNATURE) -> None:
    if frappe.db.exists("User", user):
        user_doc = frappe.get_doc("User", user)
        user_doc.user_type = "System User"
        if role not in {row.role for row in user_doc.roles}:
            user_doc.append("roles", {"role": role})
        user_doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": user,
                "send_welcome_email": 0,
                "user_type": "System User",
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)

    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if employee_name:
        employee = frappe.get_doc("Employee", employee_name)
        employee.status = "Active"
        employee.approval_signature = signature
        employee.save(ignore_permissions=True)
        return

    department = frappe.db.get_value("Department", {"company": COMPANY}, "name")
    employment_type = frappe.db.get_value("Employment Type", {}, "name")
    if not department or not employment_type:
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
            "approval_signature": signature,
        }
    ).insert(ignore_permissions=True)


def _item() -> str:
    item = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
    if not item:
        raise AssertionError("A stock Item prerequisite is unavailable")
    return str(item)


def _warehouse() -> str:
    warehouse = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name")
    if not warehouse:
        raise AssertionError("A company Warehouse prerequisite is unavailable")
    return str(warehouse)


def _price_list() -> str:
    price_list = frappe.db.get_value("Price List", {"selling": 1}, "name")
    if not price_list:
        price_list = frappe.get_doc(
            {"doctype": "Price List", "price_list_name": "_Test TSK-600 Selling", "selling": 1, "buying": 0}
        ).insert(ignore_permissions=True).name
    return str(price_list)


def _customer() -> str:
    customer = frappe.db.get_value("Customer", {}, "name")
    if not customer:
        group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        if not group or not territory:
            raise AssertionError("Customer Group and Territory prerequisites are unavailable")
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "_Test TSK-600 Customer",
                "customer_code": "TSK600CUST",
                "customer_group": group,
                "territory": territory,
            }
        ).insert(ignore_permissions=True).name
    return str(customer)


def _sales_order() -> frappe.model.document.Document:
    return frappe.get_doc(
        {
            "doctype": "Sales Order",
            "company": COMPANY,
            "customer": _customer(),
            "transaction_date": frappe.utils.today(),
            "delivery_date": frappe.utils.today(),
            "selling_price_list": _price_list(),
            "price_list_currency": "THB",
            "plc_conversion_rate": 1,
            "items": [{"item_code": _item(), "qty": 1, "rate": 100, "warehouse": _warehouse()}],
        }
    ).insert(ignore_permissions=True)


def _material_request() -> frappe.model.document.Document:
    return frappe.get_doc(
        {
            "doctype": "Material Request",
            "company": COMPANY,
            "material_request_type": "Purchase",
            "purchase_reason": "TSK-600 signed approval integration test",
            "transaction_date": frappe.utils.today(),
            "schedule_date": frappe.utils.today(),
            "items": [
                {
                    "item_code": _item(),
                    "qty": 1,
                    "schedule_date": frappe.utils.today(),
                    "warehouse": _warehouse(),
                }
            ],
        }
    ).insert(ignore_permissions=True)


class TestSignedApprovalWorkflowIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    def _approve(self, doc: frappe.model.document.Document, maker: str, approver: str, action: str) -> None:
        frappe.set_user(maker)
        apply_workflow(doc, f"Submit {doc.doctype} for Review")
        frappe.set_user(approver)
        apply_workflow(doc.reload(), action)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_sales_order_and_material_request_approve_capture_active_signature(
        self, _send_email: object
    ) -> None:
        _ensure_user_and_employee(MAKER, "Sales User")
        _ensure_user_and_employee(MAKER, "Purchase User")
        _ensure_user_and_employee(MAKER, "Stock User")
        _ensure_user_and_employee(MAKER, "Accounts User")
        _ensure_user_and_employee(SALES_APPROVER, "Sales Manager")
        _ensure_user_and_employee(SALES_APPROVER, "Stock User")
        _ensure_user_and_employee(SALES_APPROVER, "Accounts User")
        _ensure_user_and_employee(PURCHASE_APPROVER, "Purchase Manager")
        _ensure_user_and_employee(PURCHASE_APPROVER, "Stock User")
        _ensure_user_and_employee(PURCHASE_APPROVER, "Accounts User")

        frappe.set_user("Administrator")
        sales_order = _sales_order()
        frappe.share.add("Sales Order", sales_order.name, MAKER, read=1, write=1)
        self._approve(sales_order, MAKER, SALES_APPROVER, "Approve Sales Order")
        sales_order.reload()
        self.assertEqual(sales_order.workflow_state, "Sales Order Approved")
        self.assertEqual(sales_order.authorized_by, frappe.db.get_value("Employee", {"user_id": SALES_APPROVER}, "name"))
        self.assertEqual(sales_order.authorized_signature, SIGNATURE)

        frappe.set_user("Administrator")
        material_request = _material_request()
        frappe.share.add("Material Request", material_request.name, MAKER, read=1, write=1)
        self._approve(material_request, MAKER, PURCHASE_APPROVER, "Approve Material Request")
        material_request.reload()
        self.assertEqual(material_request.workflow_state, "Material Request Approved")
        self.assertEqual(material_request.authorized_by, frappe.db.get_value("Employee", {"user_id": PURCHASE_APPROVER}, "name"))
        self.assertEqual(material_request.authorized_signature, SIGNATURE)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_approve_requires_active_employee_with_signature_and_preserves_state(
        self, _send_email: object
    ) -> None:
        _ensure_user_and_employee(MAKER, "Sales User")
        _ensure_user_and_employee(SALES_APPROVER, "Sales Manager", signature="")
        sales_order = _sales_order()
        frappe.set_user(MAKER)
        apply_workflow(sales_order, "Submit Sales Order for Review")
        before = frappe.db.get_value("Sales Order", sales_order.name, ["workflow_state", "authorized_signature"], as_dict=True)
        frappe.set_user(SALES_APPROVER)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(sales_order.reload(), "Approve Sales Order")
        after = frappe.db.get_value("Sales Order", sales_order.name, ["workflow_state", "authorized_signature"], as_dict=True)
        self.assertEqual(after, before)

        employee = frappe.get_doc("Employee", {"user_id": SALES_APPROVER})
        employee.status = "Inactive"
        employee.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(sales_order.reload(), "Approve Sales Order")
        self.assertEqual(frappe.db.get_value("Sales Order", sales_order.name, "workflow_state"), before.workflow_state)

    def test_snapshot_remains_immutable_when_employee_signature_changes(self) -> None:
        _ensure_user_and_employee(SALES_APPROVER, "Sales Manager")
        order = _sales_order()
        frappe.set_user(SALES_APPROVER)
        capture_print_action(order, "authorized")
        captured = order.authorized_signature
        employee = frappe.get_doc("Employee", {"user_id": SALES_APPROVER})
        employee.approval_signature = "changed-signature"
        employee.save(ignore_permissions=True)
        self.assertEqual(order.authorized_signature, captured)
