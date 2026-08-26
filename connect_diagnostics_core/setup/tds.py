# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Disable ERPNext's core TDS configuration for Thai sites.

Thai withholding tax is configured on Payment Entry through erpnext_thailand's
``Withholding Tax Type``.  ERPNext's Tax Withholding Category flow remains in
the database for historical compatibility, but is hidden and made unavailable
to normal users.
"""

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

ADMINISTRATOR = "Administrator"

TDS_DOCTYPES = (
    "Tax Withholding Category",
    "Tax Withholding Group",
    "Lower Deduction Certificate",
    "Customer",
    "Supplier",
    "Purchase Invoice",
    "Purchase Invoice Item",
    "Sales Invoice",
    "Sales Invoice Item",
    "Payment Entry",
    "Journal Entry",
    "Item",
)

TDS_MASTER_DOCTYPES = (
    "Tax Withholding Category",
    "Tax Withholding Group",
    "Lower Deduction Certificate",
)

TDS_REPORTS = (
    "TDS Computation Summary",
    "Tax Withholding Details",
)

PERMISSION_FIELDS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
)

# This is the source of truth for the core fields that must not be exposed on
# Thai sites.  Layout fields are included so a hidden TDS section/tab cannot be
# left visible with an empty table.
TDS_FIELDS: dict[str, tuple[str, ...]] = {
    "Customer": ("tax_withholding_category", "tax_withholding_group"),
    "Supplier": ("tax_withholding_category", "tax_withholding_group"),
    "Purchase Invoice": (
        "apply_tds",
        "section_tax_withholding_entry",
        "tax_withholding_group",
        "tax_withholding_entries",
        "ignore_tax_withholding_threshold",
        "override_tax_withholding_entries",
    ),
    "Purchase Invoice Item": ("tax_withholding_category", "apply_tds"),
    "Sales Invoice": (
        "apply_tds",
        "section_tax_withholding_entry",
        "tax_withholding_group",
        "tax_withholding_entries",
        "ignore_tax_withholding_threshold",
        "override_tax_withholding_entries",
    ),
    "Sales Invoice Item": ("tax_withholding_category", "apply_tds"),
    "Payment Entry": (
        "tax_withholding_category",
        "apply_tds",
        "section_tax_withholding_entry",
        "tax_withholding_group",
        "ignore_tax_withholding_threshold",
        "tax_withholding_entries",
        "override_tax_withholding_entries",
    ),
    "Journal Entry": (
        "tax_withholding_category",
        "apply_tds",
        "section_tax_withholding_entry",
        "tax_withholding_group",
        "ignore_tax_withholding_threshold",
        "override_tax_withholding_entries",
        "tax_withholding_entries",
        "tax_withholding_tab",
    ),
    "Item": ("purchase_tax_withholding_category", "sales_tax_withholding_category"),
    "Lower Deduction Certificate": ("tax_withholding_category",),
}

TDS_LAYOUT_FIELDS = frozenset(
    {
        "section_tax_withholding_entry",
        "tax_withholding_tab",
    }
)


def get_property_setters() -> dict[str, tuple[tuple[str, str, str, str], ...]]:
    """Return only setters supported by the installed ERPNext metadata."""
    property_setters: dict[str, tuple[tuple[str, str, str, str], ...]] = {}
    for doctype, fieldnames in TDS_FIELDS.items():
        meta = frappe.get_meta(doctype)
        setters: list[tuple[str, str, str, str]] = []
        for fieldname in fieldnames:
            if not meta.has_field(fieldname):
                continue
            setters.append((fieldname, "hidden", "1", "Check"))
            if fieldname not in TDS_LAYOUT_FIELDS:
                setters.append((fieldname, "reqd", "0", "Check"))
        property_setters[doctype] = tuple(setters)
    return property_setters


def apply_configuration() -> None:
    """Apply TDS field visibility and access configuration after app setup."""
    for doctype, setters in get_property_setters().items():
        for fieldname, prop, value, property_type in setters:
            make_property_setter(
                doctype,
                fieldname,
                prop,
                value,
                property_type,
                validate_fields_for_doctype=False,
            )
    ensure_configuration()


def ensure_configuration() -> None:
    """Apply admin-only access to the retained core TDS records and reports."""
    ensure_doctype_permissions()
    ensure_report_permissions()
    for doctype in TDS_MASTER_DOCTYPES:
        frappe.clear_cache(doctype=doctype)
    frappe.clear_cache()


def ensure_doctype_permissions() -> None:
    for doctype in TDS_MASTER_DOCTYPES:
        setup_custom_perms(doctype)
        permission_names = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": doctype},
            pluck="name",
            order_by="creation asc",
        )
        if not permission_names:
            permission_names = [_create_blocking_permission(doctype)]
        for permission_name in permission_names:
            _zero_permission(permission_name)


def ensure_report_permissions() -> None:
    for report_name in TDS_REPORTS:
        if not frappe.db.exists("Report", report_name):
            continue

        custom_role_names = frappe.get_all(
            "Custom Role",
            filters={"report": report_name},
            pluck="name",
            order_by="creation asc",
        )
        if custom_role_names:
            custom_role = cast(Document, frappe.get_doc("Custom Role", custom_role_names[0]))
            for duplicate in custom_role_names[1:]:
                frappe.delete_doc("Custom Role", duplicate, force=True, ignore_permissions=True)
        else:
            custom_role = cast(Document, frappe.get_doc({"doctype": "Custom Role", "report": report_name}))

        desired_ref_doctype = frappe.db.get_value("Report", report_name, "ref_doctype") or ""
        desired_roles = [{"role": ADMINISTRATOR}]
        if custom_role.get("ref_doctype") == desired_ref_doctype and [
            row.get("role") for row in custom_role.get("roles", [])
        ] == [ADMINISTRATOR]:
            continue
        custom_role.set("ref_doctype", desired_ref_doctype)
        custom_role.set("roles", desired_roles)
        if custom_role.is_new():
            custom_role.insert(ignore_permissions=True)
        else:
            custom_role.save(ignore_permissions=True)


def _create_blocking_permission(doctype: str) -> str:
    permission = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "role": "All",
                "permlevel": 0,
                **{fieldname: 0 for fieldname in PERMISSION_FIELDS},
            }
        ),
    )
    permission.insert(ignore_permissions=True)
    return cast(str, permission.name)


def _zero_permission(permission_name: str) -> None:
    permission = cast(Document, frappe.get_doc("Custom DocPerm", permission_name))
    changed = False
    for fieldname in PERMISSION_FIELDS:
        if permission.get(fieldname) != 0:
            permission.set(fieldname, 0)
            changed = True
    if changed:
        permission.save(ignore_permissions=True)


def get_disabled_message() -> str:
    """Return the shared user-facing explanation for the disabled core flow."""
    return _(
        "This site uses Thai withholding tax at Payment Entry (Withholding Tax Type); "
        "ERPNext Tax Withholding Category is disabled."
    )
