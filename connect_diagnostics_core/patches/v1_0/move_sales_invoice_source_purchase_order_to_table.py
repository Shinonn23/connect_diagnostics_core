# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Move the single source Purchase Order fields into the ``source_purchase_orders`` table.

A tax invoice can carry goods from several Purchase Orders, so the single
``source_purchase_order`` link and ``source_purchase_order_file`` attach become one
row in a table with a copy count per row. This patch copies each Sales Invoice's
scalar values into one child row, giving it the Customer's copy count so the
printed output is unchanged, then drops the two Custom Fields and their columns.

Idempotent: an invoice that already has a row is skipped, and a second run after
the columns are gone is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old

OLD_LINK = "source_purchase_order"
OLD_FILE = "source_purchase_order_file"
TABLE_FIELD = "source_purchase_orders"
CHILD_DOCTYPE = "Sales Invoice Source Purchase Order"


def execute() -> None:
    """Copy scalar source Purchase Order values into one child row, then drop them."""
    has_link = frappe.db.has_column("Sales Invoice", OLD_LINK)
    has_file = frappe.db.has_column("Sales Invoice", OLD_FILE)
    if not has_link and not has_file:
        return

    fields = ["name", "customer"]
    if has_link:
        fields.append(OLD_LINK)
    if has_file:
        fields.append(OLD_FILE)

    invoices = cast(list[dict[str, Any]], frappe.get_all("Sales Invoice", fields=fields))
    for row in invoices:
        link = _text(row.get(OLD_LINK))
        file = _text(row.get(OLD_FILE))
        if not link and not file:
            continue
        _ensure_row(cast(str, row["name"]), _text(row.get("customer")), link, file)

    for field in (OLD_LINK, OLD_FILE):
        _drop_old("Sales Invoice", field)
    frappe.db.commit()


def _ensure_row(invoice: str, customer: str, link: str, file: str) -> None:
    existing = frappe.db.exists(
        CHILD_DOCTYPE,
        {"parenttype": "Sales Invoice", "parent": invoice, "parentfield": TABLE_FIELD},
    )
    if existing:
        return

    frappe.get_doc(
        {
            "doctype": CHILD_DOCTYPE,
            "parenttype": "Sales Invoice",
            "parent": invoice,
            "parentfield": TABLE_FIELD,
            "purchase_order": link or None,
            "purchase_order_file": file or None,
            "copies": _customer_copy_count(customer),
        }
    ).insert(ignore_permissions=True)


def _customer_copy_count(customer: str) -> int:
    if not customer:
        return 1
    count = cast(Any, frappe.db.get_value("Customer", customer, "purchase_order_copy_count"))
    return max(int(count or 0), 0) or 1


def _text(value: Any) -> str:
    return str(value or "").strip()
