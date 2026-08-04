# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Preserve Customer print defaults while retiring Quotation print snapshots."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

from connect_diagnostics_core.api.erpnext.print_configuration import get_default_configuration
from connect_diagnostics_core.setup import customer

DEFAULT_TEMPLATE = "Default"

RETIRED_QUOTATION_FIELDS = (
    "quotation_print_configuration_section",
    "quotation_form_preset",
    "show_quotation_date",
    "quotation_signatory_type",
    "quotation_sales_representative",
    "quotation_print_configuration_column",
    "quotation_validity_mode",
    "quotation_custom_validity_text",
    "quotation_delivery_terms",
    "quotation_language",
    "quotation_original_count",
    "quotation_copy_count",
)


def execute() -> None:
    """Create the reusable Default Template and retain every Customer's current values."""
    create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True)
    _ensure_default_template()
    _link_existing_customers()
    delete_custom_fields({"Quotation": list(RETIRED_QUOTATION_FIELDS)}, bypass_hooks=True)
    frappe.clear_cache()


def _ensure_default_template() -> None:
    if frappe.db.exists("Print Configuration Template", DEFAULT_TEMPLATE):
        return

    template = frappe.get_doc(
        {
            "doctype": "Print Configuration Template",
            "template_name": DEFAULT_TEMPLATE,
            **get_default_configuration(),
        }
    )
    template.insert(ignore_permissions=True)


def _link_existing_customers() -> None:
    customers = cast(
        list[dict[str, Any]], frappe.get_all("Customer", fields=["name", "print_configuration_template"])
    )
    updates = {
        cast(str, customer_row["name"]): {"print_configuration_template": DEFAULT_TEMPLATE}
        for customer_row in customers
        if not customer_row.get("print_configuration_template")
    }
    if updates:
        frappe.db.bulk_update("Customer", updates, update_modified=False)
