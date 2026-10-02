# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Ensure the WF-15 scope-owner roles exist without assigning them to users."""

from __future__ import annotations

import frappe
from frappe import _

OWNER_ROLES = ("Company Owner", "Department Head", "Warehouse Manager")


def ensure_configuration() -> None:
    """Create missing owner roles and fail closed on disabled reserved roles."""
    for role_name in OWNER_ROLES:
        existing = frappe.db.get_value("Role", role_name, ["name", "disabled"], as_dict=True)
        if existing:
            if existing.disabled:
                frappe.throw(
                    _("The reserved role {0} is disabled and requires owner disposition.").format(role_name)
                )
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)
