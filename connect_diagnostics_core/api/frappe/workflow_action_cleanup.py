# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Delete source-bound Workflow Actions through Frappe's native child cascade."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_SOURCE_DOCTYPES = frozenset(
    {
        "Asset Movement",
        "Journal Entry",
        "Payment Entry",
        "Payroll Entry",
        "Purchase Invoice",
        "Purchase Order",
        "Sales Invoice",
        "Sales Order",
        "Stock Entry",
        "Stock Reconciliation",
    }
)


def delete_linked_actions(doc: Document, method: str) -> None:
    """Remove only actions for an authorized source delete, before native wildcard cleanup."""
    if method != "on_trash" or doc.doctype not in _SOURCE_DOCTYPES or not doc.name:
        frappe.throw(_("Workflow Action cleanup requires a supported source deletion."))

    action_names = frappe.db.get_values(
        "Workflow Action",
        {"reference_doctype": doc.doctype, "reference_name": doc.name},
        "name",
        pluck=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    for action_name in sorted(set(action_names)):
        frappe.delete_doc("Workflow Action", action_name, ignore_permissions=True, delete_permanently=True)
