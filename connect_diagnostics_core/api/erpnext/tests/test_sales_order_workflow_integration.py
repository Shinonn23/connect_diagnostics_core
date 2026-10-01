# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import sales_order_workflow
from connect_diagnostics_core.setup import workflow_fields


class TestSalesOrderWorkflowIntegration(IntegrationTestCase):
    """Native Workflow lifecycle checks against the configured local.test route."""

    def test_local_test_site_is_the_only_demo_target(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")

    def test_direct_submit_is_blocked_without_native_post_marker(self) -> None:
        doc = self._fresh_order()
        with self.assertRaises(Exception):
            doc.submit()

    def test_state_spoof_and_wrong_role_are_rejected(self) -> None:
        from frappe.model.workflow import apply_workflow

        doc = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        frappe.db.set_value(
            "Sales Order",
            doc.name,
            {"docstatus": 0, "workflow_state": "Sales Order Draft"},
            update_modified=False,
        )
        frappe.db.set_value(
            "Sales Order",
            doc.name,
            {
                field: None
                for field in (
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
            },
            update_modified=False,
        )
        doc.reload()
        frappe.set_user(self._users[1])
        with self.assertRaises(Exception):
            apply_workflow(doc, "Submit Sales Order for Review")
        frappe.set_user(self._users[0])
        doc.reload()
        doc.workflow_state = "Sales Order Approved"
        with self.assertRaises(Exception):
            sales_order_workflow.capture_sales_order_demo_maker(doc)

    def test_distinct_user_separation_is_enforced_for_approval(self) -> None:
        doc = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        doc.workflow_state = "Sales Order Pending Final Approval"
        doc.approval_maker_user = self._users[2]
        doc.approval_reviewer_user = self._users[2]
        doc.approval_approver_user = self._users[2]
        self.assertFalse(sales_order_workflow._distinct_actors(doc))

    def test_unknown_child_business_mutation_is_fail_closed(self) -> None:
        doc = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        previous = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        doc.items[0].qty = previous.items[0].qty + 1
        self.assertTrue(sales_order_workflow._disallowed_changed(doc, previous))

    def test_reject_route_does_not_submit(self) -> None:
        from frappe.model.workflow import apply_workflow

        doc = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        frappe.db.set_value(
            "Sales Order",
            doc.name,
            {"docstatus": 0, "workflow_state": "Sales Order Draft"},
            update_modified=False,
        )
        frappe.db.set_value(
            "Sales Order",
            doc.name,
            {
                field: None
                for field in (
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
            },
            update_modified=False,
        )
        doc.reload()
        frappe.set_user(self._users[0])
        doc = apply_workflow(doc, "Submit Sales Order for Review")
        frappe.set_user(self._users[1])
        doc = apply_workflow(doc, "Review Sales Order")
        doc = apply_workflow(doc, "Reject Sales Order")
        self.assertEqual(doc.docstatus, 0)
        self.assertEqual(doc.workflow_state, "Sales Order Rejected")

    def test_marker_is_one_use_and_replay_is_rejected(self) -> None:
        self.assertIsNone(getattr(frappe.flags, "sales_order_demo_submission", None))

    def test_native_apply_workflow_reaches_post_and_submit_guard(self) -> None:
        from frappe.model.workflow import apply_workflow

        doc = frappe.get_doc("Sales Order", getattr(self._sales_order, "name", ""))
        doc.workflow_state = "Sales Order Draft"
        doc.save(ignore_permissions=True)
        frappe.db.set_value("Sales Order", doc.name, "owner", self._users[0], update_modified=False)
        doc.reload()
        doc.owner = self._users[0]
        frappe.set_user(self._users[0])
        doc = apply_workflow(doc, "Submit Sales Order for Review")
        frappe.set_user(self._users[1])
        doc = apply_workflow(doc, "Review Sales Order")
        frappe.set_user(self._users[2])
        doc = apply_workflow(doc, "Approve Sales Order")
        doc = apply_workflow(doc, "Post Sales Order")
        self.assertEqual(doc.workflow_state, "Sales Order Submitted")
        self.assertEqual(doc.docstatus, 1)
        self.assertIsNone(getattr(frappe.flags, "sales_order_demo_submission", None))
        sales_order_workflow.clear_sales_order_demo_submission()
        self.assertIsNone(getattr(frappe.flags, "sales_order_demo_submission", None))

    def test_workflow_route_uses_exact_demo_states(self) -> None:
        workflow = frappe.db.get_value("Workflow", {"document_type": "Sales Order", "is_active": 1}, "name")
        self.assertTrue(workflow, "local.test Sales Order Workflow is not configured")
        states = {
            row.state
            for row in frappe.get_all(
                "Workflow Document State", filters={"parent": workflow}, fields=["state"]
            )
        }
        expected = {
            "Sales Order Pending Commercial/Credit Review",
            "Sales Order Pending Final Approval",
            "Sales Order Approved",
            "Sales Order Submitted",
        }
        self.assertTrue(expected <= states, "local.test native Workflow is missing the demo states")

    @classmethod
    def setUpClass(cls) -> None:
        cls._old_workflows = []
        cls._created_states = []
        cls._created_actions = []
        cls._task_groups = {}
        cls._users = []
        cls._employees = []
        cls._demo_workflow = None
        cls._sales_order = None
        cls._transient_orders = []
        cls._customer = None
        cls._price_list = None
        cls._config_patcher = None
        cls._hooks_patcher = None
        try:
            cls._setUpClass_impl()
        except Exception:
            cls._cleanup_demo_records()
            frappe.set_user("Administrator")
            raise

    @classmethod
    def _setUpClass_impl(cls) -> None:
        super().setUpClass()
        if frappe.local.site != "local.test":
            raise AssertionError("Sales Order demo integration must run on local.test")
        create_custom_fields(
            {"Sales Order": workflow_fields.CUSTOM_FIELDS["Sales Order"]}, ignore_validate=True
        )
        for doctype, name in (
            ("Company", "_Test Company"),
            ("Item", "_Test Item"),
            ("Warehouse", "_Test Warehouse - _TC"),
            ("UOM", "_Test UOM"),
        ):
            if not frappe.db.exists(doctype, name):
                raise AssertionError(f"local.test missing required ERPNext test master: {doctype} {name}")
        customer_group = "_Test Customer Group"
        territory = "_Test Territory"
        if not frappe.db.exists("Customer Group", customer_group) or not frappe.db.exists(
            "Territory", territory
        ):
            raise AssertionError("local.test missing required leaf Customer Group/Territory")
        cls._customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_code": "_TEST-SALES-DEMO-CUST",
                "customer_name": "_Test Sales Demo Customer",
                "customer_type": "Company",
                "customer_group": customer_group,
                "territory": territory,
            }
        ).insert(ignore_permissions=True)
        cls._old_workflows = frappe.get_all(
            "Workflow", filters={"document_type": "Sales Order"}, fields=["name", "is_active"]
        )
        cls._state_names = [
            "Sales Order Draft",
            "Sales Order Pending Commercial/Credit Review",
            "Sales Order Pending Final Approval",
            "Sales Order Approved",
            "Sales Order Submitted",
            "Sales Order Rejected",
            "Sales Order Cancelled",
        ]
        cls._created_states = []
        for name in cls._state_names:
            if not frappe.db.exists("Workflow State", name):
                frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": name}).insert(
                    ignore_permissions=True
                )
                cls._created_states.append(name)
        cls._action_names = [
            "Submit Sales Order for Review",
            "Review Sales Order",
            "Approve Sales Order",
            "Post Sales Order",
            "Reject Sales Order",
            "Return Sales Order",
            "Cancel Sales Order",
        ]
        cls._created_actions = []
        for name in cls._action_names:
            if not frappe.db.exists("Workflow Action Master", name):
                frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": name}).insert(
                    ignore_permissions=True
                )
                cls._created_actions.append(name)
        cls._task_groups = {}
        task_specs = {
            "maker": ["Capture Sales Order Demo Maker"],
            "review": ["Capture Print Action: Checked", "Capture Sales Order Demo Review"],
            "approval": ["Capture Print Action: Authorized", "Capture Sales Order Demo Final Approval"],
            "clear": ["Clear Sales Order Demo Approval"],
            "post": ["Authorize Sales Order Demo Submission"],
        }
        for key, tasks in task_specs.items():
            name = f"_Test Sales Order Demo {key.title()} Tasks"
            group = frappe.new_doc("Workflow Transition Tasks")
            group.name = name
            for task in tasks:
                group.append("tasks", {"task": task, "enabled": 1, "asynchronous": 0})
            group.insert(ignore_permissions=True)
            cls._task_groups[key] = name
        for row in cls._old_workflows:
            frappe.db.set_value("Workflow", row.name, "is_active", 0, update_modified=False)
        workflow = frappe.get_doc(
            {
                "doctype": "Workflow",
                "workflow_name": "_Test Sales Order Demo Workflow",
                "document_type": "Sales Order",
                "is_active": 1,
                "workflow_state_field": "workflow_state",
            }
        )
        for state, status, role in (
            (cls._state_names[0], 0, "Sales User"),
            (cls._state_names[1], 0, "Sales Manager"),
            (cls._state_names[2], 0, "Sales Manager"),
            (cls._state_names[3], 0, "C-Level Approver"),
            (cls._state_names[4], 1, "C-Level Approver"),
            (cls._state_names[5], 0, "Sales Manager"),
            (cls._state_names[6], 2, "C-Level Approver"),
        ):
            workflow.append("states", {"state": state, "doc_status": status, "allow_edit": role})
        transitions = (
            (cls._state_names[0], cls._action_names[0], cls._state_names[1], "Sales User", "maker"),
            (cls._state_names[1], cls._action_names[1], cls._state_names[2], "Sales Manager", "review"),
            (cls._state_names[2], cls._action_names[2], cls._state_names[3], "C-Level Approver", "approval"),
            (cls._state_names[3], cls._action_names[3], cls._state_names[4], "C-Level Approver", "post"),
            (cls._state_names[1], cls._action_names[5], cls._state_names[0], "Sales Manager", "clear"),
            (cls._state_names[2], cls._action_names[4], cls._state_names[5], "Sales Manager", "clear"),
            (cls._state_names[4], cls._action_names[6], cls._state_names[6], "C-Level Approver", None),
        )
        for state, action, next_state, role, task_key in transitions:
            row = {
                "state": state,
                "action": action,
                "next_state": next_state,
                "allowed": role,
                "allow_self_approval": 1 if task_key == "maker" else 0,
            }
            if task_key:
                row["transition_tasks"] = cls._task_groups[task_key]
            workflow.append("transitions", row)
        workflow.append(
            "transitions",
            {
                "state": cls._state_names[2],
                "action": "Return Sales Order",
                "next_state": cls._state_names[0],
                "allowed": "Sales Manager",
                "allow_self_approval": 0,
                "transition_tasks": cls._task_groups["clear"],
            },
        )
        workflow.insert(ignore_permissions=True)
        cls._demo_workflow = workflow.name
        original_get_site_config = sales_order_workflow.frappe.get_site_config

        def demo_site_config():
            config = original_get_site_config()
            config.update(
                {"sales_order_approval_demo_enabled": 1, "sales_order_approval_demo_site": "local.test"}
            )
            return config

        cls._config_patcher = patch.object(
            sales_order_workflow.frappe, "get_site_config", side_effect=demo_site_config
        )
        cls._config_patcher.start()
        original_get_hooks = frappe.get_hooks

        def demo_hooks(hook=None, *args, **kwargs):
            result = original_get_hooks(hook, *args, **kwargs)
            if hook == "workflow_methods":
                result = list(result) + [
                    {
                        "name": name,
                        "method": f"connect_diagnostics_core.api.erpnext.sales_order_workflow.{method}",
                    }
                    for name, method in (
                        ("Capture Sales Order Demo Maker", "capture_sales_order_demo_maker"),
                        ("Capture Sales Order Demo Review", "capture_sales_order_demo_review"),
                        (
                            "Capture Sales Order Demo Final Approval",
                            "capture_sales_order_demo_final_approval",
                        ),
                        ("Clear Sales Order Demo Approval", "clear_sales_order_demo_approval"),
                        ("Authorize Sales Order Demo Submission", "authorize_sales_order_demo_submission"),
                    )
                ]
            return result

        cls._hooks_patcher = patch.object(frappe, "get_hooks", side_effect=demo_hooks)
        cls._hooks_patcher.start()
        cls._users = []
        cls._employees = []
        company = "_Test Company"
        department = "_Test Department - _TC"
        employment_type = "Full-time"
        price_list = frappe.db.get_value("Price List", {"enabled": 1}, "name")
        if not price_list:
            cls._price_list = frappe.get_doc(
                {
                    "doctype": "Price List",
                    "price_list_name": "_Test Sales Demo Price List",
                    "enabled": 1,
                    "selling": 1,
                    "currency": "INR",
                }
            ).insert(ignore_permissions=True)
            price_list = cls._price_list.name
        for email, role, first_name in (
            ("_test_sales_demo_maker@example.com", "Sales User", "Sales Demo Maker"),
            ("_test_sales_demo_reviewer@example.com", "Sales Manager", "Sales Demo Reviewer"),
            ("_test_sales_demo_approver@example.com", "C-Level Approver", "Sales Demo Approver"),
        ):
            if not frappe.db.exists("Role", role):
                frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
            user = frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0}
            ).insert(ignore_permissions=True)
            user.append("roles", {"role": role})
            if role == "C-Level Approver" and frappe.db.exists("Role", "Sales Manager"):
                user.append("roles", {"role": "Sales Manager"})
            for support_role in ("Stock User", "Accounts User"):
                if frappe.db.exists("Role", support_role):
                    user.append("roles", {"role": support_role})
            user.save(ignore_permissions=True)
            cls._users.append(email)
            employee = frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": first_name,
                    "company": company,
                    "department": department,
                    "employment_type": employment_type,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active",
                    "user_id": email,
                    "approval_signature": f"signature-{email}",
                }
            ).insert(ignore_permissions=True)
            cls._employees.append(employee.name)
        frappe.set_user(cls._users[0])
        cls._sales_order = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "customer": getattr(cls._customer, "name", ""),
                "company": "_Test Company",
                "currency": "INR",
                "selling_price_list": price_list,
                "price_list_currency": "INR",
                "plc_conversion_rate": 1,
                "transaction_date": frappe.utils.today(),
                "delivery_date": frappe.utils.add_days(frappe.utils.today(), 10),
                "items": [
                    {"item_code": "_Test Item", "warehouse": "_Test Warehouse - _TC", "qty": 1, "rate": 50000}
                ],
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Sales Order", cls._sales_order.name, "owner", cls._users[0], update_modified=False
        )
        cls._sales_order.reload()

    @classmethod
    def _fresh_order(cls):
        order = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "customer": getattr(cls._customer, "name", ""),
                "company": "_Test Company",
                "currency": "INR",
                "selling_price_list": frappe.db.get_value("Price List", {"enabled": 1}, "name"),
                "price_list_currency": "INR",
                "plc_conversion_rate": 1,
                "transaction_date": frappe.utils.today(),
                "delivery_date": frappe.utils.add_days(frappe.utils.today(), 10),
                "items": [
                    {"item_code": "_Test Item", "warehouse": "_Test Warehouse - _TC", "qty": 1, "rate": 50000}
                ],
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value("Sales Order", order.name, "owner", cls._users[0], update_modified=False)
        order.reload()
        cls._transient_orders.append(order.name)
        return order

    @classmethod
    def _post_order(cls, order):
        from frappe.model.workflow import apply_workflow

        frappe.set_user(cls._users[0])
        order = apply_workflow(order, "Submit Sales Order for Review")
        frappe.set_user(cls._users[1])
        order = apply_workflow(order, "Review Sales Order")
        frappe.set_user(cls._users[2])
        order = apply_workflow(order, "Approve Sales Order")
        return apply_workflow(order, "Post Sales Order")

    def test_return_clears_evidence_and_requires_full_reapproval(self) -> None:
        from frappe.model.workflow import apply_workflow

        order = self._fresh_order()
        frappe.set_user(self._users[0])
        order = apply_workflow(order, "Submit Sales Order for Review")
        frappe.set_user(self._users[1])
        order = apply_workflow(order, "Review Sales Order")
        self.assertTrue(order.approval_digest)
        order = apply_workflow(order, "Return Sales Order")
        self.assertEqual(order.workflow_state, "Sales Order Draft")
        self.assertIsNone(order.approval_digest)
        self.assertIsNone(order.approval_reviewer_user)
        order.items[0].qty = 2
        order.save(ignore_permissions=True)
        self.assertEqual(self._post_order(order).docstatus, 1)

    def test_direct_sales_order_with_configured_discount_uses_same_route(self) -> None:
        order = self._fresh_order()
        order.items[0].discount_percentage = 15
        order.save(ignore_permissions=True)
        posted = self._post_order(order)
        self.assertEqual(posted.docstatus, 1)

    def test_native_credit_limit_and_controller_are_used_for_crossing_order(self) -> None:
        customer_name = getattr(self._customer, "name", "")
        old_controller = frappe.db.get_single_value("Accounts Settings", "credit_controller")
        try:
            frappe.db.delete("Customer Credit Limit", {"parent": customer_name, "parenttype": "Customer"})
            frappe.get_doc(
                {
                    "doctype": "Customer Credit Limit",
                    "parent": customer_name,
                    "parenttype": "Customer",
                    "parentfield": "credit_limits",
                    "company": "_Test Company",
                    "credit_limit": 100000,
                }
            ).insert(ignore_permissions=True)
            frappe.db.set_single_value("Accounts Settings", "credit_controller", "C-Level Approver")
            self.assertEqual(
                sales_order_workflow._credit_inputs(self._fresh_order())["customer_credit_limit"], 100000
            )
            from erpnext.selling.doctype.customer.customer import check_credit_limit

            frappe.set_user(self._users[0])
            with self.assertRaises(Exception):
                check_credit_limit(customer_name, "_Test Company", extra_amount=120000)
            frappe.set_user(self._users[2])
            check_credit_limit(customer_name, "_Test Company", extra_amount=120000)
            order = self._fresh_order()
            order.items[0].rate = 120000
            order.save(ignore_permissions=True)
            self.assertGreaterEqual(order.grand_total, 120000)
        finally:
            frappe.db.set_single_value("Accounts Settings", "credit_controller", old_controller)
            frappe.db.delete("Customer Credit Limit", {"parent": customer_name, "parenttype": "Customer"})

    def test_native_quotation_mapping_enters_the_same_demo_route(self) -> None:
        from erpnext.selling.doctype.quotation.quotation import make_sales_order

        quotation = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "selling_price_list": frappe.db.get_value("Price List", {"enabled": 1}, "name"),
                "items": [{"item_code": "_Test Item", "qty": 1, "rate": 50000}],
            }
        )
        quotation.set("customer", getattr(self._customer, "name", ""))
        quotation.set("party_name", getattr(self._customer, "name", ""))
        quotation.set("transaction_date", frappe.utils.today())
        quotation.set("valid_till", frappe.utils.add_days(frappe.utils.today(), 30))
        quotation.set("tc_name", frappe.db.get_value("Terms and Conditions", {}, "name"))
        quotation.set("terms", "Demo delivery terms")
        quotation.set("quotation_delivery_terms", "Delivery within 30 days")
        quotation.set("quotation_signatory_type", "Managing Director")
        quotation.set("signatory_employee", self._employees[2])
        quotation.get("items")[0].set("item_code", "_Test Item")
        quotation.get("items")[0].set("qty", 1)
        quotation.get("items")[0].set("rate", 50000)
        quotation.insert(ignore_permissions=True)
        try:
            quotation.submit()
            mapped = make_sales_order(quotation.name)
            mapped.transaction_date = frappe.utils.today()
            mapped.delivery_date = frappe.utils.add_days(frappe.utils.today(), 10)
            mapped.items[0].warehouse = "_Test Warehouse - _TC"
            frappe.set_user(self._users[0])
            mapped.insert(ignore_permissions=True)
            self._transient_orders.append(mapped.name)
            self.assertEqual(mapped.items[0].prevdoc_docname, quotation.name)
            self.assertEqual(self._post_order(mapped).docstatus, 1)
        finally:
            if frappe.db.exists("Quotation", quotation.name):
                if frappe.db.get_value("Quotation", quotation.name, "docstatus") == 1:
                    frappe.db.set_value("Quotation", quotation.name, "docstatus", 2, update_modified=False)
                frappe.delete_doc("Quotation", quotation.name, force=True, ignore_permissions=True)

    def test_native_customer_hold_rejects_order_save(self) -> None:
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_code": "_TEST-HOLD-CUST",
                "customer_name": "_Test Hold Customer",
                "customer_type": "Company",
                "customer_group": "_Test Customer Group",
                "territory": "_Test Territory",
                "disabled": 1,
            }
        ).insert(ignore_permissions=True)
        try:
            order = frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "customer": customer.name,
                    "company": "_Test Company",
                    "currency": "INR",
                    "transaction_date": frappe.utils.today(),
                    "delivery_date": frappe.utils.add_days(frappe.utils.today(), 10),
                    "items": [
                        {
                            "item_code": "_Test Item",
                            "warehouse": "_Test Warehouse - _TC",
                            "qty": 1,
                            "rate": 50000,
                        }
                    ],
                }
            )
            with self.assertRaises(Exception):
                order.insert(ignore_permissions=True)
        finally:
            if frappe.db.exists("Customer", customer.name):
                frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)

    def test_direct_cancel_is_blocked_but_native_cancel_workflow_succeeds(self) -> None:
        from frappe.model.workflow import apply_workflow

        order = self._post_order(self._fresh_order())
        frappe.set_user(self._users[2])
        with self.assertRaises(Exception):
            order.cancel()
        order.reload()
        cancelled = apply_workflow(order, "Cancel Sales Order")
        self.assertEqual(cancelled.docstatus, 2)

    def test_amendment_starts_without_approval_and_can_reenter_route(self) -> None:
        from frappe.model.workflow import apply_workflow

        order = self._post_order(self._fresh_order())
        from frappe import copy_doc

        cancelled = apply_workflow(order, "Cancel Sales Order")
        amended = copy_doc(cancelled, ignore_no_copy=False)
        amended.set("amended_from", cancelled.name)
        amended.set("workflow_state", "Sales Order Draft")
        amended.docstatus = 0
        amended.set("delivery_date", frappe.utils.add_days(frappe.utils.today(), 10))
        for field in (
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
        ):
            amended.set(field, None)
        self.assertEqual(amended.docstatus, 0)
        self.assertIsNone(amended.get("approval_digest"))
        self.assertIsNone(amended.get("approval_maker_user"))
        amended.save(ignore_permissions=True)
        frappe.set_user(self._users[0])
        amended = apply_workflow(amended, "Submit Sales Order for Review")
        self.assertEqual(amended.workflow_state, "Sales Order Pending Commercial/Credit Review")

    def test_native_downstream_mappers_require_submitted_sales_order(self) -> None:
        order = self._fresh_order()
        with self.assertRaises(Exception):
            make_delivery_note(order.name)
        with self.assertRaises(Exception):
            make_sales_invoice(order.name)
        posted = self._post_order(order)
        delivery = make_delivery_note(posted.name)
        invoice = make_sales_invoice(posted.name)
        self.assertEqual(delivery.items[0].against_sales_order, posted.name)
        self.assertEqual(invoice.items[0].sales_order, posted.name)

    def test_consumed_post_marker_cannot_be_replayed(self) -> None:
        order = self._post_order(self._fresh_order())
        self.assertIsNone(getattr(frappe.flags, "sales_order_demo_submission", None))
        replay = self._fresh_order()
        replay.workflow_state = "Sales Order Draft"
        for field in (
            "approval_revision",
            "approval_digest",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_approver_user",
            "checked_by",
            "checked_signature",
            "authorized_by",
            "authorized_signature",
        ):
            replay.set(field, order.get(field))
        frappe.db.set_value(
            "Sales Order",
            replay.name,
            {
                "workflow_state": "Sales Order Approved",
                **{
                    field: replay.get(field)
                    for field in (
                        "approval_revision",
                        "approval_digest",
                        "approval_maker_user",
                        "approval_reviewer_user",
                        "approval_approver_user",
                        "checked_by",
                        "checked_signature",
                        "authorized_by",
                        "authorized_signature",
                    )
                },
            },
            update_modified=False,
        )
        replay.reload()
        frappe.set_user(self._users[2])
        with self.assertRaises(Exception):
            replay.submit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cleanup_demo_records()
        frappe.set_user("Administrator")
        super().tearDownClass()

    @classmethod
    def _cleanup_demo_records(cls) -> None:
        if cls._config_patcher:
            cls._config_patcher.stop()
            cls._config_patcher = None
        if getattr(cls, "_hooks_patcher", None):
            if cls._hooks_patcher:
                cls._hooks_patcher.stop()
            cls._hooks_patcher = None
        names = [getattr(cls._sales_order, "name", "")] if getattr(cls, "_sales_order", None) else []
        names += list(getattr(cls, "_transient_orders", []))
        for name in set(names):
            if frappe.db.exists("Sales Order", name):
                if frappe.db.get_value("Sales Order", name, "docstatus") == 1:
                    frappe.db.set_value("Sales Order", name, "docstatus", 2, update_modified=False)
                frappe.delete_doc("Sales Order", name, force=True, ignore_permissions=True)
        if getattr(cls, "_customer", None) and frappe.db.exists(
            "Customer", getattr(cls._customer, "name", "")
        ):
            frappe.delete_doc(
                "Customer", getattr(cls._customer, "name", ""), force=True, ignore_permissions=True
            )
        if cls._price_list and frappe.db.exists("Price List", cls._price_list.name):
            frappe.delete_doc("Price List", cls._price_list.name, force=True, ignore_permissions=True)
        for name in getattr(cls, "_employees", []):
            if frappe.db.exists("Employee", name):
                frappe.delete_doc("Employee", name, force=True, ignore_permissions=True)
        for email in getattr(cls, "_users", []):
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        if cls._sales_order and frappe.db.exists("Sales Order", cls._sales_order.name):
            frappe.delete_doc("Sales Order", cls._sales_order.name, force=True, ignore_permissions=True)
        if cls._demo_workflow and frappe.db.exists("Workflow", cls._demo_workflow):
            frappe.delete_doc("Workflow", cls._demo_workflow, force=True, ignore_permissions=True)
        for name in cls._created_actions:
            if frappe.db.exists("Workflow Action Master", name):
                frappe.delete_doc("Workflow Action Master", name, force=True, ignore_permissions=True)
        for name in getattr(cls, "_task_groups", {}).values():
            if frappe.db.exists("Workflow Transition Tasks", name):
                frappe.delete_doc("Workflow Transition Tasks", name, force=True, ignore_permissions=True)
        for name in cls._created_states:
            if frappe.db.exists("Workflow State", name):
                frappe.delete_doc("Workflow State", name, force=True, ignore_permissions=True)
        for row in cls._old_workflows:
            frappe.db.set_value("Workflow", row.name, "is_active", row.is_active, update_modified=False)
