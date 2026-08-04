# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Set the named Sales Invoice print selections for existing configuration records."""

from __future__ import annotations

from typing import cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import customer as customer_setup

SALES_INVOICE_PRINT_DEFAULTS = {
    "print_tax_invoice_original": 1,
    "print_tax_invoice_customer_copy": 1,
    "print_tax_invoice_accounting_copy": 1,
    "print_tax_invoice_sales_copy": 1,
    "show_tax_invoice_batch_serial": 1,
}


def execute() -> None:
    """Create new fields and initialize existing Customers and Templates."""
    create_custom_fields(customer_setup.CUSTOM_FIELDS, ignore_validate=True)

    customers = cast(list[str], frappe.get_all("Customer", pluck="name"))
    for customer in customers:
        frappe.db.set_value("Customer", customer, SALES_INVOICE_PRINT_DEFAULTS, update_modified=False)

    templates = cast(list[str], frappe.get_all("Print Configuration Template", pluck="name"))
    for template in templates:
        frappe.db.set_value(
            "Print Configuration Template",
            template,
            SALES_INVOICE_PRINT_DEFAULTS,
            update_modified=False,
        )

    frappe.logger(__name__).info(
        "migrate_sales_invoice_print_configuration: updated %s Customers and %s Templates",
        len(customers),
        len(templates),
    )
