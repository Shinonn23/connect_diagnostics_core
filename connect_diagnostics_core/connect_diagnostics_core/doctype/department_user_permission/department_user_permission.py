# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DepartmentUserPermission(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_core.doctype.department_user_permission_user.department_user_permission_user import (
            DepartmentUserPermissionUser,
        )

        allow: DF.Link
        applicable_for: DF.Link | None
        apply_to_all_doctypes: DF.Check
        department: DF.Link
        for_value: DF.DynamicLink
        hide_descendants: DF.Check
        is_default: DF.Check
        users: DF.Table[DepartmentUserPermissionUser]
    # end: auto-generated types
    pass


@frappe.whitelist()
def get_employees_in_department(department: str) -> list[dict]:
    if not department:
        return []
    # Fetch active employees with a valid user_id in the selected department
    employees = frappe.get_all(
        "Employee",
        filters={"department": department, "status": "Active", "user_id": ["is", "set"]},
        fields=["user_id", "name", "employee_name"],
    )
    return employees


@frappe.whitelist()
def apply_permissions(docname: str) -> dict[str, int]:
    doc = frappe.get_doc("Department User Permission", docname)
    if not doc.users:
        frappe.throw(_("No users found in the table to apply permissions to."))

    applied_count = 0
    updated_count = 0

    for u in doc.users:
        if not u.apply:
            continue

        # Check if the user permission already exists
        existing_name = frappe.db.get_value(
            "User Permission",
            {
                "user": u.user,
                "allow": doc.allow,
                "for_value": doc.for_value,
                "applicable_for": doc.applicable_for or None,
            },
        )

        if existing_name:
            # Update existing permission
            up = frappe.get_doc("User Permission", existing_name)
            up.is_default = doc.is_default
            up.apply_to_all_doctypes = doc.apply_to_all_doctypes
            up.hide_descendants = doc.hide_descendants
            up.save(ignore_permissions=True)
            updated_count += 1
        else:
            # Create new user permission
            up = frappe.new_doc("User Permission")
            up.update(
                {
                    "user": u.user,
                    "allow": doc.allow,
                    "for_value": doc.for_value,
                    "is_default": doc.is_default,
                    "applicable_for": doc.applicable_for or None,
                    "apply_to_all_doctypes": doc.apply_to_all_doctypes,
                    "hide_descendants": doc.hide_descendants,
                }
            )
            up.insert(ignore_permissions=True)
            applied_count += 1

    return {"applied": applied_count, "updated": updated_count}


@frappe.whitelist()
def remove_permissions(docname: str) -> dict[str, int]:
    doc = frappe.get_doc("Department User Permission", docname)
    if not doc.users:
        frappe.throw(_("No users found in the table to remove permissions from."))

    removed_count = 0

    for u in doc.users:
        if not u.apply:
            continue

        # Get matching user permissions
        existing_permissions = frappe.get_all(
            "User Permission",
            filters={
                "user": u.user,
                "allow": doc.allow,
                "for_value": doc.for_value,
                "applicable_for": doc.applicable_for or None,
            },
            pluck="name",
        )

        for name in existing_permissions:
            frappe.delete_doc("User Permission", name, ignore_permissions=True)
            removed_count += 1

    return {"removed": removed_count}
