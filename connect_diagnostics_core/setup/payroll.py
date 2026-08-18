# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Idempotent Thai payroll foundation: Salary Components, Income Tax Slab,
Payroll Period, and a base Salary Structure template.

Per-employee data (base pay, provident-fund rate, tax-exemption declarations)
lives on the Employee and the Salary Structure Assignment — this module only
seeds the shared policy/config, never per-person amounts. Every record is
created only when absent so a later manual edit is preserved.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import frappe
import frappe.defaults
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

# --- SSO (Social Security) ---------------------------------------------------
# Company policy caps the SSO contribution base at 17,500 (5% -> 875/month),
# above the current statutory 15,000/750 ceiling. See CLAUDE.md payroll notes.
SSO_CONTRIBUTION_CEILING = 17500
SSO_RATE = 0.05

# --- Thai Personal Income Tax ------------------------------------------------
# Personal allowance (60,000) + capped expense deduction (50%, max 100,000)
# folded into the slab's standard exemption. Per-person deductions (spouse,
# children, insurance, SSO/PF paid, ...) flow through Employee Tax Exemption
# Declarations, enabled by allow_tax_exemption.
STANDARD_TAX_EXEMPTION_AMOUNT = 160000

# Progressive annual brackets (Revenue Code sec. 48). to_amount 0 = open-ended.
INCOME_TAX_SLABS = (
    (0, 150000, 0),
    (150000, 300000, 5),
    (300000, 500000, 10),
    (500000, 750000, 15),
    (750000, 1000000, 20),
    (1000000, 2000000, 25),
    (2000000, 5000000, 30),
    (5000000, 0, 35),
)

INCOME_TAX_SLAB_NAME = "Thailand Personal Income Tax"
SALARY_STRUCTURE_NAME = "Connect Diagnostics Monthly"

SALARY_SLIP_DOCTYPE = "Salary Slip"
SALARY_SLIP_REVIEW_STATE_FIELD = "salary_slip_review_state"

CUSTOM_FIELDS = {
    SALARY_SLIP_DOCTYPE: [
        {
            "fieldname": SALARY_SLIP_REVIEW_STATE_FIELD,
            "label": "Salary Slip Review State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "read_only": 1,
            "no_copy": 1,
            "allow_on_submit": 1,
            "insert_after": "status",
        }
    ]
}

# --- Salary Components -------------------------------------------------------
# formula: an amount_based_on_formula expression evaluated in the HRMS salary
#   component context (base, employee fields, min/max are available).
# variable_based_on_taxable_salary: HRMS computes the amount from the tax slab.
BASE_FORMULA = "base"
SSO_FORMULA = f"min(base, {SSO_CONTRIBUTION_CEILING}) * {SSO_RATE}"
PROVIDENT_FUND_FORMULA = "base * (provident_fund_rate or 0) / 100"

# Each: (name, type, {flags})
SALARY_COMPONENTS: tuple[tuple[str, str, dict], ...] = (
    ("Basic", "Earning", {"is_tax_applicable": 1, "formula": BASE_FORMULA}),
    ("Retro", "Earning", {"is_tax_applicable": 1}),
    ("Travelling Allowance", "Earning", {"is_tax_applicable": 1}),
    ("MBO", "Earning", {"is_tax_applicable": 1}),
    ("Bonus", "Earning", {"is_tax_applicable": 1, "deduct_full_tax_on_selected_payroll_date": 1}),
    ("Overtime", "Earning", {"is_tax_applicable": 1}),
    ("Allowance", "Earning", {"is_tax_applicable": 1}),
    ("Incentive", "Earning", {"is_tax_applicable": 1}),
    ("Social Security", "Deduction", {"formula": SSO_FORMULA}),
    ("Provident Fund", "Deduction", {"formula": PROVIDENT_FUND_FORMULA}),
    ("Withholding Tax", "Deduction", {"variable_based_on_taxable_salary": 1}),
    # Employee Welfare Fund becomes mandatory 1 Oct 2026 (0.25%); seeded disabled.
    ("Employee Welfare Fund", "Deduction", {"disabled": 1, "formula": "base * 0.25 / 100"}),
    ("Student Loan Repayment", "Deduction", {}),
    ("Advance", "Deduction", {}),
)

# Components wired into the base structure (auto-computed each cycle). Other
# components stay available to add to individual slips or assignments.
STRUCTURE_EARNINGS = ("Basic",)
STRUCTURE_DEDUCTIONS = ("Social Security", "Provident Fund", "Withholding Tax")


