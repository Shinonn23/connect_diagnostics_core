# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import cast
from unittest import SkipTest

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import get_first_day, getdate, nowdate
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry, get_start_end_dates

from connect_diagnostics_core.api.frappe.approval_routes import get_route

WORKFLOW_NAME = "Connect Payroll Entry Blueprint"
ROUTE = get_route("payroll_entry")


def _require_integrated_route() -> None:
    """Skip until the serialized Payroll route migration is installed."""
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        raise SkipTest("The serialized Payroll Entry Workflow migration has not run on this site")
    workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
    states = {row.state for row in workflow.states}
    required_states = {
        ROUTE.draft_state,
        ROUTE.pending_review_state,
        ROUTE.reviewed_state,
        ROUTE.returned_state,
        ROUTE.approved_state,
        ROUTE.submitted_state,
    }
    if not required_states.issubset(states):
        raise SkipTest("The serialized Payroll Entry Workflow integration is not installed")


class TestPayrollEntryWorkflowIntegration(IntegrationTestCase):
    """Verify the installed route and native HRMS payroll/accounting effects."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        _require_integrated_route()

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
        extensions = frappe.get_hooks("extend_doctype_class")
        self.assertIn(
            "connect_diagnostics_core.api.hrms.payroll_entry_workflow.PayrollEntryApprovalMixin",
            extensions.get("Payroll Entry", ()),
        )

    def test_native_payroll_methods_are_not_replaced_by_whitelisted_overrides(self) -> None:
        overrides = frappe.get_hooks("override_whitelisted_methods")
        native_methods = {
            "hrms.payroll.doctype.payroll_entry.payroll_entry.create_salary_slips",
            "hrms.payroll.doctype.payroll_entry.payroll_entry.submit_salary_slips",
            "hrms.payroll.doctype.payroll_entry.payroll_entry.make_bank_entry",
        }
        self.assertTrue(native_methods.isdisjoint(overrides))

    def test_z_approved_route_preserves_native_payroll_accounting_and_cancellation(self) -> None:
        maker = "_test_payroll_maker@example.com"
        reviewer = "_test_payroll_reviewer@example.com"
        approver = "_test_payroll_approver@example.com"
        payroll_employee_user = "_test_payroll_employee@example.com"
        company = frappe.get_doc("Company", "_Test Company")
        self._prepare_payroll_accounts(company)
        employee = self._make_employee(payroll_employee_user, company.name)
        self._make_salary_structure_assignment(employee, company)
        self._make_actor(maker, "HR User", company.name)
        reviewer_employee = self._make_actor(reviewer, "HR Manager", company.name)
        approver_employee = self._make_actor(approver, "Accounts Manager", company.name)

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
        self._apply(reviewer, payroll_entry_name, ROUTE.review_action)
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
        submitted.submit_salary_slips()
        salary_slip = frappe.db.get_value(
            "Salary Slip",
            {"payroll_entry": payroll_entry_name},
            ["name", "docstatus", "journal_entry"],
            as_dict=True,
        )
        self.assertEqual(salary_slip.docstatus, 1)
        accrual_journal = frappe.get_doc("Journal Entry", salary_slip.journal_entry)
        self.assertEqual(accrual_journal.docstatus, 1)
        self.assertEqual(accrual_journal.voucher_type, "Journal Entry")

        payment_entries_before = frappe.db.count("Payment Entry")
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

        frappe.set_user("Administrator")
        frappe.delete_doc("Journal Entry", bank_entry.name, force=True, ignore_permissions=True)
        cancelled = self._apply(reviewer, payroll_entry_name, "Cancel Payroll Entry")
        self.assertEqual(cancelled.docstatus, 2)
        self.assertEqual(cancelled.get("workflow_state"), "Payroll Entry Cancelled")
        self.assertFalse(frappe.db.exists("Salary Slip", salary_slip.name))
        self.assertEqual(frappe.db.get_value("Journal Entry", accrual_journal.name, "docstatus"), 2)

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
                "employment_type": "Intern",
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

    @staticmethod
    def _prepare_payroll_accounts(company) -> None:
        frappe.set_user("Administrator")
        year = cast(date, getdate(nowdate())).year
        holiday_list = f"_Test Connect Payroll Holidays {year}"
        if not frappe.db.exists("Holiday List", holiday_list):
            frappe.get_doc(
                {
                    "doctype": "Holiday List",
                    "holiday_list_name": holiday_list,
                    "from_date": f"{year}-01-01",
                    "to_date": f"{year}-12-31",
                }
            ).insert(ignore_permissions=True)
        frappe.db.set_value("Company", company.name, "default_holiday_list", holiday_list)
        holiday_assignment = frappe.get_doc(
            {
                "doctype": "Holiday List Assignment",
                "applicable_for": "Company",
                "assigned_to": company.name,
                "holiday_list": holiday_list,
                "employee_company": company.name,
                "from_date": f"{year}-01-01",
            }
        )
        holiday_assignment.insert(ignore_permissions=True)
        holiday_assignment.submit()
        frappe.db.set_single_value("Payroll Settings", "email_salary_slip_to_employee", 0)
        payable_account = "_Test Payroll Payable - _TC"
        if not frappe.db.exists("Account", payable_account):
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": "_Test Payroll Payable",
                    "company": company.name,
                    "parent_account": "Current Liabilities - _TC",
                    "account_type": "Payable",
                }
            ).insert(ignore_permissions=True)
        frappe.db.set_value("Account", payable_account, "account_type", "Payable")
        frappe.db.set_value("Company", company.name, "default_payroll_payable_account", payable_account)
        thai_tax_settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == company.name for row in thai_tax_settings.company_accounts):
            thai_tax_settings.append("company_accounts", {"company": company.name})
            thai_tax_settings.save(ignore_permissions=True)
        if not frappe.db.exists("Salary Component", "_Test Connect Payroll Basic"):
            frappe.get_doc(
                {
                    "doctype": "Salary Component",
                    "salary_component": "_Test Connect Payroll Basic",
                    "type": "Earning",
                    "is_tax_applicable": 0,
                    "accounts": [{"company": company.name, "account": "Salary - _TC"}],
                }
            ).insert(ignore_permissions=True)
        company.reload()

    @staticmethod
    def _make_salary_structure_assignment(employee: str, company) -> None:
        structure_name = "_Test Connect Approved Payroll Structure"
        if not frappe.db.exists("Salary Structure", structure_name):
            structure = frappe.get_doc(
                {
                    "doctype": "Salary Structure",
                    "name": structure_name,
                    "company": company.name,
                    "currency": company.default_currency,
                    "payroll_frequency": "Monthly",
                    "is_active": "Yes",
                    "earnings": [
                        {
                            "salary_component": "_Test Connect Payroll Basic",
                            "amount_based_on_formula": 1,
                            "formula": "base",
                        }
                    ],
                }
            )
            structure.insert(ignore_permissions=True)
            structure.submit()
        assignment = frappe.get_doc(
            {
                "doctype": "Salary Structure Assignment",
                "employee": employee,
                "salary_structure": structure_name,
                "from_date": get_first_day(nowdate()),
                "base": 50000,
                "company": company.name,
                "currency": company.default_currency,
                "payroll_payable_account": company.default_payroll_payable_account,
            }
        )
        assignment.insert(ignore_permissions=True)
        assignment.submit()
