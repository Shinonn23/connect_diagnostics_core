# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.model.document import Document
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import get_first_day, getdate, nowdate
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry, get_start_end_dates

from connect_diagnostics_core.api.frappe.approval_routes import get_route
from connect_diagnostics_core.api.hrms import payroll_entry_workflow as payroll_workflow
from connect_diagnostics_core.api.hrms import payroll_output_review as output
from connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline import preflight

WORKFLOW_NAME = "Connect Payroll Entry Blueprint"
ROUTE = get_route("payroll_entry")


def _attempt_reassignment_guard(
    site: str, sites_path: str, old_employee: str, new_employee: str, ready: threading.Event
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        doc = Document({"doctype": "Additional Salary", "name": "AS-MUTEX-PROBE", "employee": new_employee})
        db = frappe.db
        exists = db.exists
        get_value = db.get_value

        def probe_exists(doctype: str, *args: object, **kwargs: object) -> bool:
            if doctype == "Additional Salary":
                return True
            return bool(exists(doctype, *args, **kwargs))

        def probe_get_value(doctype: str, *args: object, **kwargs: object) -> object:
            if doctype == "Additional Salary":
                return old_employee
            return get_value(doctype, *args, **kwargs)

        ready.set()
        with (
            patch.object(db, "exists", side_effect=probe_exists),
            patch.object(db, "get_value", side_effect=probe_get_value),
        ):
            payroll_workflow.guard_additional_salary_employee_scope(doc, "before_update")
        db.rollback()
        return "acquired"
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.db.rollback()
        return "serialized"
    finally:
        frappe.destroy()


def _restore_payroll_setting(site: str, sites_path: str, field: str, value: str | None) -> None:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        if value is None:
            frappe.db.delete("Singles", {"doctype": "Payroll Settings", "field": field})
            frappe.clear_document_cache("Payroll Settings", "Payroll Settings")
        else:
            frappe.db.set_single_value("Payroll Settings", field, value)
        frappe.db.commit()
    finally:
        frappe.destroy()


def _payroll_settings_stale_reader_probe(
    site: str,
    sites_path: str,
    field: str,
    snapshot_ready: threading.Event,
    revert_complete: threading.Event,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        stale_value = frappe.db.get_single_value("Payroll Settings", field, cache=False)
        snapshot_ready.set()
        if not revert_complete.wait(timeout=15):
            raise AssertionError("Payroll Settings ABA writer did not finish")
        locked = payroll_workflow._locked_payroll_settings()
        digest = payroll_workflow.critical_digest(
            {"settings": [{"field": row.field, "value": row.value} for row in locked]}
        )
        try:
            payroll_workflow._verify_native_payroll_settings(digest)
        except frappe.ValidationError:
            frappe.db.rollback()
            return f"denied:{stale_value}"
        frappe.db.rollback()
        return f"accepted:{stale_value}"
    finally:
        frappe.destroy()


def _revert_payroll_setting_after_snapshot(
    site: str,
    sites_path: str,
    field: str,
    approved_value: str,
    snapshot_ready: threading.Event,
    revert_complete: threading.Event,
) -> None:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        if not snapshot_ready.wait(timeout=15):
            raise AssertionError("Payroll Settings reader did not establish its snapshot")
        frappe.db.set_single_value("Payroll Settings", field, approved_value)
        frappe.db.commit()  # nosemgrep - publish the independent Payroll Settings ABA test write
        revert_complete.set()
    finally:
        frappe.destroy()


def _require_integrated_route() -> None:
    """Require the actual reviewed route, never silently skip runtime acceptance."""
    preflight()
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        raise AssertionError("The canonical Payroll Entry Workflow is missing")
    workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
    states = {row.state for row in workflow.states}
    required_states = {
        ROUTE.draft_state,
        ROUTE.pending_review_state,
        ROUTE.reviewed_state,
        ROUTE.returned_state,
        ROUTE.approved_state,
        ROUTE.submitted_state,
        output.REVIEWED,
        output.CLOSED,
    }
    if not required_states.issubset(states):
        raise AssertionError("The canonical Payroll Entry Workflow states are incomplete")


class TestPayrollEntryWorkflowIntegration(IntegrationTestCase):
    """Verify the installed route and native HRMS payroll/accounting effects."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        _require_integrated_route()

    def setUp(self) -> None:
        super().setUp()
        self._old_user = frappe.session.user
        self._old_request = getattr(frappe.local, "request", None)
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        self._old_grants = list(grants) if grants is not None else None
        self._old_execution = getattr(frappe.flags, "via_payroll_entry", None)
        self._users: list[str] = []
        self._suffix = uuid4().hex[:12]
        self._holiday_list = f"_Test Payroll Holidays {self._suffix}"
        self._salary_component = f"_Test Payroll Basic {self._suffix}"
        self._savepoint = f"payroll_native_{uuid4().hex}"
        frappe.db.savepoint(self._savepoint)
        self.addCleanup(self._restore)
        frappe.local.request = frappe._dict(method="POST")

    def _restore(self) -> None:
        try:
            frappe.db.rollback(save_point=self._savepoint)
        finally:
            frappe.set_user(self._old_user)
            frappe.local.request = self._old_request
            frappe.flags.via_payroll_entry = self._old_execution
            if self._old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = self._old_grants
            for user in self._users:
                frappe.clear_cache(user=user)
            frappe.clear_document_cache("Company", "_Test Company")
            frappe.clear_document_cache("Payroll Settings", "Payroll Settings")
            frappe.clear_document_cache("Thai Tax Settings", "Thai Tax Settings")
            for doctype in ("Account", "Salary Component", "Salary Structure", "Holiday List", "Employee"):
                frappe.clear_document_cache(doctype)

    def test_workflow_uses_three_distinct_approval_stages(self) -> None:
        workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
        transitions = {(row.state, row.action): (row.next_state, row.allowed) for row in workflow.transitions}
        self.assertEqual(
            transitions[(ROUTE.draft_state, ROUTE.send_action)][:2],
            (ROUTE.pending_review_state, ROUTE.maker_roles[0]),
        )
        self.assertEqual(
            transitions[(ROUTE.pending_review_state, ROUTE.review_action)][:2],
            (ROUTE.reviewed_state, ROUTE.reviewer_roles[0]),
        )
        self.assertEqual(
            transitions[(ROUTE.reviewed_state, ROUTE.approve_action)][:2],
            (ROUTE.approved_state, ROUTE.final_approver_roles[0]),
        )
        self.assertEqual(
            transitions[(ROUTE.approved_state, ROUTE.execute_action)],
            (ROUTE.submitted_state, ROUTE.execution_roles[0]),
        )
        states = {row.state: str(row.doc_status) for row in workflow.states}
        self.assertEqual(states[ROUTE.submitted_state], "1")
        self.assertEqual(states[output.REVIEWED], "1")
        self.assertEqual(states[output.CLOSED], "1")
        self.assertEqual(transitions[(output.SUBMITTED, "Review Calculated Payroll")][0], output.REVIEWED)
        self.assertEqual(transitions[(output.REVIEWED, "Close Payroll")][0], output.CLOSED)

    def test_additional_salary_reassignment_serializes_on_old_and_new_employee(self) -> None:
        employees = frappe.get_all("Employee", fields=["name"], order_by="name asc", limit_page_length=2)
        if len(employees) != 2:
            raise AssertionError("Two Employee rows are required for the reassignment mutex integration test")
        old_employee, new_employee = (str(row.name) for row in employees)
        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        for locked_employee in (old_employee, new_employee):
            with self.subTest(locked_employee=locked_employee):
                savepoint = f"payroll_employee_mutex_{uuid4().hex}"
                frappe.db.savepoint(savepoint)
                payroll_workflow._lock_employee_scope([locked_employee])
                ready = threading.Event()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        _attempt_reassignment_guard,
                        site,
                        sites_path,
                        old_employee,
                        new_employee,
                        ready,
                    )
                    self.assertTrue(ready.wait(timeout=10))
                    self.assertEqual(future.result(timeout=15), "serialized")
                frappe.db.rollback(save_point=savepoint)

    def test_payroll_settings_aba_stale_native_reader_fails_before_payroll_effects(self) -> None:
        field = "process_payroll_accounting_entry_based_on_employee"
        original = frappe.db.get_value("Singles", {"doctype": "Payroll Settings", "field": field}, "value")
        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        snapshot_ready = threading.Event()
        revert_complete = threading.Event()
        _restore_payroll_setting(site, sites_path, field, "0")
        try:
            _restore_payroll_setting(site, sites_path, field, "1")
            with ThreadPoolExecutor(max_workers=2) as executor:
                reader = executor.submit(
                    _payroll_settings_stale_reader_probe,
                    site,
                    sites_path,
                    field,
                    snapshot_ready,
                    revert_complete,
                )
                writer = executor.submit(
                    _revert_payroll_setting_after_snapshot,
                    site,
                    sites_path,
                    field,
                    "0",
                    snapshot_ready,
                    revert_complete,
                )
                writer.result(timeout=30)
                self.assertEqual(reader.result(timeout=30), "denied:1")
        finally:
            _restore_payroll_setting(site, sites_path, field, str(original) if original is not None else None)

    def test_server_hooks_guard_workflow_and_native_submit_boundary(self) -> None:
        doc_events = frappe.get_hooks("doc_events")
        payroll_hooks = doc_events.get("Payroll Entry", {})
        self.assertIn(
            "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_workflow",
            payroll_hooks.get("validate", ()),
        )
        self.assertIn(
            "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_before_submit",
            payroll_hooks.get("before_submit", ()),
        )
        salary_slip_hooks = doc_events.get("Salary Slip", {})
        self.assertIn(
            "connect_diagnostics_core.api.erpnext.salary_slip.validate_creation",
            salary_slip_hooks.get("before_insert", ()),
        )
        self.assertIn(
            "connect_diagnostics_core.api.erpnext.salary_slip.validate_submission",
            salary_slip_hooks.get("before_submit", ()),
        )
        additional_salary_hooks = doc_events.get("Additional Salary", {})
        for event in (
            "before_insert",
            "before_save",
            "before_submit",
            "before_update_after_submit",
            "before_cancel",
        ):
            self.assertIn(
                "connect_diagnostics_core.api.hrms.payroll_entry_workflow.guard_additional_salary_employee_scope",
                additional_salary_hooks.get(event, ()),
            )
        extensions = frappe.get_hooks("extend_doctype_class")
        self.assertIn(
            "connect_diagnostics_core.api.hrms.payroll_entry_workflow.PayrollEntryApprovalMixin",
            extensions.get("Payroll Entry", ()),
        )
        live = frappe.new_doc("Payroll Entry")
        for method in ("create_salary_slips", "submit_salary_slips", "make_bank_entry"):
            live.is_whitelisted(method)

    def test_native_payroll_methods_are_not_replaced_by_whitelisted_overrides(self) -> None:
        overrides = frappe.get_hooks("override_whitelisted_methods")
        native_methods = {
            "hrms.payroll.doctype.payroll_entry.payroll_entry.create_salary_slips",
            "hrms.payroll.doctype.payroll_entry.payroll_entry.submit_salary_slips",
            "hrms.payroll.doctype.payroll_entry.payroll_entry.make_bank_entry",
        }
        self.assertTrue(native_methods.isdisjoint(overrides))

    def test_z_approved_route_preserves_native_payroll_accounting_and_cancellation(self) -> None:
        suffix = uuid4().hex
        maker = f"_test_payroll_maker_{suffix}@example.com"
        reviewer = f"_test_payroll_reviewer_{suffix}@example.com"
        approver = f"_test_payroll_approver_{suffix}@example.com"
        finance_approver = f"_test_payroll_finance_{suffix}@example.com"
        payroll_employee_user = f"_test_payroll_employee_{suffix}@example.com"
        self._users = [maker, reviewer, approver, finance_approver, payroll_employee_user]
        company = frappe.get_doc("Company", "_Test Company")
        self._prepare_payroll_accounts(company)
        employee = self._make_employee(payroll_employee_user, company.name)
        self._assign_employee_holidays(employee, company.name)
        self._make_salary_structure_assignment(employee, company)
        self._make_actor(maker, "HR User", company.name)
        reviewer_employee = self._make_actor(reviewer, "HR Manager", company.name)
        approver_employee = self._make_actor(approver, "Accounts Manager", company.name)
        frappe.get_doc("User", reviewer).add_roles("Accounts User")
        frappe.get_doc("User", approver).add_roles("Accounts User")
        self._make_actor(finance_approver, "C-Level Approver", company.name)
        frappe.get_doc("User", finance_approver).add_roles("Accounts User")

        dates = get_start_end_dates("Monthly", nowdate())
        frappe.set_user(maker)
        self.assertIn("HR User", frappe.get_roles(maker))
        self.assertTrue(frappe.has_permission("Payroll Entry", "create", user=maker))
        payroll_entry = cast(PayrollEntry, frappe.new_doc("Payroll Entry"))
        payroll_entry.update(
            {
                "company": company.name,
                "posting_date": nowdate(),
                "start_date": dates.start_date,
                "end_date": dates.end_date,
                "payroll_frequency": "Monthly",
                "payroll_payable_account": company.default_payroll_payable_account,
                "payment_account": frappe.db.get_value(
                    "Account",
                    {"company": company.name, "account_type": "Cash", "is_group": 0},
                    "name",
                ),
                "currency": company.default_currency,
                "exchange_rate": 1,
                "cost_center": "Main - _TC",
            }
        )
        employee_details = frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "department", "designation"],
            as_dict=True,
        )
        payroll_entry.append("employees", {"employee": employee, **employee_details})
        payroll_entry.set("number_of_employees", 1)
        payroll_entry.insert()
        payroll_entry_name = str(payroll_entry.name)
        self.assertEqual(payroll_entry.get("workflow_state"), ROUTE.draft_state)

        frappe.set_user(reviewer)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc("Payroll Entry", payroll_entry_name).submit()

        self._apply(maker, payroll_entry_name, ROUTE.send_action)
        frappe.set_user("Administrator")
        frappe.get_doc("User", maker).add_roles("HR Manager")
        with self.assertRaises(frappe.ValidationError):
            self._apply(maker, payroll_entry_name, ROUTE.review_action)
        frappe.set_user("Administrator")
        frappe.get_doc("User", maker).remove_roles("HR Manager")
        returned = self._apply(reviewer, payroll_entry_name, ROUTE.return_action)
        self.assertEqual(returned.get("workflow_state"), ROUTE.returned_state)
        self.assertFalse(frappe.db.exists("Salary Slip", {"payroll_entry": payroll_entry_name}))
        self._apply(maker, payroll_entry_name, ROUTE.resubmit_action)
        self._apply(reviewer, payroll_entry_name, ROUTE.review_action)
        rejection_probe = f"payroll_reject_{uuid4().hex}"
        frappe.db.savepoint(rejection_probe)
        try:
            rejected = self._apply(approver, payroll_entry_name, ROUTE.reject_action)
            self.assertEqual(rejected.get("workflow_state"), "Payroll Entry Rejected")
            self.assertFalse(rejected.get("checked_signature"))
            self.assertFalse(rejected.get("authorized_signature"))
            self.assertFalse(frappe.db.exists("Salary Slip", {"payroll_entry": payroll_entry_name}))
            with self.assertRaises(WorkflowTransitionError):
                self._apply(maker, payroll_entry_name, ROUTE.resubmit_action)
        finally:
            frappe.db.rollback(save_point=rejection_probe)
            frappe.clear_document_cache("Payroll Entry", payroll_entry_name)
        self._apply(approver, payroll_entry_name, ROUTE.approve_action)
        submitted = self._apply(reviewer, payroll_entry_name, ROUTE.execute_action)
        self.assertEqual(submitted.docstatus, 1)
        self.assertEqual(submitted.get("workflow_state"), ROUTE.submitted_state)
        self.assertEqual(submitted.get("approval_maker_user"), maker)
        self.assertEqual(submitted.get("approval_reviewer_user"), reviewer)
        self.assertEqual(submitted.get("approval_authorized_user"), approver)
        self.assertEqual(submitted.get("checked_by"), reviewer_employee)
        self.assertEqual(submitted.get("authorized_by"), approver_employee)

        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={"payroll_entry": payroll_entry_name},
            fields=["name", "docstatus", "journal_entry"],
        )
        self.assertEqual(len(salary_slips), 1)
        self.assertEqual(salary_slips[0].docstatus, 0)

        frappe.set_user(reviewer)
        slip = frappe.get_doc("Salary Slip", salary_slips[0].name)
        with self.assertRaises(frappe.ValidationError):
            slip.submit()
        with self.assertRaises(frappe.PermissionError):
            submitted.submit_salary_slips()
        submitted = self._apply(reviewer, payroll_entry_name, "Review Calculated Payroll")
        self.assertEqual(submitted.get("workflow_state"), output.REVIEWED)
        self.assertEqual(submitted.get("output_review_version"), output.VERSION)
        self.assertTrue(submitted.get("output_review_signature"))
        first_review_revision = int(submitted.get("output_review_revision") or 0)
        slip_to_correct = frappe.get_doc("Salary Slip", salary_slips[0].name)
        self.assertTrue(slip_to_correct.earnings)
        slip_to_correct.earnings[0].amount = float(slip_to_correct.earnings[0].amount or 0) + 1
        slip_to_correct.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            submitted.submit_salary_slips()
        reopened_output = self._apply(reviewer, payroll_entry_name, "Reopen Payroll Output")
        self.assertEqual(reopened_output.get("workflow_state"), output.SUBMITTED)
        self.assertFalse(reopened_output.get("output_review_signature"))
        self.assertEqual(int(reopened_output.get("output_review_revision") or 0), first_review_revision + 1)
        submitted = self._apply(reviewer, payroll_entry_name, "Review Calculated Payroll")
        self.assertEqual(int(submitted.get("output_review_revision") or 0), first_review_revision + 2)
        self.assertTrue(submitted.get("output_review_signature"))
        submitted.submit_salary_slips()
        salary_slip = frappe.db.get_value(
            "Salary Slip",
            {"payroll_entry": payroll_entry_name},
            ["name", "docstatus", "journal_entry"],
            as_dict=True,
        )
        self.assertEqual(salary_slip.docstatus, 1)
        accrual_journal = frappe.get_doc("Journal Entry", salary_slip.journal_entry)
        self.assertEqual(accrual_journal.docstatus, 0)
        self.assertEqual(accrual_journal.voucher_type, "Journal Entry")
        self.assertFalse(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Journal Entry", "voucher_no": accrual_journal.name}
            )
        )
        accrual_journal = self._approve_journal(accrual_journal.name, reviewer, approver, finance_approver)
        self.assertEqual(accrual_journal.docstatus, 1)
        self.assertTrue(
            frappe.db.exists(
                "GL Entry",
                {"voucher_type": "Journal Entry", "voucher_no": accrual_journal.name, "is_cancelled": 0},
            )
        )
        net_pay = float(frappe.db.get_value("Salary Slip", salary_slip.name, "net_pay"))
        self.assertGreater(net_pay, 0)
        self.assertAlmostEqual(
            self._payable_effect(accrual_journal.name, company.default_payroll_payable_account), -net_pay
        )

        payment_entries_before = frappe.db.count("Payment Entry")
        frappe.set_user(reviewer)
        bank_entry = submitted.make_bank_entry()
        self.assertIsNotNone(bank_entry)
        self.assertIn(bank_entry.voucher_type, {"Bank Entry", "Cash Entry"})
        self.assertEqual(frappe.db.count("Payment Entry"), payment_entries_before)
        self.assertTrue(
            any(
                row.reference_type == "Payroll Entry" and row.reference_name == payroll_entry_name
                for row in bank_entry.accounts
            )
        )
        self.assertEqual(bank_entry.docstatus, 0)
        bank_entry = self._approve_journal(bank_entry.name, reviewer, approver, finance_approver)
        self.assertEqual(bank_entry.docstatus, 1)
        self.assertTrue(
            frappe.db.exists(
                "GL Entry",
                {"voucher_type": "Journal Entry", "voucher_no": bank_entry.name, "is_cancelled": 0},
            )
        )
        self.assertAlmostEqual(
            self._payable_effect(bank_entry.name, company.default_payroll_payable_account), net_pay
        )
        closed = self._apply(reviewer, payroll_entry_name, "Close Payroll")
        self.assertEqual(closed.get("workflow_state"), output.CLOSED)
        reopened = self._apply(reviewer, payroll_entry_name, "Reopen Payroll Accounting")
        self.assertEqual(reopened.get("workflow_state"), output.REVIEWED)
        frappe.set_user(approver)
        apply_workflow(bank_entry, "Cancel Journal Entry")
        apply_workflow(accrual_journal, "Cancel Journal Entry")
        cancelled = self._apply(reviewer, payroll_entry_name, "Cancel Payroll Entry")
        self.assertEqual(cancelled.docstatus, 2)
        self.assertEqual(cancelled.get("workflow_state"), "Payroll Entry Cancelled")
        self.assertFalse(frappe.db.exists("Salary Slip", salary_slip.name))
        self.assertEqual(frappe.db.get_value("Journal Entry", accrual_journal.name, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Journal Entry", bank_entry.name, "docstatus"), 2)
        for name in (bank_entry.name, accrual_journal.name):
            self.assertFalse(
                frappe.db.exists(
                    "GL Entry", {"voucher_type": "Journal Entry", "voucher_no": name, "is_cancelled": 0}
                )
            )

    @staticmethod
    def _payable_effect(name: str | None, account: str) -> float:
        if not name:
            raise AssertionError("Native payroll Journal Entry must be saved before reading its GL")
        entries = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_type": "Journal Entry",
                "voucher_no": name,
                "account": account,
                "is_cancelled": 0,
            },
            fields=["debit", "credit"],
        )
        return sum(float(row.debit) - float(row.credit) for row in entries)

    @staticmethod
    def _approve_journal(name: str, maker: str, checker: str, approver: str) -> Document:
        doc = frappe.get_doc("Journal Entry", name)
        for user, action in (
            (maker, "Send Journal Entry for Review"),
            (checker, "Review Journal Entry"),
            (approver, "Approve Journal Entry"),
            (checker, "Submit Journal Entry"),
        ):
            frappe.set_user(user)
            doc = apply_workflow(doc, action)
        return doc.reload()

    def _assign_employee_holidays(self, employee: str, company: str) -> None:
        year = cast(date, getdate(nowdate())).year
        assignment = frappe.get_doc(
            {
                "doctype": "Holiday List Assignment",
                "applicable_for": "Employee",
                "assigned_to": employee,
                "employee_company": company,
                "holiday_list": self._holiday_list,
                "from_date": f"{year}-01-01",
            }
        )
        assignment.insert(ignore_permissions=True).submit()

    @staticmethod
    def _make_actor(user: str, role: str, company: str) -> str:
        frappe.set_user("Administrator")
        employee = TestPayrollEntryWorkflowIntegration._make_employee(
            user,
            company,
            approval_signature=f"data:image/png;base64,{role.replace(' ', '')}",
        )
        frappe.get_doc("User", user).add_roles(role)
        return employee

    @staticmethod
    def _make_employee(user: str, company: str, **values: str) -> str:
        if not frappe.db.exists("User", user):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": user,
                    "first_name": user,
                    "send_welcome_email": 0,
                    "roles": [{"role": "Employee"}],
                }
            ).insert(ignore_permissions=True)
        existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
        if existing:
            frappe.db.set_value("Employee", existing, values)
            return existing
        department = frappe.db.get_value("Department", {"company": company}, "name")
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "naming_series": "EMP-",
                "first_name": user,
                "company": company,
                "user_id": user,
                "date_of_birth": "1990-05-08",
                "date_of_joining": "2020-01-01",
                "department": department,
                "gender": "Female",
                "company_email": user,
                "prefered_contact_email": "Company Email",
                "prefered_email": user,
                "status": "Active",
                "employment_type": "Full-time",
                "create_user_permission": 0,
                **values,
            }
        )
        employee.insert(ignore_permissions=True)
        return employee.name

    @staticmethod
    def _apply(user: str, payroll_entry: str, action: str) -> PayrollEntry:
        frappe.set_user(user)
        frappe.local.request = frappe._dict(method="POST")
        return cast(
            PayrollEntry,
            apply_workflow(frappe.get_doc("Payroll Entry", payroll_entry), action),
        )

    def _prepare_payroll_accounts(self, company: Document) -> None:
        frappe.set_user("Administrator")
        year = cast(date, getdate(nowdate())).year
        frappe.get_doc(
            {
                "doctype": "Holiday List",
                "holiday_list_name": self._holiday_list,
                "from_date": f"{year}-01-01",
                "to_date": f"{year}-12-31",
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_single_value("Payroll Settings", "email_salary_slip_to_employee", 0)
        parent = frappe.get_doc("Account", "Current Liabilities - _TC")
        self.assertEqual(parent.company, company.name)
        self.assertEqual(parent.is_group, 1)
        self.assertEqual(parent.root_type, "Liability")
        payable_account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"_Test Payroll Payable {self._suffix}",
                "company": company.name,
                "parent_account": parent.name,
                "account_type": "Payable",
                "account_currency": company.get("default_currency"),
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value("Company", company.name, "default_payroll_payable_account", payable_account.name)
        thai_tax_settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == company.name for row in thai_tax_settings.company_accounts):
            thai_tax_settings.append("company_accounts", {"company": company.name})
            thai_tax_settings.save(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": self._salary_component,
                "type": "Earning",
                "is_tax_applicable": 0,
                "accounts": [{"company": company.name, "account": "Salary - _TC"}],
            }
        ).insert(ignore_permissions=True)
        company.reload()

    def _make_salary_structure_assignment(self, employee: str, company: Document) -> None:
        structure_name = f"_Test Approved Payroll Structure {self._suffix}"
        structure = frappe.get_doc(
            {
                "doctype": "Salary Structure",
                "name": structure_name,
                "company": company.name,
                "currency": company.get("default_currency"),
                "payroll_frequency": "Monthly",
                "is_active": "Yes",
                "earnings": [
                    {
                        "salary_component": self._salary_component,
                        "amount_based_on_formula": 1,
                        "formula": "base",
                    }
                ],
            }
        )
        structure.insert(ignore_permissions=True).submit()
        assignment = frappe.get_doc(
            {
                "doctype": "Salary Structure Assignment",
                "employee": employee,
                "salary_structure": structure_name,
                "from_date": get_first_day(nowdate()),
                "base": 50000,
                "company": company.name,
                "currency": company.get("default_currency"),
                "payroll_payable_account": company.get("default_payroll_payable_account"),
            }
        )
        assignment.insert(ignore_permissions=True)
        assignment.submit()
