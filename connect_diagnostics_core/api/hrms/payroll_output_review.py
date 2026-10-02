# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Current, signed review of the native HRMS calculated payroll batch."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from re import search
from typing import Any, cast

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.background_jobs import is_job_enqueued
from frappe.utils.password import get_encryption_key
from hrms.payroll.doctype.payroll_entry.payroll_entry import (
    create_salary_slips_for_employees,
    submit_salary_slips_for_employees,
)

from connect_diagnostics_core.api.frappe.approval_controls import critical_digest

VERSION = "wf14-output-v1"
SUBMITTED = "Payroll Entry Submitted"
REVIEWED = "Payroll Output Reviewed"
CLOSED = "Payroll Entry Closed"
CANCELLED = "Payroll Entry Cancelled"
OUTPUT_FIELDS = (
    "output_reviewed_by",
    "output_reviewed_at",
    "output_review_signature",
    "output_review_digest",
    "output_review_version",
    "output_review_revision",
)
_native_operation: ContextVar[tuple[str, str] | None] = ContextVar("payroll_native_operation", default=None)

HEADER_FIELDS = (
    "name",
    "payroll_entry",
    "employee",
    "company",
    "posting_date",
    "start_date",
    "end_date",
    "salary_structure",
    "salary_slip_based_on_timesheet",
    "payroll_frequency",
    "currency",
    "exchange_rate",
    "amended_from",
    "current_payroll_period",
    "department",
    "designation",
    "branch",
    "bank_name",
    "bank_account_no",
    "mode_of_payment",
    "total_working_days",
    "leave_without_pay",
    "payment_days",
    "absent_days",
    "unmarked_days",
    "total_working_hours",
    "hour_rate",
    "base_hour_rate",
    "gross_pay",
    "base_gross_pay",
    "total_deduction",
    "base_total_deduction",
    "net_pay",
    "base_net_pay",
    "rounded_total",
    "base_rounded_total",
    "year_to_date",
    "month_to_date",
    "base_year_to_date",
    "base_month_to_date",
    "gross_year_to_date",
    "base_gross_year_to_date",
    "ctc",
    "income_from_other_sources",
    "total_earnings",
    "non_taxable_earnings",
    "deductions_before_tax_calculation",
    "tax_exemption_declaration",
    "standard_tax_exemption_amount",
    "annual_taxable_amount",
    "income_tax_deducted_till_date",
    "future_income_tax_deductions",
    "current_month_income_tax",
    "total_income_tax",
    "deduct_tax_for_unsubmitted_tax_exemption_proof",
    "salary_withholding",
    "salary_withholding_cycle",
)
CHILD_FIELDS: dict[str, tuple[str, ...]] = {
    "timesheets": ("idx", "time_sheet", "working_hours"),
    "leave_details": (
        "idx",
        "leave_type",
        "total_allocated_leaves",
        "expired_leaves",
        "used_leaves",
        "pending_leaves",
        "available_leaves",
    ),
    "earnings": (
        "idx",
        "parentfield",
        "salary_component",
        "abbr",
        "statistical_component",
        "is_tax_applicable",
        "is_flexible_benefit",
        "variable_based_on_taxable_salary",
        "depends_on_payment_days",
        "deduct_full_tax_on_selected_payroll_date",
        "condition",
        "amount_based_on_formula",
        "formula",
        "amount",
        "do_not_include_in_total",
        "default_amount",
        "additional_amount",
        "tax_on_flexible_benefit",
        "tax_on_additional_salary",
        "additional_salary",
        "exempted_from_income_tax",
        "is_recurring_additional_salary",
        "do_not_include_in_accounts",
        "accrual_component",
        "year_to_date",
    ),
    "deductions": (
        "idx",
        "parentfield",
        "salary_component",
        "abbr",
        "statistical_component",
        "is_tax_applicable",
        "is_flexible_benefit",
        "variable_based_on_taxable_salary",
        "depends_on_payment_days",
        "deduct_full_tax_on_selected_payroll_date",
        "condition",
        "amount_based_on_formula",
        "formula",
        "amount",
        "do_not_include_in_total",
        "default_amount",
        "additional_amount",
        "tax_on_flexible_benefit",
        "tax_on_additional_salary",
        "additional_salary",
        "exempted_from_income_tax",
        "is_recurring_additional_salary",
        "do_not_include_in_accounts",
        "accrual_component",
        "year_to_date",
    ),
    "accrued_benefits": ("idx", "salary_component", "amount"),
}


def _deny(message: str) -> None:
    # HRMS catches ValidationError per Slip. Authorization failure must stop its batch.
    raise frappe.PermissionError(_(message))


def _locked_rows(
    doctype: str, filters: Mapping[str, Any], fields: Sequence[str], order_by: str
) -> list[frappe._dict]:
    return cast(
        list[frappe._dict],
        frappe.db.get_values(
            doctype,
            dict(filters),
            list(fields),
            as_dict=True,
            order_by=order_by,
            for_update=True,
            wait=False,
        ),
    )


