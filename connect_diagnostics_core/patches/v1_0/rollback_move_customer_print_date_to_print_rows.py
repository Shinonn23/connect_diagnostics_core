# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Undo :mod:`move_customer_print_date_to_print_rows`.

Recreates ``Customer.print_date`` (default 1), sets it to 0 for every Customer
that carries a Sales Order ``show_date = 0`` override row, and removes those
``sales_order`` configuration rows. Sales Order rows with ``show_date = 1`` were
never created by the forward patch and are left untouched.

Idempotent: recreating an existing field is skipped, and a second run with no
matching rows is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELD = "print_date"
DOCUMENT_KEY = "sales_order"

FIELD_DEF: dict[str, Any] = {
    "fieldname": "print_date",
    "label": "Legacy Global Print Date (Current Print Formats)",
    "fieldtype": "Check",
    "insert_after": "purchase_order_copy_count",
    "default": "1",
    "description": (
        "Read directly by the Sales Order Print Format, which has no Customer print configuration of its own."
    ),
}


def execute() -> None:
    """Recreate print_date and move Sales Order show_date overrides back onto it."""
    create_custom_fields({"Customer": [FIELD_DEF]}, ignore_validate=True)

    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Print Document Configuration",
            filters={
                "parenttype": "Customer",
                "parentfield": "print_documents",
                "document_key": DOCUMENT_KEY,
            },
            fields=["name", "parent", "show_date"],
        ),
    )
    for row in rows:
        customer = cast(str, row["parent"])
        if not frappe.db.exists("Customer", customer):
            continue
        if not cast(Any, row.get("show_date")):
            frappe.db.set_value("Customer", customer, FIELD, 0, update_modified=False)
        frappe.delete_doc(
            "Print Document Configuration", cast(str, row["name"]), ignore_permissions=True, force=True
        )

    frappe.db.commit()
