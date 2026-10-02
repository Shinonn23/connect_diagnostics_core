# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native row mutexes for foreground stock effects and reconciliation scope edits."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

_SOURCE_DOCTYPES = frozenset(
    {
        "Purchase Receipt",
        "Purchase Invoice",
        "Delivery Note",
        "Sales Invoice",
        "Stock Entry",
        "Subcontracting Receipt",
        "Landed Cost Voucher",
        "Stock Reconciliation",
    }
)


def lock_warehouses(names: Iterable[str]) -> None:
    """Hold sorted actual Warehouse rows until transaction end, without waiting."""
    unique = set(names)
    if any(not isinstance(name, str) or not name for name in unique):
        frappe.throw(_("A stock effect has an unknown Warehouse; retry after correcting its source."))
    for name in sorted(unique):
        if not frappe.db.get_value("Warehouse", name, "name", for_update=True, wait=False):
            frappe.throw(_("Warehouse {0} no longer exists; reload and retry.").format(frappe.bold(name)))


def locked_document(doctype: str, name: str) -> Document:
    """Lock a known parent and its native scope children NOWAIT, then load current values."""
    if doctype not in _SOURCE_DOCTYPES or not name:
        frappe.throw(_("A stock source is missing or unsupported; reload and retry."))
    if not frappe.db.get_value(doctype, name, "name", for_update=True, wait=False):
        frappe.throw(_("A stock source no longer exists; reload and retry."))
    child_names: dict[str, set[str]] = {}
    for field in frappe.get_meta(doctype).get_table_fields():
        child_names[field.fieldname] = set(
            frappe.db.get_values(
                field.options,
                {"parent": name, "parenttype": doctype, "parentfield": field.fieldname},
                "name",
                pluck=True,
                for_update=True,
                wait=False,
                order_by="name",
            )
        )
    current = cast(Document, frappe.get_doc(doctype, name, for_update=True))
    for parentfield, expected in child_names.items():
        actual = {str(row.name) for row in current.get(parentfield, [])}
        if actual != expected:
            frappe.throw(_("A stock source changed while being read; reload and retry."))
    return current


def lock_conflict() -> None:
    frappe.throw(_("Stock scope is being updated by another transaction. Please retry."))
