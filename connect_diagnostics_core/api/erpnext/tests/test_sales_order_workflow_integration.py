# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Integration checks against the shipped native Sales Order Workflow."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import sales_order_workflow


class TestSalesOrderWorkflowIntegration(IntegrationTestCase):
    def test_canonical_route_and_transition_tasks_are_live(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")
        workflow = frappe.get_doc("Workflow", "Connect Sales Order Blueprint")
        self.assertEqual(workflow.document_type, "Sales Order")
        self.assertEqual(workflow.is_active, 1)
        self.assertEqual(
            {row.state for row in workflow.states},
            {
                "Sales Order Draft",
                "Sales Order Pending Review",
                "Sales Order Reviewed",
                "Sales Order Approved",
                "Sales Order Submitted",
                "Sales Order Returned",
                "Sales Order Rejected",
                "Sales Order Cancelled",
            },
        )
        task_names = {row.transition_tasks for row in workflow.transitions if row.transition_tasks}
        self.assertEqual(
            task_names,
            {
                "Connect Sales Order Capture Maker",
                "Connect Sales Order Capture Review",
                "Connect Sales Order Capture Approval",
                "Connect Sales Order Clear Approval",
                "Connect Sales Order Submit Execution",
                "Connect Sales Order Cancel Execution",
            },
        )
        for name in task_names:
            task_doc = frappe.get_doc("Workflow Transition Tasks", name)
            self.assertEqual(len(task_doc.tasks), 1)
            self.assertEqual(task_doc.tasks[0].task, name)
            self.assertEqual(task_doc.tasks[0].enabled, 1)

    def test_direct_submit_of_real_draft_is_denied(self) -> None:
        for doctype, name in (
            ("Company", "_Test Company"),
            ("Item", "_Test Item"),
            ("Warehouse", "_Test Warehouse - _TC"),
            ("Customer Group", "_Test Customer Group"),
            ("Territory", "_Test Territory"),
        ):
            if not frappe.db.exists(doctype, name):
                self.skipTest(f"Missing ERPNext test master: {doctype} {name}")
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_code": f"_TEST-SO-{frappe.generate_hash(length=8)}",
                "customer_name": "_Test Sales Order Workflow Customer",
                "customer_group": "_Test Customer Group",
                "territory": "_Test Territory",
                "customer_type": "Company",
            }
        ).insert(ignore_permissions=True)
        currency = frappe.get_cached_value("Company", "_Test Company", "default_currency")
        price_list = frappe.db.get_value("Price List", {"enabled": 1}, "name")
        if not price_list:
            price_list = (
                frappe.get_doc(
                    {
                        "doctype": "Price List",
                        "price_list_name": f"_Test SO Workflow {frappe.generate_hash(length=8)}",
                        "enabled": 1,
                        "selling": 1,
                        "currency": currency,
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )
        order = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "customer": customer.name,
                "company": "_Test Company",
                "currency": currency,
                "selling_price_list": price_list,
                "price_list_currency": currency,
                "plc_conversion_rate": 1,
                "transaction_date": frappe.utils.today(),
                "delivery_date": frappe.utils.add_days(frappe.utils.today(), 10),
                "items": [
                    {
                        "item_code": "_Test Item",
                        "warehouse": "_Test Warehouse - _TC",
                        "qty": 1,
                        "rate": 100,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(order.workflow_state, "Sales Order Draft")
        frappe.db.savepoint("so_direct_submit")
        try:
            with self.assertRaises(frappe.ValidationError):
                order.submit()
        finally:
            frappe.db.rollback(save_point="so_direct_submit")
        self.assertEqual(frappe.db.get_value("Sales Order", order.name, "docstatus"), 0)
        self.assertIsNone(getattr(frappe.flags, "sales_order_submission", None))
        self.assertEqual(sales_order_workflow.APPROVAL_REVISION, "sales-order-native-v1")
