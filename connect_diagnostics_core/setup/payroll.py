# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom payroll policy fields and explicitly applied Salary Component formulas."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.utils import cint
from hrms.payroll.doctype.salary_component.salary_component import SalaryComponent

COMPANY_DOCTYPE = "Company"
ASSIGNMENT_DOCTYPE = "Salary Structure Assignment"

SOCIAL_SECURITY_WAGE_CEILING_FIELD = "social_security_wage_ceiling"
SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD = "social_security_employee_rate"
SOCIAL_SECURITY_EMPLOYER_RATE_FIELD = "social_security_employer_rate"
SOCIAL_SECURITY_MEMBER_FIELD = "social_security_member"
PROVIDENT_FUND_RATE_FIELD = "provident_fund_rate"

CUSTOM_FIELDS = {
    COMPANY_DOCTYPE: [
        {
            "fieldname": "payroll_policy_section",
            "label": "Payroll Policy",
            "fieldtype": "Section Break",
            "insert_after": "default_payroll_payable_account",
            "collapsible": 1,
        },
        {
            "fieldname": SOCIAL_SECURITY_WAGE_CEILING_FIELD,
            "label": "Social Security Wage Ceiling",
            "fieldtype": "Currency",
            "options": "default_currency",
            "insert_after": "payroll_policy_section",
            "non_negative": 1,
        },
        {
            "fieldname": SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD,
            "label": "Social Security Employee Rate",
            "fieldtype": "Percent",
            "insert_after": SOCIAL_SECURITY_WAGE_CEILING_FIELD,
            "non_negative": 1,
        },
        {
            "fieldname": "payroll_policy_column_break",
            "fieldtype": "Column Break",
            "insert_after": SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD,
        },
        {
            "fieldname": SOCIAL_SECURITY_EMPLOYER_RATE_FIELD,
            "label": "Social Security Employer Rate",
            "fieldtype": "Percent",
            "insert_after": "payroll_policy_column_break",
            "non_negative": 1,
        },
    ],
    ASSIGNMENT_DOCTYPE: [
        {
            "fieldname": "contribution_policy_section",
            "label": "Contribution Policy Snapshot",
            "fieldtype": "Section Break",
            "insert_after": "variable",
            "collapsible": 1,
        },
        {
            "fieldname": SOCIAL_SECURITY_MEMBER_FIELD,
            "label": "Social Security Member",
            "fieldtype": "Check",
            "insert_after": "contribution_policy_section",
            "default": "1",
        },
        {
            "fieldname": SOCIAL_SECURITY_WAGE_CEILING_FIELD,
            "label": "Social Security Wage Ceiling",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "insert_after": SOCIAL_SECURITY_MEMBER_FIELD,
            "fetch_from": f"company.{SOCIAL_SECURITY_WAGE_CEILING_FIELD}",
            "fetch_if_empty": 1,
            "mandatory_depends_on": f"eval:doc.{SOCIAL_SECURITY_MEMBER_FIELD}",
            "no_copy": 1,
            "non_negative": 1,
        },
        {
            "fieldname": SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD,
            "label": "Social Security Employee Rate",
            "fieldtype": "Percent",
            "insert_after": SOCIAL_SECURITY_WAGE_CEILING_FIELD,
            "fetch_from": f"company.{SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD}",
            "fetch_if_empty": 1,
            "mandatory_depends_on": f"eval:doc.{SOCIAL_SECURITY_MEMBER_FIELD}",
            "no_copy": 1,
            "non_negative": 1,
        },
        {
            "fieldname": "contribution_policy_column_break",
            "fieldtype": "Column Break",
            "insert_after": SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD,
        },
        {
            "fieldname": SOCIAL_SECURITY_EMPLOYER_RATE_FIELD,
            "label": "Social Security Employer Rate",
            "fieldtype": "Percent",
            "insert_after": "contribution_policy_column_break",
            "fetch_from": f"company.{SOCIAL_SECURITY_EMPLOYER_RATE_FIELD}",
            "fetch_if_empty": 1,
            "mandatory_depends_on": f"eval:doc.{SOCIAL_SECURITY_MEMBER_FIELD}",
            "no_copy": 1,
            "non_negative": 1,
        },
        {
            "fieldname": PROVIDENT_FUND_RATE_FIELD,
            "label": "Provident Fund Rate",
            "fieldtype": "Percent",
            "insert_after": SOCIAL_SECURITY_EMPLOYER_RATE_FIELD,
            "default": "0",
            "non_negative": 1,
        },
    ],
}

