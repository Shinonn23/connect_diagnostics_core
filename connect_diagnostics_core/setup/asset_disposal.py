# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the Asset Administrator functional role without assigning users."""

from __future__ import annotations

import frappe
from frappe import _

MAKER_ROLE = "Asset Administrator"


def preflight() -> None:
    """Refuse to overwrite a role with a conflicting reserved identity."""
    existing = frappe.db.get_value("Role", MAKER_ROLE, ["name", "disabled"], as_dict=True)
    if existing and existing.disabled:
        frappe.throw(_("Asset Administrator role is disabled and requires owner disposition."))


def apply_configuration() -> None:
    """Create only the functional role; no named user obtains it here."""
    preflight()
    if not frappe.db.exists("Role", MAKER_ROLE):
        role = frappe.get_doc({"doctype": "Role", "role_name": MAKER_ROLE, "desk_access": 1})
        role.insert(ignore_permissions=True)
    # Request/child permissions are code-managed by their DocType JSON. This
    # initializer intentionally does not assign users or broaden Asset rights.
