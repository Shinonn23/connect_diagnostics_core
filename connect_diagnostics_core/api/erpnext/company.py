# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document


def create_default_accounting_department(doc: Document, _method: Any) -> None:
    if frappe.db.get_value("Accounting Department", {"company": doc.name}):
        return

    if not doc.name:
        frappe.throw(_("Company name is required to create default accounting department"))

    company_name = cast(str, doc.name)
    company_abbr: str = frappe.get_cached_value("Company", company_name, "abbr")
    root_name: str = f"{doc.name} - {company_abbr}"

    dept_list = [
        {
            "department_name": doc.name,
            "company": doc.name,
            "is_group": 1,
            "parent_accounting_department": None,
        },
        {
            "department_name": _("Main"),
            "company": doc.name,
            "is_group": 0,
            "parent_accounting_department": root_name,
        },
    ]

    for dept in dept_list:
        dept["doctype"] = "Accounting Department"
        dept_doc = frappe.get_doc(dept)
        dept_doc.flags.ignore_permissions = True
        if dept.get("department_name") == doc.name:
            dept_doc.flags.ignore_mandatory = True
        dept_doc.insert()