# These policies are version-controlled but are applied only through an explicit
# environment import. after_migrate creates fields and never rewrites payroll masters.
SALARY_COMPONENT_POLICIES: dict[str, dict[str, Any]] = {
    "BS": {
        "name": "เงินเดือนค่าจ้าง",
        "type": "Earning",
        "formula": "base",
        "condition": "",
        "statistical_component": 0,
    },
    "PVD_BASE": {
        "name": "ฐานคำนวณกองทุนสำรองเลี้ยงชีพ",
        "type": "Deduction",
        "formula": "BS + RETRO",
        "condition": f"{PROVIDENT_FUND_RATE_FIELD} > 0",
        "statistical_component": 1,
    },
    "SSO_BASE": {
        "name": "ฐานคำนวณประกันสังคม",
        "type": "Deduction",
        "formula": (f"min(max(BS + RETRO, 0), {SOCIAL_SECURITY_WAGE_CEILING_FIELD})"),
        "condition": SOCIAL_SECURITY_MEMBER_FIELD,
        "statistical_component": 1,
    },
    "PVD_EE": {
        "name": "หักกองทุนสำรองเลี้ยงชีพ - พนักงาน",
        "type": "Deduction",
        "formula": f"PVD_BASE * {PROVIDENT_FUND_RATE_FIELD} / 100",
        "condition": f"{PROVIDENT_FUND_RATE_FIELD} > 0",
        "statistical_component": 0,
    },
    "SSO_EE": {
        "name": "หักประกันสังคม - พนักงาน",
        "type": "Deduction",
        "formula": f"SSO_BASE * {SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD} / 100",
        "condition": f"{SOCIAL_SECURITY_MEMBER_FIELD} and {SOCIAL_SECURITY_EMPLOYEE_RATE_FIELD} > 0",
        "statistical_component": 0,
    },
    "PVD_ER": {
        "name": "เงินสมทบกองทุนสำรองเลี้ยงชีพ - บริษัท",
        "type": "Employer Contribution",
        "formula": f"PVD_BASE * {PROVIDENT_FUND_RATE_FIELD} / 100",
        "condition": f"{PROVIDENT_FUND_RATE_FIELD} > 0",
        "statistical_component": 0,
    },
    "SSO_ER": {
        "name": "เงินสมทบประกันสังคม - บริษัท",
        "type": "Employer Contribution",
        "formula": f"SSO_BASE * {SOCIAL_SECURITY_EMPLOYER_RATE_FIELD} / 100",
        "condition": f"{SOCIAL_SECURITY_MEMBER_FIELD} and {SOCIAL_SECURITY_EMPLOYER_RATE_FIELD} > 0",
        "statistical_component": 0,
    },
}

_MANAGED_POLICY_FIELDS = (
    "amount_based_on_formula",
    "formula",
    "condition",
    "statistical_component",
    "round_to_the_nearest_integer",
)


def configure_salary_components() -> list[str]:
    """Apply approved formulas without creating or silently overriding Salary Structures."""
    updated: list[str] = []
    for abbreviation, policy in SALARY_COMPONENT_POLICIES.items():
        component_name = cast(str, policy["name"])
        if not frappe.db.exists("Salary Component", component_name):
            frappe.throw(
                _("Required Salary Component {0} ({1}) does not exist.").format(
                    frappe.bold(component_name), frappe.bold(abbreviation)
                )
            )

        component = cast(
            SalaryComponent,
            frappe.get_doc("Salary Component", component_name, for_update=True),
        )
        if component.get("salary_component_abbr") != abbreviation or component.get("type") != policy["type"]:
            frappe.throw(
                _("Salary Component {0} does not match its approved abbreviation and type.").format(
                    frappe.bold(component_name)
                )
            )

        expected = {
            "amount_based_on_formula": 1,
            "formula": policy["formula"],
            "condition": policy["condition"],
            "statistical_component": policy["statistical_component"],
            "round_to_the_nearest_integer": 0,
        }
        check_fields = {
            "amount_based_on_formula",
            "statistical_component",
            "round_to_the_nearest_integer",
        }
        changed = any(
            (cint(component.get(fieldname)) if fieldname in check_fields else component.get(fieldname) or "")
            != value
            for fieldname, value in expected.items()
        )
        if not changed:
            continue

        structures = component.get_structures_to_be_updated()
        if structures:
            frappe.throw(
                _(
                    "Salary Component {0} is already used by a Salary Structure. "
                    "Review and update that structure explicitly before changing its policy."
                ).format(frappe.bold(component_name))
            )

        for fieldname in _MANAGED_POLICY_FIELDS:
            component.set(fieldname, expected[fieldname])
        component.save(ignore_permissions=True)
        updated.append(component_name)

    return updated