def ensure_configuration() -> None:
    ensure_salary_components()
    company = _default_company()
    if not company:
        frappe.logger(__name__).warning(
            "Skipped company-scoped payroll setup (Income Tax Slab, Payroll Period, "
            "Salary Structure): no default Company resolved."
        )
        return
    ensure_income_tax_slab(company)
    ensure_payroll_period(company)
    ensure_salary_structure(company)


def _default_company() -> str | None:
    company = frappe.defaults.get_global_default("company")
    if company:
        return cast(str, company)
    companies = frappe.get_all("Company", pluck="name", limit=2)
    return companies[0] if len(companies) == 1 else None


def ensure_salary_components() -> None:
    for name, component_type, flags in SALARY_COMPONENTS:
        values = {"is_tax_applicable": 0, "amount_based_on_formula": 0, **flags}
        if flags.get("formula"):
            values["amount_based_on_formula"] = 1

        if frappe.db.exists("Salary Component", name):
            continue

        doc = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Salary Component",
                    "salary_component": name,
                    "type": component_type,
                    **values,
                }
            ),
        )
        doc.insert(ignore_permissions=True)


def ensure_income_tax_slab(company: str) -> None:
    if frappe.db.exists("Income Tax Slab", INCOME_TAX_SLAB_NAME):
        return

    currency = cast(str, frappe.get_cached_value("Company", company, "default_currency"))
    year_start = cast(date, getdate(today())).replace(month=1, day=1)
    doc = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Income Tax Slab",
                "name": INCOME_TAX_SLAB_NAME,
                "effective_from": year_start,
                "company": company,
                "currency": currency,
                "allow_tax_exemption": 1,
                "standard_tax_exemption_amount": STANDARD_TAX_EXEMPTION_AMOUNT,
                "slabs": [
                    {
                        "from_amount": from_amount,
                        "to_amount": to_amount,
                        "percent_deduction": percent,
                    }
                    for from_amount, to_amount, percent in INCOME_TAX_SLABS
                ],
            }
        ),
    )
    doc.insert(ignore_permissions=True)
    doc.submit()


def ensure_payroll_period(company: str) -> None:
    year = cast(date, getdate(today())).year
    start_date = getdate(f"{year}-01-01")
    end_date = getdate(f"{year}-12-31")

    # HRMS forbids overlapping Payroll Periods for the same company, so a period
    # is treated as present when any existing one (whatever its name) already
    # covers this range — e.g. a manually created one. Keying on our own name
    # alone would try to insert a second overlapping period and abort migrate.
    if frappe.get_all(
        "Payroll Period",
        filters={
            "company": company,
            "start_date": ["<=", end_date],
            "end_date": [">=", start_date],
        },
        limit=1,
    ):
        return

    doc = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Payroll Period",
                "name": f"{company} {year}",
                "company": company,
                "start_date": start_date,
                "end_date": end_date,
            }
        ),
    )
    doc.insert(ignore_permissions=True)


def ensure_salary_structure(company: str) -> None:
    if frappe.db.exists("Salary Structure", SALARY_STRUCTURE_NAME):
        return

    currency = cast(str, frappe.get_cached_value("Company", company, "default_currency"))
    doc = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Salary Structure",
                "name": SALARY_STRUCTURE_NAME,
                "company": company,
                "currency": currency,
                "is_active": "Yes",
                "payroll_frequency": "Monthly",
                "earnings": [_structure_row(name) for name in STRUCTURE_EARNINGS],
                "deductions": [_structure_row(name) for name in STRUCTURE_DEDUCTIONS],
            }
        ),
    )
    doc.insert(ignore_permissions=True)
    doc.submit()


def _structure_row(component: str) -> dict:
    flags = next(f for name, _type, f in SALARY_COMPONENTS if name == component)
    row: dict[str, object] = {"salary_component": component}
    if flags.get("formula"):
        row["amount_based_on_formula"] = 1
        row["formula"] = flags["formula"]
    if flags.get("variable_based_on_taxable_salary"):
        row["variable_based_on_taxable_salary"] = 1
    return row


# Re-exported for tests / callers that want the resolved monthly SSO ceiling.
def sso_ceiling_amount() -> float:
    return flt(SSO_CONTRIBUTION_CEILING * SSO_RATE)
