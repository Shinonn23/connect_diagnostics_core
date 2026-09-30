# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import ClassVar, cast

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from connect_diagnostics_core.api.erpnext import payment_entry_approval_poc as poc


class TestPaymentEntryApprovalPOCIntegration(IntegrationTestCase):
    """Exercise the disposable route with real Workflow and Payment Entry lifecycle calls."""

    WORKFLOW = "_Test POC Payment Entry Approval"
    PENDING_CHECK_STATE = "Payment Entry Pending Check"
    ACTIONS: ClassVar[dict[str, str]] = {
        "send": "_Test POC Send Payment Entry",
        "check": "_Test POC Check Payment Entry",
        "approve": "_Test POC Approve Payment Entry",
        "post": "_Test POC Post Payment Entry",
        "return": "_Test POC Return Payment Entry",
        "reject": "_Test POC Reject Payment Entry",
        "resubmit": "_Test POC Resubmit Payment Entry",
        "cancel": "_Test POC Cancel Payment Entry",
    }
    TASKS: ClassVar[dict[str, tuple[str, str]]] = {
        "maker": ("_Test POC PE Maker Tasks", "POC Payment Entry Maker"),
        "checker": ("_Test POC PE Checker Tasks", "POC Payment Entry Checker"),
        "approver": ("_Test POC PE Approver Tasks", "POC Payment Entry Approver"),
        "submit": ("_Test POC PE Submit Tasks", "POC Payment Entry Submit"),
        "return": ("_Test POC PE Return Tasks", "POC Payment Entry Return"),
        "reject": ("_Test POC PE Reject Tasks", "POC Payment Entry Reject"),
    }
    USERS: ClassVar[dict[str, str]] = {
        "maker": "_test_pe_poc_maker@example.com",
        "checker": "_test_pe_poc_checker@example.com",
        "approver": "_test_pe_poc_approver@example.com",
    }
    baseline_workflows: ClassVar[list[str]]
    baseline_actions: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if frappe.local.site != poc.ENABLED_SITE:
            raise AssertionError("Payment Entry POC integration tests require local.test")

        cls._assert_snapshot_metadata()
        cls.baseline_workflows = frappe.get_all(
            "Workflow",
            filters={"document_type": "Payment Entry", "is_active": 1},
            pluck="name",
        )
        cls.baseline_actions = frappe.get_all(
            "Workflow Action",
            filters={"reference_doctype": "Payment Entry", "status": "Open"},
            pluck="name",
        )
        cls._assert_no_collisions()
        cls._configure_test_company_thai_tax()
        cls._make_users()
        cls._make_workflow()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            frappe.clear_cache(doctype="Payment Entry")
            active = frappe.get_all(
                "Workflow",
                filters={"document_type": "Payment Entry", "is_active": 1},
                pluck="name",
            )
            actions = frappe.get_all(
                "Workflow Action",
                filters={"reference_doctype": "Payment Entry", "status": "Open"},
                pluck="name",
            )
            if sorted(active) != sorted(cls.baseline_workflows):
                raise AssertionError("Payment Entry Workflow baseline was not restored")
            if sorted(actions) != sorted(cls.baseline_actions):
                raise AssertionError("Payment Entry Workflow Actions were not restored")
        finally:
            super().tearDownClass()

    @classmethod
    def _assert_snapshot_metadata(cls) -> None:
        meta = frappe.get_meta("Payment Entry")
        missing = [fieldname for fieldname in poc.SNAPSHOT_FIELDS if not meta.has_field(fieldname)]
        if missing:
            raise AssertionError(f"Payment Entry snapshot fields are missing: {', '.join(missing)}")
        for fieldname in poc.SNAPSHOT_FIELDS:
            field = meta.get_field(fieldname)
            if not field or not field.read_only:
                raise AssertionError(f"Payment Entry snapshot field must be read-only: {fieldname}")

    @classmethod
    def _assert_no_collisions(cls) -> None:
        collisions: list[str] = []
        candidates = [
            ("Workflow", cls.WORKFLOW),
            ("Workflow State", cls.PENDING_CHECK_STATE),
            *[("Workflow Action Master", name) for name in cls.ACTIONS.values()],
            *[("Workflow Transition Tasks", name) for name, _task in cls.TASKS.values()],
        ]
        for doctype, name in candidates:
            if frappe.db.exists(doctype, name):
                collisions.append(f"{doctype} {name}")
        if collisions:
            raise AssertionError("POC configuration collision: " + ", ".join(collisions))

    @classmethod
    def _make_users(cls) -> None:
        roles = {
            "maker": (poc.MAKER_ROLE,),
            "checker": (poc.CHECKER_ROLE,),
            "approver": (poc.APPROVER_ROLE, poc.MAKER_ROLE),
        }
        department = frappe.get_all("Department", pluck="name", limit=1)[0]
        for actor, user in cls.USERS.items():
            user_doc = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": user,
                    "first_name": actor.title(),
                    "enabled": 1,
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
            user_doc.add_roles(*roles[actor])
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "naming_series": "EMP-",
                    "first_name": actor.title(),
                    "company": "_Test Company",
                    "user_id": user,
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2026-01-01",
                    "department": department,
                    "gender": "Female",
                    "status": "Active",
                    "employment_type": "Intern",
                    "approval_signature": f"data:image/png;base64,{actor}",
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def _configure_test_company_thai_tax(cls) -> None:
        settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == "_Test Company" for row in settings.company_accounts):
            settings.append("company_accounts", {"company": "_Test Company"})
            settings.save(ignore_permissions=True)

    @classmethod
    def _make_workflow(cls) -> None:
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Workflow",
            {"document_type": "Payment Entry", "is_active": 1},
            "is_active",
            0,
            update_modified=False,
        )
        frappe.get_doc(
            {
                "doctype": "Workflow State",
                "workflow_state_name": cls.PENDING_CHECK_STATE,
            }
        ).insert(ignore_permissions=True)
        for action in cls.ACTIONS.values():
            frappe.get_doc(
                {
                    "doctype": "Workflow Action Master",
                    "workflow_action_name": action,
                }
            ).insert(ignore_permissions=True)
        for name, task in cls.TASKS.values():
            frappe.get_doc(
                {
                    "doctype": "Workflow Transition Tasks",
                    "name": name,
                    "tasks": [{"task": task, "enabled": 1, "asynchronous": 0}],
                }
            ).insert(ignore_permissions=True)

        workflow = frappe.get_doc(
            {
                "doctype": "Workflow",
                "workflow_name": cls.WORKFLOW,
                "document_type": "Payment Entry",
                "workflow_state_field": "workflow_state",
                "is_active": 1,
                "enable_action_confirmation": 1,
                "states": [
                    {"state": poc.DRAFT, "doc_status": "0", "allow_edit": poc.MAKER_ROLE},
                    {"state": poc.PENDING_CHECK, "doc_status": "0", "allow_edit": poc.CHECKER_ROLE},
                    {"state": poc.PENDING_APPROVAL, "doc_status": "0", "allow_edit": poc.APPROVER_ROLE},
                    {"state": poc.APPROVED, "doc_status": "0", "allow_edit": poc.CHECKER_ROLE},
                    {"state": poc.REJECTED, "doc_status": "0", "allow_edit": poc.MAKER_ROLE},
                    {"state": poc.SUBMITTED, "doc_status": "1", "allow_edit": poc.CHECKER_ROLE},
                    {"state": "Payment Entry Cancelled", "doc_status": "2", "allow_edit": poc.CHECKER_ROLE},
                ],
                "transitions": [
                    cls._transition(
                        poc.DRAFT, cls.ACTIONS["send"], poc.PENDING_CHECK, poc.MAKER_ROLE, "maker"
                    ),
                    cls._transition(
                        poc.PENDING_CHECK,
                        cls.ACTIONS["check"],
                        poc.PENDING_APPROVAL,
                        poc.CHECKER_ROLE,
                        "checker",
                    ),
                    cls._transition(
                        poc.PENDING_APPROVAL,
                        cls.ACTIONS["approve"],
                        poc.APPROVED,
                        poc.APPROVER_ROLE,
                        "approver",
                    ),
                    cls._transition(
                        poc.APPROVED, cls.ACTIONS["post"], poc.SUBMITTED, poc.CHECKER_ROLE, "submit"
                    ),
                    cls._transition(
                        poc.PENDING_CHECK,
                        cls.ACTIONS["return"],
                        poc.DRAFT,
                        poc.CHECKER_ROLE,
                        "return",
                    ),
                    cls._transition(
                        poc.PENDING_APPROVAL,
                        cls.ACTIONS["reject"],
                        poc.REJECTED,
                        poc.APPROVER_ROLE,
                        "reject",
                    ),
                    cls._transition(
                        poc.REJECTED,
                        cls.ACTIONS["resubmit"],
                        poc.PENDING_CHECK,
                        poc.MAKER_ROLE,
                        "maker",
                    ),
                    {
                        "state": poc.SUBMITTED,
                        "action": cls.ACTIONS["cancel"],
                        "next_state": "Payment Entry Cancelled",
                        "allowed": poc.CHECKER_ROLE,
                        "allow_self_approval": 0,
                    },
                ],
            }
        )
        workflow.insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Payment Entry")

    @classmethod
    def _transition(
        cls,
        state: str,
        action: str,
        next_state: str,
        allowed: str,
        task_key: str,
    ) -> dict[str, str | int]:
        return {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "allow_self_approval": 1 if task_key == "maker" else 0,
            "transition_tasks": cls.TASKS[task_key][0],
        }

    @contextmanager
    def _enabled(self) -> Iterator[None]:
        old_site = frappe.local.site
        had_flag = poc.ENABLED_FLAG in frappe.conf
        old_flag = frappe.conf.get(poc.ENABLED_FLAG)
        had_key = "encryption_key" in frappe.conf
        old_key = frappe.conf.get("encryption_key")
        try:
            frappe.local.site = poc.ENABLED_SITE
            frappe.conf[poc.ENABLED_FLAG] = 1
            frappe.conf["encryption_key"] = "local-test-payment-entry-poc-key"
            yield
        finally:
            frappe.local.site = old_site
            if had_flag:
                frappe.conf[poc.ENABLED_FLAG] = old_flag
            else:
                frappe.conf.pop(poc.ENABLED_FLAG, None)
            if had_key:
                frappe.conf["encryption_key"] = old_key
            else:
                frappe.conf.pop("encryption_key", None)
            frappe.set_user("Administrator")

    def _new_payment_entry(self) -> PaymentEntry:
        frappe.set_user(self.USERS["maker"])
        payment_entry = cast(PaymentEntry, frappe.new_doc("Payment Entry"))
        payment_entry.set("company", "_Test Company")
        payment_entry.set("payment_type", "Pay")
        payment_entry.set("party_type", "Supplier")
        payment_entry.set("party", "_Test Supplier")
        payment_entry.set("paid_from", "_Test Bank - _TC")
        payment_entry.set("paid_to", "Creditors - _TC")
        payment_entry.set("paid_amount", 1000)
        payment_entry.setup_party_account_field()
        payment_entry.set_missing_values()
        payment_entry.set_exchange_rate()
        payment_entry.set(
            "received_amount",
            flt(payment_entry.get("paid_amount")) / flt(payment_entry.get("target_exchange_rate")),
        )
        payment_entry.set("reference_no", "POC-TEST-001")
        payment_entry.set("reference_date", nowdate())
        payment_entry.insert()
        return payment_entry

    def test_state_spoof_and_direct_submit_are_blocked(self) -> None:
        with self._enabled():
            payment_entry = self._new_payment_entry()
            payment_entry.set("workflow_state", poc.APPROVED)
            with self.assertRaises(frappe.ValidationError):
                payment_entry.save()
            payment_entry.reload()
            with self.assertRaises(frappe.ValidationError):
                payment_entry.submit()

    def test_real_workflow_posts_once_and_preserves_native_cancel(self) -> None:
        with self._enabled():
            payment_entry = self._new_payment_entry()
            payment_entry = cast(PaymentEntry, apply_workflow(payment_entry, self.ACTIONS["send"]))
            self.assertEqual(payment_entry.get("workflow_state"), poc.PENDING_CHECK)
            self.assertTrue(payment_entry.get("submit_by"))

            frappe.set_user(self.USERS["checker"])
            payment_entry = cast(PaymentEntry, apply_workflow(payment_entry, self.ACTIONS["check"]))
            self.assertEqual(payment_entry.get("workflow_state"), poc.PENDING_APPROVAL)
            self.assertTrue(payment_entry.get("checked_signature"))

            frappe.set_user(self.USERS["approver"])
            payment_entry = cast(PaymentEntry, apply_workflow(payment_entry, self.ACTIONS["approve"]))
            self.assertEqual(payment_entry.get("workflow_state"), poc.APPROVED)
            self.assertTrue(payment_entry.get("authorized_signature"))

            frappe.set_user(self.USERS["checker"])
            payment_entry = cast(PaymentEntry, apply_workflow(payment_entry, self.ACTIONS["post"]))
            self.assertEqual(payment_entry.docstatus, 1)
            self.assertEqual(payment_entry.get("workflow_state"), poc.SUBMITTED)
            gl_count = frappe.db.count(
                "GL Entry",
                {"voucher_type": "Payment Entry", "voucher_no": payment_entry.name},
            )
            self.assertGreater(gl_count, 0)
            payment_entry.submit()
            self.assertEqual(
                frappe.db.count(
                    "GL Entry",
                    {"voucher_type": "Payment Entry", "voucher_no": payment_entry.name},
                ),
                gl_count,
            )

            payment_entry = cast(PaymentEntry, apply_workflow(payment_entry, self.ACTIONS["cancel"]))
            self.assertEqual(payment_entry.docstatus, 2)
