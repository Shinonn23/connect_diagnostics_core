# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fold ``Customer.print_date`` into the Sales Order print configuration.

The Sales Order date used to be one Boolean per Customer, read directly by the
Sales Order print format. Sales Order is now a registered print document, so the
date is a per-document ``show_date`` resolved live from the Customer and
overridable per print request, exactly like the other documents.

The registry default for ``show_date`` is 1, so only Customers that had
``print_date = 0`` need a stored override: this patch writes them one
``Print Document Configuration`` row with ``document_key = sales_order`` and
``show_date = 0``. Customers at 1 keep the default with no row. The field and its
column are then dropped.

Idempotent: an existing ``sales_order`` row is not duplicated, and a second run
after the column is gone is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old

FIELD = "print_date"
DOCUMENT_KEY = "sales_order"
DOCUMENT_LABEL = "Sales Order"


def execute() -> None:
    """Store a show_date override for every Customer that hid the Sales Order date."""
    if not frappe.db.has_column("Customer", FIELD):
        return

    customers = cast(
        list[dict[str, Any]],
        frappe.get_all("Customer", filters={FIELD: 0}, fields=["name"]),
    )
    for row in customers:
        _ensure_hidden_date_row(cast(str, row["name"]))

    _drop_old("Customer", FIELD)
    frappe.db.commit()


def _ensure_hidden_date_row(customer: str) -> None:
    existing = frappe.db.exists(
        "Print Document Configuration",
        {
            "parenttype": "Customer",
            "parent": customer,
            "parentfield": "print_documents",
            "document_key": DOCUMENT_KEY,
        },
    )
    if existing:
        return

    frappe.get_doc(
        {
            "doctype": "Print Document Configuration",
            "parenttype": "Customer",
            "parent": customer,
            "parentfield": "print_documents",
            "document_key": DOCUMENT_KEY,
            "document_label": DOCUMENT_LABEL,
            "enabled": 1,
            "show_date": 0,
        }
    ).insert(ignore_permissions=True)
