# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Replace the retired Accounting Department tree with ERPNext Department.

The old HR Department values are deliberately cleared.  Accounting-dimension
values are remapped to the newly-created Department rows before the source
DocType is removed, preserving posted GL history.
"""

from __future__ import annotations

import re
from typing import cast

import frappe
from frappe import _

SOURCE_DOCTYPE = "Accounting Department"
TARGET_DOCTYPE = "Department"
DIMENSION_FIELDNAME = "department"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_ ]+$")


def execute() -> None:
    if not frappe.db.exists("DocType", SOURCE_DOCTYPE):
        return

    source_rows = frappe.get_all(
        SOURCE_DOCTYPE,
        fields=["name", "department_name", "company", "parent_accounting_department", "is_group", "disabled"],
        order_by="lft asc",
    )
    if not source_rows:
        _remove_source_doctype()
        return

    accounting_fields = _accounting_fields()
    _clear_non_accounting_department_links(accounting_fields)
    _delete_departments()
    mapping = _create_departments(source_rows)
    _remap_accounting_fields(accounting_fields, mapping)
    _retarget_dimension()
    _remove_hr_custom_fields()
    _remove_source_doctype()
    frappe.db.commit()


def _accounting_fields() -> set[tuple[str, str]]:
    fields = {
        (row.dt, row.fieldname)
        for row in frappe.get_all(
            "Custom Field",
            filters={"options": SOURCE_DOCTYPE},
            fields=["dt", "fieldname"],
        )
    }
    for doctype in frappe.get_hooks("accounting_dimension_doctypes"):
        if (
            frappe.db.table_exists(doctype)
            and not _is_hr_doctype(doctype)
            and frappe.db.has_column(doctype, DIMENSION_FIELDNAME)
        ):
            fields.add((doctype, DIMENSION_FIELDNAME))
    return fields


def _clear_non_accounting_department_links(accounting_fields: set[tuple[str, str]]) -> None:
    links = frappe.get_all(
        "DocField",
        filters={"fieldtype": "Link", "options": TARGET_DOCTYPE},
        fields=["parent", "fieldname"],
    )
    links.extend(
        frappe.get_all(
            "Custom Field",
            filters={"fieldtype": "Link", "options": TARGET_DOCTYPE},
            fields=["dt as parent", "fieldname"],
        )
    )
    for link in links:
        field = (link.parent, link.fieldname)
        if field == (TARGET_DOCTYPE, "parent_department") or field in accounting_fields:
            continue
        _set_null(link.parent, link.fieldname)


def _delete_departments() -> None:
    for name in frappe.get_all(TARGET_DOCTYPE, pluck="name", order_by="lft desc"):
        frappe.delete_doc(TARGET_DOCTYPE, name, force=True, ignore_permissions=True)


def _create_departments(source_rows: list[frappe._dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    pending = list(source_rows)
    while pending:
        remaining: list[frappe._dict] = []
        for source in pending:
            source_name = cast(str, source.name)
            parent = cast(str | None, source.parent_accounting_department)
            if parent and parent not in mapping:
                remaining.append(source)
                continue
            department_name = cast(str, source.department_name or source.company)
            target = frappe.get_doc(
                {
                    "doctype": TARGET_DOCTYPE,
                    "department_name": department_name,
                    "company": source.company,
                    "parent_department": mapping[parent] if parent else None,
                    "is_group": source.is_group,
                    "disabled": source.disabled,
                }
            )
            target.insert(ignore_permissions=True)
            mapping[source_name] = cast(str, target.name)
        if len(remaining) == len(pending):
            frappe.throw(_("Accounting Department hierarchy contains an unresolved parent."))
        pending = remaining
    return mapping


def _remap_accounting_fields(fields: set[tuple[str, str]], mapping: dict[str, str]) -> None:
    for doctype, fieldname in fields:
        for old_name, new_name in mapping.items():
            _update_value(doctype, fieldname, old_name, new_name)
        if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
            frappe.db.set_value("Custom Field", f"{doctype}-{fieldname}", "options", TARGET_DOCTYPE)


def _retarget_dimension() -> None:
    dimension = frappe.db.exists("Accounting Dimension", {"fieldname": DIMENSION_FIELDNAME})
    if dimension:
        frappe.db.set_value("Accounting Dimension", dimension, "document_type", TARGET_DOCTYPE)


def _remove_hr_custom_fields() -> None:
    for doctype in (TARGET_DOCTYPE, "Employee"):
        name = f"{doctype}-accounting_department"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
        if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, "accounting_department"):
            frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN IF EXISTS `accounting_department`")


def _remove_source_doctype() -> None:
    if frappe.db.exists("DocType", SOURCE_DOCTYPE):
        frappe.delete_doc("DocType", SOURCE_DOCTYPE, force=True, ignore_permissions=True)


def _set_null(doctype: str, fieldname: str) -> None:
    if (
        _safe_identifier(doctype)
        and _safe_identifier(fieldname)
        and frappe.db.table_exists(doctype)
        and frappe.db.has_column(doctype, fieldname)
    ):
        frappe.db.sql(_null_values_sql(doctype, fieldname))


def _update_value(doctype: str, fieldname: str, old_name: str, new_name: str) -> None:
    if (
        _safe_identifier(doctype)
        and _safe_identifier(fieldname)
        and frappe.db.table_exists(doctype)
        and frappe.db.has_column(doctype, fieldname)
    ):
        frappe.db.sql(_remap_values_sql(doctype, fieldname), (new_name, old_name))


def _null_values_sql(doctype: str, fieldname: str) -> str:
    """Build SQL for metadata-validated identifiers only."""
    return "UPDATE `tab" + doctype + "` SET `" + fieldname + "` = NULL WHERE `" + fieldname + "` IS NOT NULL"


def _remap_values_sql(doctype: str, fieldname: str) -> str:
    """Build parameterized SQL for metadata-validated identifiers only."""
    return "UPDATE `tab" + doctype + "` SET `" + fieldname + "` = %s WHERE `" + fieldname + "` = %s"


def _safe_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.fullmatch(value))


def _is_hr_doctype(doctype: str) -> bool:
    module = frappe.db.get_value("DocType", doctype, "module")
    return module in {"HR", "HRMS", "Payroll"}