def locked_payroll_entry(name: str) -> Document:
    if not name:
        _deny("Payroll Entry is required.")
    row = frappe.db.get_value(
        "Payroll Entry",
        name,
        ["name", "docstatus", "workflow_state"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if not row:
        _deny("Payroll Entry could not be found.")
    # The first read acquires the parent mutex. Frappe's for_update loader then
    # current-reads the complete parent and child rows under that lock.
    return cast(Document, frappe.get_doc("Payroll Entry", name, for_update=True))


def current_roster(pe: Document, *, complete: bool = True, allow_queued: bool = False) -> list[Document]:
    """Lock every active Slip, including Withheld and unexpected employees."""
    pe = locked_payroll_entry(str(pe.name or ""))
    employees = _locked_rows(
        "Payroll Employee Detail",
        {"parenttype": "Payroll Entry", "parent": pe.name},
        ("name", "idx", "employee"),
        "idx asc, name asc",
    )
    expected = [str(row.employee or "") for row in employees]
    if not expected or any(not name for name in expected) or len(set(expected)) != len(expected):
        _deny("Payroll Entry employee roster is incomplete or duplicated.")
    rows = _locked_rows(
        "Salary Slip",
        {"payroll_entry": pe.name, "docstatus": ("!=", 2)},
        (
            "name",
            "employee",
            "docstatus",
            "company",
            "start_date",
            "end_date",
            "posting_date",
            "payroll_frequency",
            "currency",
            "salary_slip_based_on_timesheet",
        ),
        "employee asc, name asc",
    )
    if complete:
        if (
            str(pe.get("status") or "") == "Failed"
            or (str(pe.get("status") or "") == "Queued" and not allow_queued)
            or (_active_job(pe) and not allow_queued)
            or not int(pe.get("salary_slips_created") or 0)
            or str(pe.get("error_message") or "").strip()
        ):
            _deny("Payroll salary creation has not completed successfully.")
        if Counter(str(row.employee) for row in rows) != Counter(expected):
            _deny("Payroll Salary Slip roster does not match the approved employees.")
        historical = _locked_rows(
            "Salary Slip",
            {"payroll_entry": pe.name, "docstatus": 2},
            ("name", "employee"),
            "employee asc, name asc",
        )
        if any(str(row.employee) in expected for row in historical):
            _deny("Cancelled Salary Slip history requires native payroll correction before review.")
    for row in rows:
        if complete and any(
            str(row.get(field) or "") != str(pe.get(field) or "")
            for field in (
                "company",
                "start_date",
                "end_date",
                "posting_date",
                "payroll_frequency",
                "currency",
                "salary_slip_based_on_timesheet",
            )
        ):
            _deny("Payroll Salary Slip identity or period has changed.")
    # The identity query above preserves the payroll lock order. Load each
    # complete Slip and its child tables with a current locking read afterward.
    return [cast(Document, frappe.get_doc("Salary Slip", row.name, for_update=True)) for row in rows]


def _field_value(doc: Document, fieldname: str) -> Any:
    field = doc.meta.get_field(fieldname)
    if field is None and fieldname not in {"name", "idx", "parentfield"}:
        _deny("Payroll output schema has changed; a new review version is required.")
    value = doc.get(fieldname)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if field and field.fieldtype in {"Currency", "Float", "Percent"}:
        if value is None or value == "":
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            _deny("Payroll output contains an invalid number.")
        if not number.is_finite():
            _deny("Payroll output contains an invalid number.")
        precision = int(frappe.get_precision(doc.doctype, fieldname) or 0)
        return format(number.quantize(Decimal(1).scaleb(-precision)), "f")
    if field and field.fieldtype in {"Int", "Check"}:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            _deny("Payroll output contains an invalid integer.")
        if field.fieldtype == "Check":
            if number not in {0, 1}:
                _deny("Payroll output contains an invalid checkbox.")
            return bool(number)
        return number
    return value


def _slip_payload(slip: Document, dimensions: Sequence[str]) -> dict[str, Any]:
    payload = {field: _field_value(slip, field) for field in (*HEADER_FIELDS, *dimensions)}
    for table, fields in CHILD_FIELDS.items():
        children = sorted(slip.get(table) or [], key=lambda row: (int(row.idx or 0), str(row.name)))
        payload[table] = [
            {
                field: _field_value(row, field)
                for field in (*fields, *dimensions)
                if row.meta.has_field(field) or field in {"idx", "parentfield"}
            }
            for row in children
        ]
    return payload


def _schema(slip: Document, dimensions: Sequence[str]) -> dict[str, Any]:
    """Reject new financial fields until a reviewed seal version enumerates them."""
    result: dict[str, Any] = {}
    tables: dict[str, tuple[str, ...]] = {"Salary Slip": (*HEADER_FIELDS, *dimensions)}
    for table, fields in CHILD_FIELDS.items():
        definition = slip.meta.get_field(table)
        if not definition or not definition.options:
            _deny("Payroll output child table schema is missing.")
        tables[str(definition.options)] = (*fields, *dimensions)
    for doctype, fields in tables.items():
        meta = frappe.get_meta(doctype)
        allowed = set(fields)
        for field in meta.fields:
            name = str(field.fieldname or "")
            if name in allowed:
                continue
            if field.fieldtype in {"Currency", "Float", "Percent", "Int", "Check"} or (
                field.fieldtype in {"Data", "Link", "Select", "Date", "Datetime"}
                and search(r"(?:bank|account|payment|payable|tax|loan|advance|salary|wage)", name)
            ):
                if name not in {"salary_slip_review_state"}:
                    _deny("Payroll output schema has an unreviewed financial field.")
        result[doctype] = [
            {
                "field": name,
                "type": str(meta.get_field(name).fieldtype) if meta.get_field(name) else "identity",
                "precision": str(meta.get_field(name).precision or "") if meta.get_field(name) else "",
            }
            for name in fields
            if meta.has_field(name) or name in {"name", "idx", "parentfield"}
        ]
    return result


def _dimensions() -> list[str]:
    rows = _locked_rows(
        "Accounting Dimension",
        {},
        ("name", "fieldname", "disabled"),
        "name asc",
    )
    active = sorted(str(row.fieldname) for row in rows if not int(row.disabled or 0))
    if len(set(active)) != len(active) or active != sorted(
        str(field) for field in get_accounting_dimensions()
    ):
        _deny("Payroll Accounting Dimension registry changed during review.")
    return active


def _native_sources(pe: Document, slips: Sequence[Document]) -> dict[str, Any]:
    """Lock the masters HRMS reads when it builds accrual and bank JEs."""
    names = sorted(
        {
            str(detail.salary_component)
            for slip in slips
            for table in ("earnings", "deductions")
            for detail in (slip.get(table) or [])
            if detail.salary_component
        }
    )
    components = []
    for name in names:
        row = frappe.db.get_value(
            "Salary Component",
            name,
            ["name", "statistical_component"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not row:
            _deny("Payroll Salary Component is missing.")
        accounts = _locked_rows(
            "Salary Component Account",
            {"parent": name, "company": pe.get("company")},
            ("name", "account"),
            "name asc",
        )
        if len(accounts) != 1:
            _deny("Payroll Salary Component account is incomplete or duplicated.")
        for slip in slips:
            for table in ("earnings", "deductions"):
                for detail in slip.get(table) or []:
                    if detail.salary_component == name and int(detail.statistical_component or 0) != int(
                        row.statistical_component or 0
                    ):
                        _deny("Payroll Salary Component changed; recalculate the Salary Slip.")
        components.append(
            {"name": name, "statistical": int(row.statistical_component or 0), "account": accounts[0].account}
        )
    assignments = []
    for slip in sorted(slips, key=lambda item: (str(item.employee), str(item.name))):
        employee = str(slip.get("employee"))
        candidates = _locked_rows(
            "Salary Structure Assignment",
            {"employee": employee, "docstatus": 1, "from_date": ("<=", pe.get("end_date"))},
            ("name", "from_date", "salary_structure", "company"),
            "from_date asc, name asc",
        )
        matched = [row for row in candidates if row.salary_structure == slip.get("salary_structure")]
        if not matched:
            _deny("Payroll Salary Structure Assignment is missing.")
        selected = matched[-1]
        if len(matched) > 1 and matched[-2].from_date == selected.from_date:
            _deny("Payroll has ambiguous effective Salary Structure Assignments.")
        if selected.company != pe.get("company"):
            _deny("Payroll Salary Structure Assignment company has changed.")
        cost_centers = _locked_rows(
            "Employee Cost Center",
            {"parent": selected.name},
            ("name", "idx", "cost_center", "percentage"),
            "idx asc, name asc",
        )
        employee_row = frappe.db.get_value(
            "Employee",
            employee,
            ["name", "company", "payroll_cost_center", "department"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not employee_row or employee_row.company != pe.get("company"):
            _deny("Payroll Employee master is missing or belongs to another Company.")
        department_row = None
        if employee_row.department:
            department_row = frappe.db.get_value(
                "Department",
                employee_row.department,
                ["name", "payroll_cost_center"],
                as_dict=True,
                for_update=True,
                wait=False,
            )
            if not department_row:
                _deny("Payroll Employee Department is missing.")
        assignments.append(
            {
                "employee": employee,
                "name": selected.name,
                "from_date": selected.from_date,
                "salary_structure": selected.salary_structure,
                "cost_centers": [dict(row) for row in cost_centers],
                "employee_cost_center": employee_row.payroll_cost_center,
                "employee_department": employee_row.department,
                "department_cost_center": department_row.payroll_cost_center if department_row else None,
            }
        )
    additional_names = sorted(
        {
            str(detail.additional_salary)
            for slip in slips
            for table in ("earnings", "deductions")
            for detail in (slip.get(table) or [])
            if detail.additional_salary
        }
    )
    additional = []
    for name in additional_names:
        row = frappe.db.get_value(
            "Additional Salary",
            name,
            ["name", "ref_doctype", "ref_docname"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not row:
            _deny("Referenced Additional Salary is missing.")
        additional.append(dict(row))
    settings = frappe.qb.get_query(
        table="Singles",
        filters={
            "doctype": "Payroll Settings",
            "field": "process_payroll_accounting_entry_based_on_employee",
        },
        fields="value",
        for_update=True,
        wait=False,
    ).run(as_dict=True)
    if len(settings) != 1:
        _deny("Payroll accounting setting is missing or duplicated.")
    account_names = sorted(
        {
            str(account)
            for account in (
                pe.get("payroll_payable_account"),
                pe.get("payment_account"),
                *(row["account"] for row in components),
            )
            if account
        }
    )
    accounts = (
        _locked_rows(
            "Account",
            {"name": ("in", account_names)},
            ("name", "company", "account_currency", "account_type", "is_group", "disabled"),
            "name asc",
        )
        if account_names
        else []
    )
    if len(accounts) != len(account_names) or any(
        row.company != pe.get("company") or int(row.disabled or 0) or int(row.is_group or 0)
        for row in accounts
    ):
        _deny("Payroll Account master is missing or belongs to another Company.")
    company = frappe.db.get_value(
        "Company",
        str(pe.get("company") or ""),
        ["name", "default_currency"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if not company:
        _deny("Payroll Company master is missing.")
    return {
        "components": components,
        "assignments": assignments,
        "additional_salaries": additional,
        "employee_wise_accounting": int(settings[0].value or 0),
        "accounts": [dict(row) for row in accounts],
        "company_currency": company.default_currency,
    }


def output_payload(pe: Document, slips: Sequence[Document]) -> dict[str, Any]:
    if "lending" in frappe.get_installed_apps():
        _deny("Payroll output review requires a versioned Lending contract.")
    dimensions = _dimensions()
    employees = _locked_rows(
        "Payroll Employee Detail",
        {"parenttype": "Payroll Entry", "parent": pe.name},
        ("name", "idx", "employee"),
        "idx asc, name asc",
    )
    return {
        "version": VERSION,
        "payroll_entry": pe.name,
        "company": pe.get("company"),
        "posting_date": pe.get("posting_date"),
        "start_date": pe.get("start_date"),
        "end_date": pe.get("end_date"),
        "employees": [row.employee for row in employees],
        "dimensions": dimensions,
        "schema": _schema(slips[0], dimensions),
        "sources": _native_sources(pe, slips),
        "slips": [
            _slip_payload(slip, dimensions)
            for slip in sorted(slips, key=lambda item: (str(item.employee), str(item.name)))
        ],
    }


def output_digest(pe: Document, slips: Sequence[Document]) -> str:
    return critical_digest(output_payload(pe, slips))


def _signature(pe: Document, digest: str, reviewer: str, acted_at: str, revision: int) -> str:
    payload = critical_digest(
        {
            "version": VERSION,
            "payroll_entry": pe.name,
            "company": pe.get("company"),
            "digest": digest,
            "reviewer": reviewer,
            "acted_at": acted_at,
            "revision": revision,
        }
    )
    return hmac.new(get_encryption_key().encode(), payload.encode(), hashlib.sha256).hexdigest()


def require_output_review(
    pe: Document, slips: Sequence[Document] | None = None, *, allow_queued: bool = False
) -> list[Document]:
    pe = locked_payroll_entry(str(pe.name or ""))
    if int(pe.docstatus or 0) != 1 or pe.get("workflow_state") not in {REVIEWED, CLOSED}:
        _deny("Payroll calculated output has not been reviewed.")
    if pe.get("output_review_version") != VERSION:
        _deny("Payroll calculated output review version is missing or unknown.")
    if not all(pe.get(field) for field in OUTPUT_FIELDS):
        _deny("Payroll calculated output review evidence is incomplete.")
    # Caller-provided Documents may predate a competing writer's committed
    # update. Rebuild the signed roster from the locked current-read source.
    active = current_roster(pe, allow_queued=allow_queued)
    digest = output_digest(pe, active)
    if not hmac.compare_digest(str(pe.get("output_review_digest")), digest):
        _deny("Payroll calculated output has changed since review.")
    expected = _signature(
        pe,
        digest,
        str(pe.get("output_reviewed_by")),
        str(pe.get("output_reviewed_at")),
        int(pe.get("output_review_revision")),
    )
    if not hmac.compare_digest(str(pe.get("output_review_signature")), expected):
        _deny("Payroll calculated output review signature is invalid.")
    return active


def seal_output_review(pe: Document, slips: Sequence[Document], reviewer: str) -> None:
    digest = output_digest(pe, slips)
    revision = int(pe.get("output_review_revision") or 0) + 1
    acted_at = frappe.utils.now()
    pe.set("output_reviewed_by", reviewer)
    pe.set("output_reviewed_at", acted_at)
    pe.set("output_review_digest", digest)
    pe.set("output_review_version", VERSION)
    pe.set("output_review_revision", revision)
    pe.set("output_review_signature", _signature(pe, digest, reviewer, acted_at, revision))


def clear_output_review(pe: Document) -> None:
    for field in OUTPUT_FIELDS[:-1]:
        if field == "output_review_version" and pe.get(field) == VERSION:
            continue
        pe.set(field, None)
    pe.set("output_review_revision", int(pe.get("output_review_revision") or 0) + 1)


@contextmanager
def native_operation(payroll_entry: str, kind: str) -> Any:
    token = _native_operation.set((payroll_entry, kind))
    try:
        yield
    finally:
        _native_operation.reset(token)


def require_native_operation(payroll_entry: str, kind: str) -> None:
    if _native_operation.get() != (payroll_entry, kind):
        _deny("Salary Slip processing must use the reviewed Payroll Entry operation.")


def native_operation_kind(payroll_entry: str) -> str | None:
    current = _native_operation.get()
    return current[1] if current and current[0] == payroll_entry else None


def _clear_payroll_read_cache(pe: Document, slips: Sequence[Document]) -> None:
    """Remove request-local values HRMS reads with cache=True after our locked read."""
    frappe.db.value_cache.pop("Payroll Settings", None)
    frappe.clear_document_cache("Payroll Settings", "Payroll Settings")
    for account in (pe.get("payroll_payable_account"), pe.get("payment_account")):
        if account:
            frappe.clear_document_cache("Account", str(account))
    for slip in slips:
        frappe.clear_document_cache("Employee", str(slip.get("employee")))


def require_current_payroll_fields(candidate: Document, persisted: Document) -> None:
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import CRITICAL_FIELDS

    fields = (*CRITICAL_FIELDS, *sorted(str(field) for field in get_accounting_dimensions()))
    if any(candidate.get(field) != persisted.get(field) for field in fields):
        _deny("Payroll Entry fields changed before native processing.")


def require_sealed_candidate(candidate: Document, persisted: Document) -> None:
    """Verify the actual Workflow candidate before Frappe persists its new state."""
    slips = current_roster(persisted)
    digest = output_digest(persisted, slips)
    if candidate.get("output_review_version") != VERSION or not hmac.compare_digest(
        str(candidate.get("output_review_digest") or ""), digest
    ):
        _deny("Payroll calculated output review is stale.")
    signature = _signature(
        persisted,
        digest,
        str(candidate.get("output_reviewed_by") or ""),
        str(candidate.get("output_reviewed_at") or ""),
        int(candidate.get("output_review_revision") or 0),
    )
    if not hmac.compare_digest(str(candidate.get("output_review_signature") or ""), signature):
        _deny("Payroll calculated output review signature is invalid.")


def _caller(pe: Document, expected_user: str | None = None) -> str:
    user = str(frappe.session.user or "")
    if user in {"", "Guest", "Administrator"} or (expected_user and user != expected_user):
        _deny("Payroll processing requires the initiating business User.")
    if not frappe.db.get_value("User", user, "enabled") or "HR Manager" not in frappe.get_roles(user):
        _deny("Payroll processing requires a current HR Manager.")
    if not frappe.has_permission("Payroll Entry", "write", doc=pe, user=user):
        _deny("Payroll Entry write permission is required.")
    return user


def _creation_args(pe: Document) -> frappe._dict:
    # Mirrors the native HRMS argument contract, including its original types.
    return frappe._dict(
        {
            "salary_slip_based_on_timesheet": pe.get("salary_slip_based_on_timesheet"),
            "payroll_frequency": pe.get("payroll_frequency"),
            "start_date": pe.get("start_date"),
            "end_date": pe.get("end_date"),
            "company": pe.get("company"),
            "posting_date": pe.get("posting_date"),
            "deduct_tax_for_unsubmitted_tax_exemption_proof": pe.get(
                "deduct_tax_for_unsubmitted_tax_exemption_proof"
            ),
            "payroll_entry": pe.name,
            "exchange_rate": pe.get("exchange_rate"),
            "currency": pe.get("currency"),
        }
    )


def _job_id(pe: Document, operation: str) -> str:
    return f"payroll-output-{pe.name}-{operation}-{int(pe.get('output_review_revision') or 0)}"


def _active_job(pe: Document) -> bool:
    return any(is_job_enqueued(_job_id(pe, kind)) for kind in ("create", "submit"))


def _lock_creation_sources(pe: Document, employees: Sequence[str]) -> None:
    """Hold the input masters used by native Slip construction through its worker."""
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import _payroll_source_revisions

    inventory = _payroll_source_revisions(pe)
    components = sorted(str(row.name) for row in inventory["salary_components"])
    if components:
        _locked_rows("Salary Component", {"name": ("in", components)}, ("name", "modified"), "name asc")
        _locked_rows(
            "Salary Component Account",
            {"parent": ("in", components), "company": pe.get("company")},
            ("name", "parent", "account"),
            "parent asc, name asc",
        )
    assignments = _locked_rows(
        "Salary Structure Assignment",
        {"employee": ("in", list(employees)), "docstatus": 1, "from_date": ("<=", pe.get("end_date"))},
        ("name", "employee", "salary_structure", "income_tax_slab"),
        "employee asc, from_date asc, name asc",
    )
    structures = sorted({str(row.salary_structure) for row in assignments if row.salary_structure})
    slabs = sorted({str(row.income_tax_slab) for row in assignments if row.income_tax_slab})
    if structures:
        _locked_rows("Salary Structure", {"name": ("in", structures)}, ("name", "modified"), "name asc")
        _locked_rows(
            "Salary Detail",
            {"parenttype": "Salary Structure", "parent": ("in", structures)},
            ("name", "parent", "idx", "salary_component"),
            "parent asc, idx asc, name asc",
        )
    if slabs:
        _locked_rows("Income Tax Slab", {"name": ("in", slabs)}, ("name", "modified"), "name asc")
    employee_rows = _locked_rows(
        "Employee",
        {"name": ("in", list(employees))},
        ("name", "company", "department", "payroll_cost_center"),
        "name asc",
    )
    if len(employee_rows) != len(employees) or any(row.company != pe.get("company") for row in employee_rows):
        _deny("Payroll Employee master is missing or belongs to another Company.")
    departments = sorted({str(row.department) for row in employee_rows if row.department})
    if departments:
        _locked_rows(
            "Department",
            {"name": ("in", departments)},
            ("name", "payroll_cost_center"),
            "name asc",
        )
    _locked_rows(
        "Additional Salary",
        {"employee": ("in", list(employees)), "company": pe.get("company"), "docstatus": 1},
        ("name", "employee", "salary_component", "amount", "ref_doctype", "ref_docname"),
        "name asc",
    )
    frappe.qb.get_query(
        table="Singles",
        filters={"doctype": "Payroll Settings"},
        fields=["field", "value"],
        order_by="field asc",
        for_update=True,
        wait=False,
    ).run(as_dict=True)


def _preflight_create(pe: Document, expected_user: str | None = None) -> tuple[list[str], frappe._dict]:
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import validate_downstream_operation

    if pe.get("workflow_state") != SUBMITTED or int(pe.docstatus or 0) != 1:
        _deny("Salary Slip creation requires the submitted Payroll Entry state.")
    _caller(pe, expected_user)
    employees = _locked_rows(
        "Payroll Employee Detail",
        {"parenttype": "Payroll Entry", "parent": pe.name},
        ("name", "idx", "employee"),
        "idx asc, name asc",
    )
    names = [str(row.employee or "") for row in employees]
    if not names or len(set(names)) != len(names) or any(not name for name in names):
        _deny("Payroll Entry employees are incomplete or duplicated.")
    current_roster(pe, complete=False)
    _lock_creation_sources(pe, names)
    validate_downstream_operation(pe, require_current_digest=True)
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import (
        verify_native_payroll_input_readers,
    )

    verify_native_payroll_input_readers(pe)
    return names, _creation_args(pe)


def create_salary_slips(pe: Document, *args: Any, **kwargs: Any) -> None:
    if args or kwargs:
        _deny("Salary Slip creation does not accept additional arguments.")
    current = locked_payroll_entry(str(pe.name))
    employees, native_args = _preflight_create(current)
    if str(current.get("status") or "") == "Queued" or _active_job(current):
        _deny("Payroll Entry already has a queued batch operation.")
    if len(employees) > 30 or frappe.flags.enqueue_payroll_entry:
        current.db_set("status", "Queued")
        frappe.enqueue(
            create_reviewed_salary_slips_for_employees,
            timeout=3000,
            enqueue_after_commit=True,
            deduplicate=True,
            job_id=_job_id(current, "create"),
            payroll_entry_name=str(current.name),
            expected_employee_ids=employees,
            expected_args=dict(native_args),
            expected_revision=int(current.get("output_review_revision") or 0),
            initiating_user=str(frappe.session.user),
        )
        frappe.msgprint(
            _("Salary Slip creation is queued. It may take a few minutes"), alert=True, indicator="blue"
        )
    else:
        with native_operation(str(current.name), "create"):
            _clear_payroll_read_cache(current, [])
            create_salary_slips_for_employees(employees, native_args, publish_progress=False)
        pe.reload()


def create_reviewed_salary_slips_for_employees(
    payroll_entry_name: str,
    expected_employee_ids: list[str],
    expected_args: Mapping[str, Any],
    expected_revision: int,
    initiating_user: str,
) -> None:
    pe = locked_payroll_entry(payroll_entry_name)
    employees, native_args = _preflight_create(pe, initiating_user)
    if (
        employees != expected_employee_ids
        or critical_digest(dict(native_args)) != critical_digest(dict(expected_args))
        or int(pe.get("output_review_revision") or 0) != expected_revision
        or str(pe.get("status") or "") != "Queued"
    ):
        _deny("Queued Salary Slip creation no longer matches the Payroll Entry.")
    with native_operation(str(pe.name), "create"):
        _clear_payroll_read_cache(pe, [])
        create_salary_slips_for_employees(employees, native_args, publish_progress=False)


def _preflight_submit(
    pe: Document, expected_user: str | None = None
) -> tuple[list[Document], list[frappe._dict]]:
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import validate_downstream_operation

    validate_downstream_operation(pe, require_current_digest=False)
    if pe.get("workflow_state") != REVIEWED:
        _deny("Salary Slip submission requires reviewed calculated output.")
    _caller(pe, expected_user)
    active = require_output_review(pe, allow_queued=expected_user is not None)
    selected = cast(list[frappe._dict], cast(Any, pe).get_sal_slip_list(ss_status=0))
    expected = {
        str(slip.name) for slip in active if int(slip.docstatus or 0) == 0 and not slip.get("journal_entry")
    }
    if {str(row[0]) for row in selected} != expected or len(selected) != len(expected):
        _deny("Native Salary Slip selection does not match the reviewed roster.")
    return active, selected


def submit_salary_slips(pe: Document, *args: Any, **kwargs: Any) -> None:
    if args or kwargs:
        _deny("Salary Slip submission does not accept additional arguments.")
    current = locked_payroll_entry(str(pe.name))
    active, selected = _preflight_submit(current)
    if str(current.get("status") or "") == "Queued" or _active_job(current):
        _deny("Payroll Entry already has a queued batch operation.")
    if not selected:
        _deny("There are no reviewed draft Salary Slips to submit.")
    if len(selected) > 30 or frappe.flags.enqueue_payroll_entry:
        current.db_set("status", "Queued")
        frappe.enqueue(
            submit_reviewed_salary_slips_for_employees,
            timeout=3000,
            enqueue_after_commit=True,
            deduplicate=True,
            job_id=_job_id(current, "submit"),
            payroll_entry_name=str(current.name),
            expected_draft_slip_names=[str(row[0]) for row in selected],
            expected_output_revision=int(current.get("output_review_revision") or 0),
            initiating_user=str(frappe.session.user),
        )
        frappe.msgprint(
            _("Salary Slip submission is queued. It may take a few minutes"), alert=True, indicator="blue"
        )
    else:
        with native_operation(str(current.name), "submit"):
            _clear_payroll_read_cache(current, active)
            submit_salary_slips_for_employees(current, selected, publish_progress=False)


def submit_reviewed_salary_slips_for_employees(
    payroll_entry_name: str,
    expected_draft_slip_names: list[str],
    expected_output_revision: int,
    initiating_user: str,
) -> None:
    pe = locked_payroll_entry(payroll_entry_name)
    active, selected = _preflight_submit(pe, initiating_user)
    if (
        [str(row[0]) for row in selected] != expected_draft_slip_names
        or int(pe.get("output_review_revision") or 0) != expected_output_revision
        or str(pe.get("status") or "") != "Queued"
    ):
        _deny("Queued Salary Slip submission no longer matches the reviewed batch.")
    with native_operation(str(pe.name), "submit"):
        _clear_payroll_read_cache(pe, active)
        submit_salary_slips_for_employees(pe, selected, publish_progress=False)


def _active_journals(pe: Document, slips: Sequence[Document]) -> dict[str, Document]:
    refs = _locked_rows(
        "Journal Entry Account",
        {"reference_type": "Payroll Entry", "reference_name": pe.name},
        ("name", "parent"),
        "parent asc, name asc",
    )
    names = sorted(
        {str(row.parent) for row in refs}
        | {str(slip.get("journal_entry")) for slip in slips if slip.get("journal_entry")}
    )
    journals: dict[str, Document] = {}
    for name in names:
        row = frappe.db.get_value(
            "Journal Entry",
            name,
            ["name", "docstatus"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not row:
            _deny("Payroll Journal Entry link is missing.")
        # The JE header identity is locked above; read its complete accounts
        # table under the same lock rather than using a stale ordinary snapshot.
        journals[name] = cast(Document, frappe.get_doc("Journal Entry", name, for_update=True))
    return journals


def require_cancellable_accounting(pe: Document) -> None:
    """Require finance to reverse every payroll JE through its Workflow first."""
    slips = current_roster(pe, complete=False)
    if any(int(je.docstatus or 0) != 2 for je in _active_journals(pe, slips).values()):
        _deny("Cancel linked payroll Journal Entries through finance approval first.")


def _money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        _deny("Payroll accounting contains an invalid amount.")
    if not result.is_finite():
        _deny("Payroll accounting contains an invalid amount.")
    return result


def _currency_round(value: Decimal) -> Decimal:
    precision = int(frappe.get_precision("GL Entry", "debit") or 2)
    return value.quantize(Decimal(1).scaleb(-precision))


def _slip_obligation(slip: Document) -> Decimal:
    amount = Decimal(0)
    for table, multiplier in (("earnings", 1), ("deductions", -1)):
        for detail in slip.get(table) or []:
            if int(detail.get("do_not_include_in_total") or 0) and int(
                detail.get("do_not_include_in_accounts") or 0
            ):
                continue
            if int(detail.get("statistical_component") or 0):
                continue
            amount += multiplier * _money(detail.get("amount"))
    return amount


def _native_accrual_projection(
    pe: Document, slips: Sequence[Document], sources: Mapping[str, Any]
) -> dict[str, Decimal]:
    """Project only HRMS's payable line from sealed rows and its native allocation rule."""
    precision = int(frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 2)
    components = {str(row["name"]): str(row["account"]) for row in sources["components"]}
    assignments = {str(row["employee"]): row for row in sources["assignments"]}
    additional = {str(row["name"]): row for row in sources["additional_salaries"]}
    employee_wise = int(sources["employee_wise_accounting"])
    grouped: dict[str, dict[tuple[str, str], float]] = {"earnings": {}, "deductions": {}}
    advance_amounts: list[float] = []
    by_employee: dict[str, dict[str, float]] = {}
    for slip in slips:
        employee = str(slip.get("employee"))
        assignment = assignments.get(employee)
        if not assignment:
            _deny("Payroll cost center allocation source is missing.")
        cost_centers = _effective_cost_centers(pe, cast(Mapping[str, Any], assignment))
        for table in ("earnings", "deductions"):
            for detail in slip.get(table) or []:
                if int(detail.get("do_not_include_in_total") or 0) and int(
                    detail.get("do_not_include_in_accounts") or 0
                ):
                    continue
                component = str(detail.get("salary_component") or "")
                account = str(components.get(component) or "")
                if not account:
                    _deny("Payroll Salary Component account source is missing.")
                amount = flt(detail.get("amount"))
                extra = additional.get(str(detail.get("additional_salary") or ""))
                is_advance = table == "deductions" and extra and extra["ref_doctype"] == "Employee Advance"
                for center, percentage in cost_centers.items():
                    allocated = flt(amount) * percentage / 100
                    if is_advance:
                        advance_amounts.append(allocated)
                    else:
                        key = (account, center)
                        grouped[table][key] = grouped[table].get(key, 0.0) + allocated
                    if employee_wise:
                        by_employee.setdefault(employee, {}).setdefault(table, 0.0)
                        by_employee[employee][table] += allocated
    rate = flt(pe.get("exchange_rate") or 1)
    if employee_wise:
        return {
            employee: _currency_round(
                Decimal(
                    str(
                        flt(flt(values.get("earnings", 0)) - flt(values.get("deductions", 0)), precision)
                        * rate
                    )
                )
            )
            for employee, values in by_employee.items()
        }
    payable = 0.0
    for amount in grouped["earnings"].values():
        payable += flt(amount, precision)
    for amount in grouped["deductions"].values():
        payable -= flt(amount, precision)
    for amount in advance_amounts:
        payable -= flt(amount, precision)
    return {"": _currency_round(Decimal(str(flt(payable, precision) * rate)))}


def _native_accrual_component_projection(
    pe: Document, slips: Sequence[Document], sources: Mapping[str, Any]
) -> dict[tuple[str, str, str, str, str], Decimal]:
    """Match native account/cost-center allocation before accepting its payable row."""
    precision = int(frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 2)
    component_accounts = {str(row["name"]): str(row["account"]) for row in sources["components"]}
    assignments = {str(row["employee"]): row for row in sources["assignments"]}
    additional = {str(row["name"]): row for row in sources["additional_salaries"]}
    accounts = {str(row["name"]): row for row in sources["accounts"]}
    company_currency = str(sources["company_currency"])
    rate = flt(pe.get("exchange_rate") or 1)
    grouped: dict[tuple[str, str, str, str, str], float] = {}
    advances: list[tuple[tuple[str, str, str, str, str], float]] = []
    for slip in slips:
        employee = str(slip.get("employee"))
        assignment = assignments.get(employee)
        if not assignment:
            _deny("Payroll cost center allocation source is missing.")
        for table in ("earnings", "deductions"):
            for detail in slip.get(table) or []:
                if int(detail.get("do_not_include_in_total") or 0) and int(
                    detail.get("do_not_include_in_accounts") or 0
                ):
                    continue
                account = component_accounts.get(str(detail.get("salary_component") or ""))
                if not account or account not in accounts:
                    _deny("Payroll Salary Component account source is missing.")
                account = str(account or "")
                extra = additional.get(str(detail.get("additional_salary") or ""))
                is_advance = table == "deductions" and extra and extra["ref_doctype"] == "Employee Advance"
                for center, percentage in _effective_cost_centers(
                    pe, cast(Mapping[str, Any], assignment)
                ).items():
                    amount = flt(detail.get("amount")) * percentage / 100
                    key = (
                        account,
                        center,
                        table,
                        str(extra["ref_docname"]) if is_advance else "",
                        employee if is_advance else "",
                    )
                    if is_advance:
                        advances.append((key, amount))
                    else:
                        grouped[key] = grouped.get(key, 0.0) + amount
    projected: dict[tuple[str, str, str, str, str], Decimal] = {}
    for key, amount in [*grouped.items(), *advances]:
        account_currency = str(accounts[key[0]]["account_currency"])
        currency_amount = flt(amount) * (rate if account_currency == company_currency else 1)
        if not currency_amount:
            continue
        exchange = 1 if account_currency == company_currency else rate
        base = _currency_round(Decimal(str(flt(currency_amount, precision) * exchange)))
        projected[key] = projected.get(key, Decimal(0)) + base
    return projected


def _candidate_accrual_components(
    je: Document, payable_account: str
) -> dict[tuple[str, str, str, str, str], Decimal]:
    actual: dict[tuple[str, str, str, str, str], Decimal] = {}
    for row in je.get("accounts") or []:
        if row.get("account") == payable_account:
            continue
        debit = _money(row.get("debit"))
        credit = _money(row.get("credit"))
        if bool(debit) == bool(credit):
            _deny("Native accrual component row has an invalid direction.")
        reference_type = str(row.get("reference_type") or "")
        reference_name = str(row.get("reference_name") or "")
        party_type = str(row.get("party_type") or "")
        party = str(row.get("party") or "")
        if (
            reference_type not in {"", "Employee Advance"}
            or (reference_type == "Employee Advance")
            != bool(reference_name and party_type == "Employee" and party)
            or (not reference_type and (reference_name or party_type or party))
        ):
            _deny("Native accrual component reference or party is invalid.")
        key = (
            str(row.get("account") or ""),
            str(row.get("cost_center") or ""),
            "earnings" if debit else "deductions",
            reference_name,
            party,
        )
        actual[key] = actual.get(key, Decimal(0)) + (debit or credit)
    return {key: _currency_round(value) for key, value in actual.items()}


def _effective_cost_centers(pe: Document, assignment: Mapping[str, Any]) -> dict[str, float]:
    rows = assignment["cost_centers"]
    if rows:
        centers = {str(row["cost_center"]): flt(row["percentage"]) for row in rows}
        if len(centers) != len(rows):
            _deny("Payroll cost center allocation is duplicated.")
        return centers
    fallback = (
        assignment.get("employee_cost_center")
        or assignment.get("department_cost_center")
        or pe.get("cost_center")
    )
    if not fallback:
        _deny("Payroll cost center is missing.")
    return {str(fallback): 100.0}


def _native_bank_projection(
    pe: Document, slips: Sequence[Document], sources: Mapping[str, Any]
) -> dict[str, Decimal]:
    """Project HRMS Bank/Cash payable rows, including employee cost center rounding."""
    precision = int(frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 2)
    rate = flt(pe.get("exchange_rate") or 1)
    company_currency = str(sources["company_currency"])
    accounts = {str(row["name"]): row for row in sources["accounts"]}
    employee_wise = int(sources["employee_wise_accounting"])
    amounts = {str(slip.get("employee")): flt(str(_slip_obligation(slip))) for slip in slips}
    if not employee_wise:
        account = accounts.get(str(pe.get("payroll_payable_account")))
        if not account:
            _deny("Payroll payable Account master is missing.")
        account = cast(Mapping[str, Any], account)
        amount = flt(sum(amounts.values()))
        currency_amount = flt(amount) * (rate if account["account_currency"] == company_currency else 1)
        exchange = 1 if account["account_currency"] == company_currency else rate
        return {"": _currency_round(Decimal(str(flt(currency_amount, precision) * exchange)))}
    payment_account = accounts.get(str(pe.get("payment_account")))
    if not payment_account:
        _deny("Payroll payment Account master is missing.")
    payment_account = cast(Mapping[str, Any], payment_account)
    assignments = {str(row["employee"]): row for row in sources["assignments"]}
    projected: dict[str, Decimal] = {}
    for employee, amount in amounts.items():
        assignment = assignments.get(employee)
        if not assignment:
            _deny("Payroll Employee cost center allocation is missing.")
        assignment = cast(Mapping[str, Any], assignment)
        currency_amount = flt(amount) * (
            rate if payment_account["account_currency"] == company_currency else 1
        )
        exchange = 1 if payment_account["account_currency"] == company_currency else rate
        projected[employee] = sum(
            (
                _currency_round(
                    Decimal(str(flt(flt(currency_amount) * percentage / 100, precision) * exchange))
                )
                for percentage in _effective_cost_centers(pe, assignment).values()
            ),
            Decimal(0),
        )
    return projected


def _payable_candidate(je: Document, pe: Document, *, credit: bool) -> dict[str, Decimal]:
    expected_account = str(pe.get("payroll_payable_account") or "")
    if je.get("company") != pe.get("company") or int(je.docstatus or 0) != 0:
        _deny("Native payroll Journal Entry candidate is not a draft in the approved Company.")
    parties: dict[str, Decimal] = {}
    debit = Decimal(0)
    total_credit = Decimal(0)
    for row in je.get("accounts") or []:
        if row.get("reference_type") == "Payroll Entry" and row.get("reference_name") != pe.name:
            _deny("Native payroll Journal Entry candidate references another Payroll Entry.")
        row_debit = _money(row.get("debit"))
        row_credit = _money(row.get("credit"))
        debit += row_debit
        total_credit += row_credit
        if row.get("account") != expected_account:
            continue
        if row.get("reference_type") != "Payroll Entry" or row.get("reference_name") != pe.name:
            _deny("Native payroll payable row is not linked to its Payroll Entry.")
        party_type = str(row.get("party_type") or "")
        party = str(row.get("party") or "")
        if (party_type and party_type != "Employee") or (bool(party_type) != bool(party)):
            _deny("Native payroll payable party is invalid.")
        key = party if party_type else ""
        amount = row_credit if credit else row_debit
        if (row_debit if credit else row_credit) != 0:
            _deny("Native payroll payable row has the wrong direction.")
        parties[key] = parties.get(key, Decimal(0)) + amount
    if _currency_round(debit) != _currency_round(total_credit) or not parties:
        _deny("Native payroll Journal Entry candidate is unbalanced or lacks payable rows.")
    return {party: _currency_round(amount) for party, amount in parties.items()}


def validate_accrual_candidate(pe: Document, je: Document, submitted_slips: Sequence[Document]) -> None:
    if native_operation_kind(str(pe.name)) != "submit" or je.get("voucher_type") != "Journal Entry":
        _deny("Payroll accrual Journal Entry is outside the reviewed native submission.")
    fresh = locked_payroll_entry(str(pe.name))
    active = require_output_review(fresh, allow_queued=True)
    allowed = {str(slip.name): slip for slip in active}
    if not submitted_slips or any(str(slip.name) not in allowed for slip in submitted_slips):
        _deny("Native accrual Salary Slips are outside the reviewed roster.")
    source = output_payload(fresh, active)["sources"]
    expected = _native_accrual_projection(
        fresh, [allowed[str(slip.name)] for slip in submitted_slips], source
    )
    if _payable_candidate(je, fresh, credit=True) != expected:
        _deny("Native accrual payable does not match reviewed Salary Slip components.")
    if _candidate_accrual_components(je, str(fresh.get("payroll_payable_account") or "")) != (
        _native_accrual_component_projection(
            fresh, [allowed[str(slip.name)] for slip in submitted_slips], source
        )
    ):
        _deny("Native accrual component allocation differs from reviewed Salary Slips.")
    require_output_review(fresh, allow_queued=True)


def preflight_bank(pe: Document, for_withheld_salaries: bool) -> tuple[list[Document], Decimal]:
    fresh = locked_payroll_entry(str(pe.name))
    active = require_output_review(fresh)
    if (for_withheld_salaries and fresh.get("workflow_state") not in {REVIEWED, CLOSED}) or (
        not for_withheld_salaries and fresh.get("workflow_state") != REVIEWED
    ):
        _deny("Payroll bank operation is not allowed in its current Workflow state.")
    _caller(fresh)
    if any(int(slip.docstatus or 0) != 1 for slip in active):
        _deny("Payroll bank operation requires all reviewed Salary Slips submitted.")
    journals = _active_journals(fresh, active)
    accrual_names = {str(slip.get("journal_entry")) for slip in active if slip.get("journal_entry")}
    if any(_slip_obligation(slip) and not slip.get("journal_entry") for slip in active):
        _deny("Payroll bank operation requires every native accrual link.")
    if any(int(journals[name].docstatus or 0) != 1 for name in accrual_names):
        _deny("Payroll bank operation requires approved accrual Journal Entries.")
    payment_names = {
        name
        for name, journal in journals.items()
        if name not in accrual_names and int(journal.docstatus or 0) != 2
    }
    if not for_withheld_salaries and payment_names:
        _deny("Payroll already has a Bank or Cash Journal Entry.")
    selected = [slip for slip in active if (slip.get("status") == "Withheld") == for_withheld_salaries]
    if for_withheld_salaries:
        for slip in selected:
            cycle = frappe.db.get_value(
                "Salary Withholding Cycle",
                str(slip.get("salary_withholding_cycle") or ""),
                ["journal_entry"],
                as_dict=True,
                for_update=True,
                wait=False,
            )
            if not cycle or cycle.journal_entry:
                _deny("Withheld Salary Slip cycle is missing or already has a payment Journal Entry.")
    amount = sum((_slip_obligation(slip) for slip in selected), Decimal(0))
    _clear_payroll_read_cache(fresh, active)
    return active, amount


def validate_bank_candidate(
    pe: Document, je: Document | None, for_withheld_salaries: bool, expected: Decimal
) -> None:
    fresh = locked_payroll_entry(str(pe.name))
    active = require_output_review(fresh)
    selected = [slip for slip in active if (slip.get("status") == "Withheld") == for_withheld_salaries]
    source = output_payload(fresh, active)["sources"]
    expected_parties = _native_bank_projection(fresh, selected, source)
    if expected != sum((_slip_obligation(slip) for slip in selected), Decimal(0)):
        _deny("Native bank selection changed after payroll preflight.")
    expected_base = sum(expected_parties.values(), Decimal(0))
    if expected_base == 0:
        if je is not None:
            _deny("Native payroll created a Bank or Cash Journal Entry for zero payable.")
        return
    if je is None or je.get("voucher_type") not in {"Bank Entry", "Cash Entry"}:
        _deny("Native payroll Bank or Cash Journal Entry is missing.")
    payment_account = str(fresh.get("payment_account") or "")
    account = next((row for row in source["accounts"] if row["name"] == payment_account), None)
    if not account:
        _deny("Payroll payment Account master is missing.")
    account = cast(Mapping[str, Any], account)
    je = cast(Document, je)
    expected_type = "Cash Entry" if account["account_type"] == "Cash" else "Bank Entry"
    if je.get("voucher_type") != expected_type:
        _deny("Native bank voucher type differs from its reviewed payment Account.")
    assert je is not None
    if _payable_candidate(je, fresh, credit=False) != expected_parties:
        _deny("Native bank payable does not match reviewed Salary Slip components.")
    payment_rows = [
        row for row in je.get("accounts") or [] if row.get("account") != fresh.get("payroll_payable_account")
    ]
    if not payment_rows or any(
        row.get("account") != payment_account
        or _money(row.get("debit"))
        or not _money(row.get("credit"))
        or row.get("party_type")
        or row.get("party")
        or row.get("reference_type")
        or row.get("reference_name")
        for row in payment_rows
    ):
        _deny("Native bank credit is not routed through the reviewed payment Account.")
    require_output_review(fresh)


def _gl_effects(
    je: Document,
    payable_account: str,
    payroll_entry: str,
    payment_account: str = "",
    expected_components: Mapping[tuple[str, str, str, str, str], Decimal] | None = None,
) -> tuple[dict[str, Decimal], Decimal]:
    """Use posted GL as the authority, with JE rows checked for its route and balance."""
    rows = _locked_rows(
        "GL Entry",
        {"voucher_type": "Journal Entry", "voucher_no": je.name, "is_cancelled": 0},
        ("name", "account", "cost_center", "party_type", "party", "debit", "credit"),
        "name asc",
    )
    if not rows:
        _deny("Submitted payroll Journal Entry has no active General Ledger effect.")
    debit = sum((_money(row.debit) for row in rows), Decimal(0))
    credit = sum((_money(row.credit) for row in rows), Decimal(0))
    if _currency_round(debit) != _currency_round(credit):
        _deny("Payroll Journal Entry General Ledger is unbalanced.")
    journal_debit = sum((_money(row.get("debit")) for row in je.get("accounts") or []), Decimal(0))
    journal_credit = sum((_money(row.get("credit")) for row in je.get("accounts") or []), Decimal(0))
    if (
        _currency_round(journal_debit) != _currency_round(journal_credit)
        or _currency_round(journal_debit) != _currency_round(debit)
        or _currency_round(journal_credit) != _currency_round(credit)
    ):
        _deny("Payroll Journal Entry accounts are unbalanced.")
    effects: dict[str, Decimal] = {}
    for row in rows:
        if row.account != payable_account:
            continue
        party_type = str(row.party_type or "")
        party = str(row.party or "")
        if (party_type and party_type != "Employee") or (bool(party_type) != bool(party)):
            _deny("Payroll payable party is invalid.")
        key = party if party_type else ""
        effects[key] = effects.get(key, Decimal(0)) + _money(row.credit) - _money(row.debit)
    if not effects:
        _deny("Payroll Journal Entry has no payroll payable effect.")
    journal_effects: dict[str, Decimal] = {}
    for row in je.get("accounts") or []:
        if row.get("reference_type") == "Payroll Entry" and row.get("reference_name") != payroll_entry:
            _deny("Payroll Journal Entry references another Payroll Entry.")
        if row.get("account") != payable_account:
            continue
        if row.get("reference_type") != "Payroll Entry" or row.get("reference_name") != payroll_entry:
            _deny("Payroll payable Journal Entry row lacks its Payroll Entry reference.")
        party_type = str(row.get("party_type") or "")
        party = str(row.get("party") or "")
        key = party if party_type == "Employee" else ""
        journal_effects[key] = (
            journal_effects.get(key, Decimal(0)) + _money(row.get("credit")) - _money(row.get("debit"))
        )
    if {key: _currency_round(value) for key, value in journal_effects.items()} != {
        key: _currency_round(value) for key, value in effects.items()
    }:
        _deny("Payroll payable Journal Entry and General Ledger differ.")
    if expected_components is not None:
        if _candidate_accrual_components(je, payable_account) != expected_components:
            _deny("Submitted accrual component allocation differs from reviewed Salary Slips.")
        expected_gl: dict[str, Decimal] = {}
        for (account, _center, direction, _reference, _party), amount in expected_components.items():
            expected_gl[account] = expected_gl.get(account, Decimal(0)) + (
                amount if direction == "earnings" else -amount
            )
        actual_gl: dict[str, Decimal] = {}
        for row in rows:
            if row.account == payable_account:
                continue
            row_debit, row_credit = _money(row.debit), _money(row.credit)
            account = str(row.account)
            actual_gl[account] = actual_gl.get(account, Decimal(0)) + row_debit - row_credit
        if {key: _currency_round(value) for key, value in actual_gl.items()} != {
            key: _currency_round(value) for key, value in expected_gl.items()
        }:
            _deny("Submitted accrual General Ledger allocation differs from reviewed Salary Slips.")
    if any(key for key in effects):
        ledger_rows = _locked_rows(
            "Payment Ledger Entry",
            {
                "voucher_type": "Journal Entry",
                "voucher_no": je.name,
                "account": payable_account,
                "docstatus": 1,
                "delinked": 0,
            },
            ("name", "company", "account_type", "account", "party_type", "party", "amount"),
            "name asc",
        )
        ledger_effects: dict[str, Decimal] = {}
        for row in ledger_rows:
            if (
                row.company != je.get("company")
                or row.account_type != "Payable"
                or row.account != payable_account
                or row.party_type != "Employee"
                or not row.party
            ):
                _deny("Payroll Payment Ledger route differs from its payable General Ledger.")
            party = str(row.party)
            ledger_effects[party] = ledger_effects.get(party, Decimal(0)) + _money(row.amount)
        if {key: _currency_round(value) for key, value in ledger_effects.items()} != {
            key: _currency_round(value) for key, value in effects.items()
        }:
            _deny("Payroll Payment Ledger amount differs from its payable General Ledger.")
    if payment_account:
        other_rows = [row for row in rows if row.account != payable_account]
        if any(row.account != payment_account or _money(row.debit) for row in other_rows):
            _deny("Payroll Bank or Cash General Ledger uses an unapproved payment account.")
        if not other_rows:
            _deny("Payroll Bank or Cash General Ledger lacks the payment account.")
    return effects, _currency_round(
        sum((_money(row.credit) for row in rows if row.account != payable_account), Decimal(0))
    )


def require_complete_accounting(pe: Document) -> None:
    """Close only when the complete submitted native batch is settled or Withheld."""
    pe = locked_payroll_entry(str(pe.name or ""))
    slips = require_output_review(pe)
    if str(pe.get("status") or "") in {"Queued", "Failed"} or str(pe.get("error_message") or "").strip():
        _deny("Payroll processing is still queued or failed.")
    if any(
        int(slip.docstatus or 0) != 1 or slip.get("status") not in {"Submitted", "Withheld"} for slip in slips
    ):
        _deny("Every reviewed Salary Slip must be submitted before Close.")
    if any(_money(slip.get("net_pay")) < 0 for slip in slips):
        _deny("Payroll has a Salary Slip with negative pay.")
    journals = _active_journals(pe, slips)
    accrual_names = {str(slip.get("journal_entry")) for slip in slips if slip.get("journal_entry")}
    source = output_payload(pe, slips)["sources"]
    for slip in slips:
        if _native_accrual_component_projection(pe, [slip], source) and not slip.get("journal_entry"):
            _deny("Submitted Salary Slip has no native accrual Journal Entry.")
    payable_account = str(pe.get("payroll_payable_account") or "")
    if not payable_account:
        _deny("Payroll payable account is required.")
    buckets: dict[str, dict[str, Decimal]] = {}
    for name, je in journals.items():
        if int(je.docstatus or 0) == 2:
            if name in accrual_names:
                _deny("Payroll Salary Slip references a cancelled accrual Journal Entry.")
            continue
        if int(je.docstatus or 0) != 1 or je.get("company") != pe.get("company"):
            _deny("Payroll Journal Entries must be submitted in the same Company.")
        if name in accrual_names:
            if je.get("voucher_type") != "Journal Entry":
                _deny("Salary Slip accrual Journal Entry type is invalid.")
            kind = "accrual"
        elif je.get("voucher_type") in {"Bank Entry", "Cash Entry"}:
            kind = "payment"
        else:
            _deny("Payroll Journal Entry has an unsupported voucher type.")
        expected_components = (
            _native_accrual_component_projection(
                pe, [slip for slip in slips if str(slip.get("journal_entry") or "") == name], source
            )
            if kind == "accrual"
            else None
        )
        effect, other_credit = _gl_effects(
            je,
            payable_account,
            str(pe.name),
            str(pe.get("payment_account") or "") if kind == "payment" else "",
            expected_components,
        )
        if kind == "payment":
            if other_credit != _currency_round(sum((-value for value in effect.values()), Decimal(0))):
                _deny("Payroll bank credit does not match its payable debit.")
        for party, value in effect.items():
            bucket = buckets.setdefault(party, {"A": Decimal(0), "P": Decimal(0), "H": Decimal(0)})
            bucket["A" if kind == "accrual" else "P"] += value if kind == "accrual" else -value
    release_journals = set()
    withheld_slips: list[Document] = []
    regular_slips: list[Document] = []
    release_slips: dict[str, list[Document]] = {}
    for slip in slips:
        cycle_name = str(slip.get("salary_withholding_cycle") or "")
        release_name = ""
        if cycle_name:
            cycle = frappe.db.get_value(
                "Salary Withholding Cycle",
                cycle_name,
                ["journal_entry"],
                as_dict=True,
                for_update=True,
                wait=False,
            )
            if not cycle:
                _deny("Payroll withholding cycle is missing.")
            release_name = str(cycle.journal_entry or "")
        if slip.get("status") == "Withheld":
            withheld_slips.append(slip)
            if release_name and release_name in journals and int(journals[release_name].docstatus or 0) == 1:
                _deny("Withheld Salary Slip has a submitted release Journal Entry.")
        elif release_name:
            if release_name not in journals or int(journals[release_name].docstatus or 0) != 1:
                _deny("Released Salary Slip lacks a submitted withholding Journal Entry.")
            release_journals.add(release_name)
            release_slips.setdefault(release_name, []).append(slip)
        else:
            regular_slips.append(slip)
    regular_expected = _native_bank_projection(pe, regular_slips, source)
    withheld_expected = _native_bank_projection(pe, withheld_slips, source)
    release_expected: dict[str, Decimal] = {}
    for selected in release_slips.values():
        for party, amount in _native_bank_projection(pe, selected, source).items():
            release_expected[party] = release_expected.get(party, Decimal(0)) + amount
    payment_names = {
        name
        for name, journal in journals.items()
        if name not in accrual_names and int(journal.docstatus or 0) != 2
    }
    ordinary_payment_names = payment_names - release_journals
    if (sum(regular_expected.values(), Decimal(0)) > 0 and len(ordinary_payment_names) != 1) or (
        sum(regular_expected.values(), Decimal(0)) == 0 and ordinary_payment_names
    ):
        _deny("Payroll must have exactly one submitted regular Bank or Cash Journal Entry when payable.")
    for name in release_journals:
        je = journals[name]
        effect, _credit = _gl_effects(je, payable_account, str(pe.name), str(pe.get("payment_account") or ""))
        for party, value in effect.items():
            buckets.setdefault(party, {"A": Decimal(0), "P": Decimal(0), "H": Decimal(0)})["H"] += -value
            buckets[party]["P"] -= -value
    parties = set(buckets) | set(withheld_expected) | set(regular_expected) | set(release_expected)
    for party in parties:
        actual = buckets.get(party, {"A": Decimal(0), "P": Decimal(0), "H": Decimal(0)})
        if _currency_round(actual["P"]) != _currency_round(regular_expected.get(party, Decimal(0))):
            _deny("Payroll regular payment does not match reviewed native Salary Slips.")
        if _currency_round(actual["H"]) != _currency_round(release_expected.get(party, Decimal(0))):
            _deny("Payroll withholding release does not match reviewed native Salary Slips.")
        if _currency_round(actual["A"] - actual["P"] - actual["H"]) != _currency_round(
            withheld_expected.get(party, Decimal(0))
        ):
            _deny("Payroll payable balance does not reconcile to unpaid Withheld salaries.")
