# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.model.document import Document

AUTHORIZED_SIGNATORY_DOCTYPE = "Quotation Authorized Signatory"
AUTHORIZED_SIGNATORY_ROLE = "Sales Manager"
BORROW_CONFIGURATION_FIELDS = (
    "borrow_in_transit_warehouse",
    "return_qa_hold_warehouse",
    "return_repair_warehouse",
    "return_qa_hold_location",
    "return_repair_location",
)


def validate_borrow_configuration(doc: Document, _method: str | None = None) -> None:
    """Validate the Company-owned warehouses and Locations used by returns."""
    warehouses = (
        "borrow_in_transit_warehouse",
        "return_qa_hold_warehouse",
        "return_repair_warehouse",
    )
    for fieldname in warehouses:
        warehouse = doc.get(fieldname)
        if warehouse:
            _validate_leaf_warehouse(warehouse, cast(str, doc.name), fieldname)

    for fieldname in ("return_qa_hold_location", "return_repair_location"):
        location = doc.get(fieldname)
        if location:
            location_group = frappe.db.get_value("Location", location, "is_group")
            if location_group is None or location_group:
                frappe.throw(_("{0} must be a leaf Location.").format(_field_label(fieldname)))


def validate_returnable_configuration(company: str, responsible_employee: str) -> None:
    """Require all return-loop masters before a returnable MR is approved."""
    company_doc = frappe.db.get_value("Company", company, list(BORROW_CONFIGURATION_FIELDS), as_dict=True)
    if not company_doc:
        frappe.throw(_("Company {0} does not exist.").format(company))
    for fieldname in BORROW_CONFIGURATION_FIELDS:
        if not company_doc.get(fieldname):
            frappe.throw(
                _("{0} is required for returnable Material Requests.").format(_field_label(fieldname))
            )
    for fieldname in (
        "borrow_in_transit_warehouse",
        "return_qa_hold_warehouse",
        "return_repair_warehouse",
    ):
        _validate_leaf_warehouse(cast(str, company_doc.get(fieldname)), company, fieldname)
    for fieldname in ("return_qa_hold_location", "return_repair_location"):
        location_group = frappe.db.get_value("Location", company_doc.get(fieldname), "is_group")
        if location_group is None or location_group:
            frappe.throw(_("{0} must be a leaf Location.").format(_field_label(fieldname)))

    employee = frappe.db.get_value(
        "Employee", responsible_employee, ["status", "company", "borrow_warehouse"], as_dict=True
    )
    if not employee or employee.status != "Active" or employee.company != company:
        frappe.throw(_("Responsible Employee must be active and belong to the Material Request company."))
    _validate_leaf_warehouse(employee.borrow_warehouse, company, "borrow_warehouse")


