# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field / property setter definitions for Employee."""

from __future__ import annotations

import json

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

SIGNATURE_FIELD = "signature_cvru"
SIGNATURE_ANCHOR = "shift_request_approver"

CUSTOM_FIELDS = {
    "Employee": [
        {
            "fieldname": "approvers_section",
            "label": "Approvers",
            "fieldtype": "Section Break",
            "insert_after": "default_shift",
            "is_system_generated": 1,
        },
        {
            "fieldname": "column_break_45",
            "fieldtype": "Column Break",
            "insert_after": "leave_approver",
            "is_system_generated": 1,
        },
        {
            "fieldname": "first_name_en",
            "label": "First Name EN",
            "fieldtype": "Data",
            "insert_after": "column_break_9",
        },
        {
            "fieldname": "last_name_en",
            "label": "Last Name EN",
            "fieldtype": "Data",
            "insert_after": "first_name_en",
        },
        {
            "fieldname": "default_shift",
            "label": "Default Shift",
            "fieldtype": "Link",
            "insert_after": "holiday_list",
            "is_system_generated": 1,
            "options": "Shift Type",
        },
        {
            "fieldname": "employment_type",
            "label": "Employment Type",
            "fieldtype": "Link",
            "insert_after": "department",
            "ignore_user_permissions": 1,
            "is_system_generated": 1,
            "options": "Employment Type",
        },
        {
            "fieldname": "expense_approver",
            "label": "Expense Approver",
            "fieldtype": "Link",
            "insert_after": "approvers_section",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "grade",
            "label": "Grade",
            "fieldtype": "Link",
            "insert_after": "branch",
            "is_system_generated": 1,
            "options": "Employee Grade",
        },
        {
            "fieldname": "health_insurance_no",
            "label": "Health Insurance No",
            "fieldtype": "Data",
            "insert_after": "health_insurance_provider",
            "depends_on": "eval:doc.health_insurance_provider",
            "is_system_generated": 1,
        },
        {
            "fieldname": "health_insurance_provider",
            "label": "Health Insurance Provider",
            "fieldtype": "Link",
            "insert_after": "health_insurance_section",
            "is_system_generated": 1,
            "options": "Employee Health Insurance",
        },
        {
            "fieldname": "health_insurance_section",
            "label": "Health Insurance",
            "fieldtype": "Section Break",
            "insert_after": "health_details",
            "collapsible": 0,
            "is_system_generated": 1,
        },
        {
            "fieldname": "job_applicant",
            "label": "Job Applicant",
            "fieldtype": "Link",
            "insert_after": "employment_details",
            "is_system_generated": 1,
            "options": "Job Applicant",
        },
        {
            "fieldname": "leave_approver",
            "label": "Leave Approver",
            "fieldtype": "Link",
            "insert_after": "expense_approver",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "payroll_cost_center",
            "label": "Payroll Cost Center",
            "fieldtype": "Link",
            "insert_after": "salary_cb",
            "fetch_from": "department.payroll_cost_center",
            "fetch_if_empty": 1,
            "is_system_generated": 1,
            "options": "Cost Center",
        },
        {
            "fieldname": "salary_cb",
            "fieldtype": "Column Break",
            "insert_after": "salary_mode",
            "is_system_generated": 1,
        },
        {
            "fieldname": "shift_request_approver",
            "label": "Shift Request Approver",
            "fieldtype": "Link",
            "insert_after": "column_break_45",
            "is_system_generated": 1,
            "options": "User",
        },
        {
            "fieldname": "thai_payroll_section",
            "label": "Thai Payroll",
            "fieldtype": "Section Break",
            "insert_after": "payroll_cost_center",
            "collapsible": 0,
            "is_system_generated": 1,
        },
        {
            "fieldname": "social_security_eligible",
            "label": "Social Security Eligible",
            "fieldtype": "Check",
            "insert_after": "thai_payroll_section",
            "is_system_generated": 1,
        },
        {
            "fieldname": "provident_fund_rate",
            "label": "Provident Fund Rate (%)",
            "fieldtype": "Percent",
            "insert_after": "social_security_eligible",
            "description": "Employee provident fund deduction rate (%). Set per employee; no default is applied.",
            "is_system_generated": 1,
        },
        {
            "fieldname": "national_id_section",
            "label": "National ID & Social Security",
            "fieldtype": "Section Break",
            "insert_after": "basic_details_tab",
            "collapsible": 0,
            "is_system_generated": 1,
        },
        {
            "fieldname": "national_id",
            "label": "National ID",
            "fieldtype": "Data",
            "insert_after": "national_id_section",
            "description": "13-digit Thai National ID used as the taxpayer identification number for P.N.D. 1 Kor.",
            "is_system_generated": 1,
        },
        {
            "fieldname": "national_id_display",
            "label": "National ID (Formatted)",
            "fieldtype": "Data",
            "insert_after": "national_id",
            "read_only": 1,
            "description": "Formatted National ID for display. Calculated automatically.",
            "is_system_generated": 1,
        },
        {
            "fieldname": "national_id_column_break",
            "fieldtype": "Column Break",
            "insert_after": "national_id_display",
            "is_system_generated": 1,
        },
        {
            "fieldname": "social_security_id",
            "label": "Social Security ID",
            "fieldtype": "Data",
            "insert_after": "national_id_column_break",
            "description": "Thai Social Security identification number for this employee.",
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_signature_section",
            "label": "Approval Signature",
            "fieldtype": "Section Break",
            "insert_after": "personal_details",
            "collapsible": 0,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_signature",
            "label": "Approval Signature",
            "fieldtype": "Signature",
            "insert_after": "approval_signature_section",
            "description": "Signature used for document approvals, authorization, and printed approval snapshots.",
            "is_system_generated": 1,
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Employee": [
        ("employee_number", "hidden", "1", "Check"),
        ("employee_number", "reqd", "0", "Check"),
        ("employment_type", "reqd", "1", "Check"),
        ("naming_series", "hidden", "0", "Check"),
        ("naming_series", "default", "YY-BE.MM.###", "Text"),
        ("naming_series", "options", "YY-BE.MM.###\nC.YY-BE.MM.###", "Text"),
        ("naming_series", "reqd", "1", "Check"),
        (SIGNATURE_FIELD, "label", "Employee Signature", "Data"),
    ],
}


def ensure_configuration() -> None:
    """Place the Employee signature after the app-managed approver fields."""
    doctype = "Employee"
    meta = frappe.get_meta(doctype)
    live_order = [field.fieldname for field in meta.fields if field.fieldname]

    if SIGNATURE_FIELD not in live_order or SIGNATURE_ANCHOR not in live_order:
        return

    desired_order = _relocated_after_anchor(live_order, (SIGNATURE_FIELD,), SIGNATURE_ANCHOR)
    if desired_order == live_order:
        return

    _set_field_order(doctype, desired_order)


def _relocated_after_anchor(current_order: list[str], fields: tuple[str, ...], anchor: str) -> list[str]:
    """Move fields directly after an existing anchor while preserving other fields."""
    moved = set(fields)
    remaining = [fieldname for fieldname in current_order if fieldname not in moved]

    anchor_index = remaining.index(anchor)
    remaining[anchor_index + 1 : anchor_index + 1] = list(fields)
    return remaining


def _set_field_order(doctype: str, order: list[str]) -> None:
    """Persist a DocType-level field-order Property Setter idempotently."""
    value = json.dumps(order)
    name = frappe.db.get_value("Property Setter", {"doc_type": doctype, "property": "field_order"}, "name")
    if name:
        property_setter = frappe.get_doc("Property Setter", name)
        property_setter.value = value
        property_setter.save(ignore_permissions=True)
        return

    make_property_setter(
        doctype,
        None,
        "field_order",
        value,
        "Small Text",
        for_doctype=True,
        validate_fields_for_doctype=False,
    )
