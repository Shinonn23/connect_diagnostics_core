# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Undo :mod:`move_sales_invoice_source_purchase_order_to_table`.

Recreates the ``source_purchase_order`` link and ``source_purchase_order_file``
attach fields, copies each invoice's first source row back onto them, and removes
the ``source_purchase_orders`` rows. Invoices whose table carried more than one
row keep only the first on the restored scalars — the scalar model cannot hold the
rest — so this is a lossy rollback by nature and logs how many rows were dropped.

Idempotent: recreating an existing field is skipped, and a second run with no rows
is a no-op.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OLD_LINK = "source_purchase_order"
OLD_FILE = "source_purchase_order_file"
TABLE_FIELD = "source_purchase_orders"
CHILD_DOCTYPE = "Sales Invoice Source Purchase Order"

FIELD_DEFS: list[dict[str, Any]] = [
    {
        "fieldname": "source_purchase_order",
        "label": "Source Purchase Order",
        "fieldtype": "Link",
        "options": "Purchase Order",
        "insert_after": "source_purchase_order_section",
        "description": (
            "The Purchase Order we placed with our supplier for these goods. Its "
            "copy prints after the tax invoice."
        ),
    },
    {
        "fieldname": "source_purchase_order_file",
        "label": "Source Purchase Order File",
        "fieldtype": "Attach",
        "insert_after": "source_purchase_order",
        "description": (
            "Use this for a Purchase Order raised before ERPNext, which has no "
            "record to link. An attached file prints separately."
        ),
    },
]


def execute() -> None:
    """Recreate the scalar fields and move each invoice's first source row back."""
    create_custom_fields({"Sales Invoice": FIELD_DEFS}, ignore_validate=True)

    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            CHILD_DOCTYPE,
            filters={"parenttype": "Sales Invoice", "parentfield": TABLE_FIELD},
            fields=["name", "parent", "purchase_order", "purchase_order_file", "idx"],
            order_by="parent asc, idx asc",
        ),
    )

    by_invoice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_invoice[cast(str, row["parent"])].append(row)

    dropped = 0
    for invoice, invoice_rows in by_invoice.items():
        if frappe.db.exists("Sales Invoice", invoice):
            first = invoice_rows[0]
            frappe.db.set_value(
                "Sales Invoice",
                invoice,
                {
                    OLD_LINK: _text(first.get("purchase_order")) or None,
                    OLD_FILE: _text(first.get("purchase_order_file")) or None,
                },
                update_modified=False,
            )
            dropped += len(invoice_rows) - 1
        for row in invoice_rows:
            frappe.delete_doc(CHILD_DOCTYPE, cast(str, row["name"]), ignore_permissions=True, force=True)

    if dropped:
        frappe.logger(__name__).warning(
            "rollback_move_sales_invoice_source_purchase_order_to_table: dropped %s extra "
            "source Purchase Order row(s) the scalar fields cannot hold.",
            dropped,
        )

    frappe.db.commit()


def _text(value: Any) -> str:
    return str(value or "").strip()
