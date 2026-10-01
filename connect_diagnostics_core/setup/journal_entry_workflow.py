# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Least-privilege DocPerm support for the Journal Entry approval workflow."""

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

ROLE_PERMISSIONS = {
    "Accounts User": {
        "read": 1,
        "write": 1,
        "create": 1,
        "submit": 0,
        "cancel": 0,
        "delete": 1,
        "amend": 1,
        "import": 0,
    },
    "Accounts Manager": {
        "read": 1,
        "write": 1,
        "create": 1,
        "submit": 1,
        "cancel": 1,
        "delete": 1,
        "amend": 1,
        "import": 1,
    },
    "C-Level Approver": {
        "read": 1,
        "write": 1,
        "create": 0,
        "submit": 0,
        "cancel": 0,
        "delete": 0,
        "amend": 0,
        "import": 0,
    },
}


def ensure_configuration() -> None:
    """Install the exact Maker, Checker, and Final Approver permission matrix."""
    setup_custom_perms("Journal Entry")
    for role, rights in ROLE_PERMISSIONS.items():
        filters = {
            "parent": "Journal Entry",
            "role": role,
            "permlevel": 0,
            "if_owner": 0,
        }
        name = frappe.db.get_value("Custom DocPerm", filters, "name")
        if name:
            permission = cast(Document, frappe.get_doc("Custom DocPerm", name))
            if any(int(permission.get(right) or 0) != value for right, value in rights.items()):
                permission.update(rights)
                permission.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Journal Entry",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **rights,
            }
        ).insert(ignore_permissions=True)
