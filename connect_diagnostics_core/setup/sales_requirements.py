# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fields and the override Role behind the Customer sales document requirements.

A Customer records what it needs before a sale can proceed: a Quotation issued
first, or a copy of the source Purchase Order attached to its tax invoice. The
gate that enforces those lives in
:mod:`connect_diagnostics_core.api.erpnext.sales_requirements`; this module owns
the fields it reads and the Role that may override it.
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
    "Sales Invoice": [
        {
            "fieldname": "source_purchase_order_section",
            "label": "Source Purchase Order Copy",
            "fieldtype": "Section Break",
            "insert_after": "po_date",
        },
        {
            "fieldname": "source_purchase_orders",
            "label": "Source Purchase Orders",
            "fieldtype": "Table",
            "options": "Sales Invoice Source Purchase Order",
            "insert_after": "source_purchase_order_section",
            "description": (
                "The Purchase Orders we placed with our supplier for these goods. "
                "Their copies print after the tax invoice, one row per Purchase Order "
                "with its own copy count."
            ),
        },
        {
            "fieldname": "requirement_override_reason",
            "label": "Requirement Override Reason",
            "fieldtype": "Small Text",
            "insert_after": "source_purchase_orders",
            "no_copy": 1,
            "description": OVERRIDE_REASON_DESCRIPTION,
        },
    ],
}


def ensure_configuration() -> None:
    """Create the override Role, keeping an existing one enabled."""
    if frappe.db.exists("Role", OVERRIDE_ROLE):
        role = cast(Document, frappe.get_doc("Role", OVERRIDE_ROLE))
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