def _validate_leaf_warehouse(warehouse: str | None, company: str, fieldname: str) -> None:
    if not warehouse:
        frappe.throw(_("{0} is required for returnable Material Requests.").format(_field_label(fieldname)))
    details = frappe.db.get_value("Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True)
    if not details or details.company != company:
        frappe.throw(_("{0} must belong to Company {1}.").format(_field_label(fieldname), company))
    if details.disabled or details.is_group:
        frappe.throw(_("{0} must be an active leaf Warehouse.").format(_field_label(fieldname)))


def _field_label(fieldname: str) -> str:
    return fieldname.replace("_", " ").title()


def validate_quotation_authorized_signatories(doc: Document, _method: str | None = None) -> None:
    """Validate every Employee listed as a Company's quotation signatory.

    The table is deliberately a Company-owned allow-list.  Validation is done
    on the parent so duplicate rows (including duplicates in a not-yet-saved
    grid) are caught before any child row reaches the database.
    """
    rows = cast(Iterable[Document], doc.get("quotation_authorized_signatories") or ())
    seen: set[str] = set()
    for row in rows:
        employee = _text(row.get("employee"))
        if not employee:
            continue
        if employee in seen:
            frappe.throw(
                _("Employee {0} is listed more than once as an authorized signatory.").format(employee)
            )
        seen.add(employee)
        validate_quotation_authorized_signatory_employee(employee, cast(str, doc.name))


def validate_quotation_authorized_signatory_employee(employee: str, company: str) -> None:
    """Ensure one Employee is eligible for a Company's signatory allow-list."""
    employee = _text(employee)
    company = _text(company)
    if not employee or not company:
        frappe.throw(_("An Employee and Company are required for an authorized signatory."))

    details_value = frappe.db.get_value(
        "Employee",
        employee,
        ["company", "status", "user_id"],
        as_dict=True,
    )
    if not details_value:
        frappe.throw(_("Employee {0} does not exist.").format(employee))
    details = cast(dict[str, Any], details_value)
    if _text(details.get("status")) != "Active":
        frappe.throw(_("Employee {0} must be Active to sign a quotation.").format(employee))
    if _text(details.get("company")) != company:
        frappe.throw(_("Employee {0} must belong to Company {1}.").format(employee, company))

    user_id = _text(details.get("user_id"))
    if not user_id or not frappe.db.exists(
        "Has Role", {"parent": user_id, "parenttype": "User", "role": AUTHORIZED_SIGNATORY_ROLE}
    ):
        frappe.throw(_("Employee {0} must have the {1} role.").format(employee, AUTHORIZED_SIGNATORY_ROLE))


def get_quotation_authorized_signatories(company: str) -> list[dict[str, Any]]:
    """Return valid Company signatories, retaining rows without an E-Signature.

    The caller uses ``ready`` to render unavailable names in the sidebar while
    preventing their selection.  Duplicate rows are de-duplicated defensively
    for legacy data; normal saves reject them in
    :func:`validate_quotation_authorized_signatories`.
    """
    company = _text(company)
    if not company:
        return []

    rows = frappe.get_all(
        AUTHORIZED_SIGNATORY_DOCTYPE,
        filters={"parent": company, "parenttype": "Company"},
        fields=["employee", "idx"],
        order_by="idx asc, name asc",
        ignore_permissions=True,
    )
    employee_names = []
    seen: set[str] = set()
    for row in rows:
        employee = _text(row.get("employee"))
        if employee and employee not in seen:
            seen.add(employee)
            employee_names.append(employee)
    if not employee_names:
        return []

    employees = frappe.get_all(
        "Employee",
        filters={"name": ["in", employee_names]},
        fields=["name", "employee_name", "company", "status", "user_id", "quotation_signature"],
        ignore_permissions=True,
    )
    by_name = {_text(row.get("name")): row for row in employees if _text(row.get("name"))}
    user_ids = [
        _text(row.get("user_id"))
        for row in employees
        if _text(row.get("user_id"))
        and _text(row.get("company")) == company
        and _text(row.get("status")) == "Active"
    ]
    role_users = {
        _text(parent)
        for parent in frappe.db.sql(
            """
            select parent
            from `tabHas Role`
            where parenttype = 'User'
              and role = %s
              and parent in %s
            """,
            (AUTHORIZED_SIGNATORY_ROLE, tuple(user_ids) or ("",)),
            pluck="parent",
        )
    }

    result: list[dict[str, Any]] = []
    for employee_name in employee_names:
        row = by_name.get(employee_name)
        if not row:
            continue
        if (
            _text(row.get("company")) != company
            or _text(row.get("status")) != "Active"
            or _text(row.get("user_id")) not in role_users
        ):
            continue
        signature = _text(row.get("quotation_signature"))
        result.append(
            {
                "employee": employee_name,
                "name": _text(row.get("employee_name")),
                "ready": bool(signature),
                "reason": "" if signature else _("E-Signature is not configured."),
            }
        )
    return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def authorized_signatory_employee_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Link query for the Company authorized-signatory child table."""
    company = _text((filters or {}).get("company"))
    if not company:
        return []
    if not frappe.db.exists("Company", company):
        return []
    frappe.has_permission("Company", "read", company, throw=True)
    query = (
        "select `tabEmployee`.name, `tabEmployee`.employee_name "
        "from `tabEmployee` "
        "where `tabEmployee`.status = 'Active' "
        "and `tabEmployee`.company = %(company)s "
        "and (`tabEmployee`.name like %(txt)s or `tabEmployee`.employee_name like %(txt)s) "
        "and exists (select 1 from `tabHas Role` "
        "where `tabHas Role`.parent = `tabEmployee`.user_id "
        "and `tabHas Role`.parenttype = 'User' "
        "and `tabHas Role`.role = %(role)s) "
        + get_match_cond("Employee")
        + " order by `tabEmployee`.employee_name limit %(page_len)s offset %(start)s"
    )
    return cast(
        list[tuple[str, str]],
        frappe.db.sql(
            query,
            {
                "company": company,
                "role": AUTHORIZED_SIGNATORY_ROLE,
                "txt": "%" + txt + "%",
                "page_len": page_len,
                "start": start,
            },
        ),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()
