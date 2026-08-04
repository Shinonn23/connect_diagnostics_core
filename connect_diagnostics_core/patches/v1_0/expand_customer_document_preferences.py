# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Expand legacy Customer print preferences into per-document configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import customer as customer_setup

LEGACY_FIELDS = (
    "name",
    "use_tax_invoice",
    "print_date",
)


def build_preference_values(customer: Mapping[str, Any]) -> dict[str, int | str]:
    """Map legacy values to deterministic per-document preference defaults."""
    use_tax_invoice = int(customer.get("use_tax_invoice") or 0)
    print_date_value = customer.get("print_date")
    show_date = int(print_date_value if print_date_value is not None else 1)
    values: dict[str, int | str] = {
        "use_delivery_note": use_tax_invoice,
        "use_invoice": use_tax_invoice,
        "purchase_order_copy_count": 1,
        "quotation_signatory_type": "Sales Representative",
        "override_quotation_validity_text": 0,
    }
    for prefix, _label, _use_fieldname in customer_setup.DOCUMENT_PREFERENCES:
        values.update(
            {
                f"show_{prefix}_date": show_date,
                f"{prefix}_original_count": 1,
                f"{prefix}_copy_count": 0,
                f"{prefix}_language": "Thai",
            }
        )
    return values


def execute() -> None:
    """Create the new fields and backfill every existing Customer idempotently."""
    create_custom_fields(customer_setup.CUSTOM_FIELDS, ignore_validate=True)
    customers = cast(
        list[dict[str, Any]],
        frappe.get_all("Customer", fields=list(LEGACY_FIELDS)),
    )

    for customer in customers:
        frappe.db.set_value(
            "Customer",
            cast(str, customer["name"]),
            build_preference_values(customer),
            update_modified=False,
        )

    frappe.logger(__name__).info(
        "expand_customer_document_preferences: updated %s customers",
        len(customers),
    )
