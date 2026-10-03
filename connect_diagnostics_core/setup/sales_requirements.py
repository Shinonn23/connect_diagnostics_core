# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fields and the override Role behind the Customer sales document requirements.

A Customer records what it needs before a sale can proceed: a Quotation issued
first, so a Sales Order carries the reason field used when that gate is
overridden. The gate that enforces it lives in
:mod:`connect_diagnostics_core.api.erpnext.sales_requirements`; this module owns
the field it reads and the Role that may override it.
"""

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document

OVERRIDE_ROLE = "Sales Requirement Override"

OVERRIDE_REASON_DESCRIPTION = (
    "Why this document is allowed to proceed without what the Customer requires. "
    "Only a user with the Sales Requirement Override role may fill this in."
)

CUSTOM_FIELDS = {
    "Sales Order": [
        {
            "fieldname": "requirement_override_reason",
            "label": "Requirement Override Reason",
            "fieldtype": "Small Text",
            "insert_after": "po_date",
            "no_copy": 1,
            "description": OVERRIDE_REASON_DESCRIPTION,
        },
    ],
}


def ensure_configuration() -> None:
    """Create the override Role, keeping an existing one enabled."""
    if frappe.db.exists("Role", OVERRIDE_ROLE):
        role = frappe.get_doc("Role", OVERRIDE_ROLE)
        changed = False
        for fieldname, value in {"disabled": 0, "desk_access": 1, "is_custom": 1}.items():
            if role.get(fieldname) != value:
                role.set(fieldname, value)
                changed = True
        if changed:
            role.save(ignore_permissions=True)
        return

    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": OVERRIDE_ROLE,
            "disabled": 0,
            "desk_access": 1,
            "is_custom": 1,
        }
    ).insert(ignore_permissions=True)
