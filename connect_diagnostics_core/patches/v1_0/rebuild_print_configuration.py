# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rebuild the print configuration on the print document registry.

Replaces the flat per-document Customer and Template fields with the two child
tables driven by ``connect_diagnostics_core.setup.print_documents``, and moves
the print records into the ``Connect Diagnostics Print`` module. The app is
pre-go-live, so the retired fields are dropped rather than migrated.

Idempotent: repointing a module and deleting a missing Custom Field are both
no-ops on a second run, and seeding never overwrites an existing row.
"""

from __future__ import annotations

from typing import cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields
from frappe.utils.redis_wrapper import ClientCache, RedisWrapper

from connect_diagnostics_core.setup import customer as customer_setup
from connect_diagnostics_core.setup.print_configuration_template import (
    DEFAULT_TEMPLATE,
    seed_registry_rows,
)

PRINT_MODULE = "Connect Diagnostics Print"

PRINT_FORMATS = (
    "Abbreviated Tax Invoice And Receipt",
    "Goods Receipt",
    "Monthly Count Sheet",
    "Purchase Order",
    "Quotation",
    "Receipt",
    "Sales Order",
    "Shipment Box Label",
    "Tax Invoice Delivery Note and Invoice",
    "Withholding Tax Cert CD",
    "Yearly Count Sheet",
)

MOVED_DOCTYPES = (
    "Print Configuration Template",
    "Print Document Configuration",
    "Print Copy Configuration",
    "Print Log",
)

# Retired flat per-document fields. The document types they covered are now rows
# in Print Document Configuration / Print Copy Configuration.
RETIRED_DOCUMENT_PREFIXES = (
    "quotation",
    "tax_invoice",
    "delivery_note",
    "invoice",
    "abbreviated_tax_invoice",
    "receipt",
)

RETIRED_TAX_INVOICE_FIELDS = (
    "print_tax_invoice_original",
    "print_tax_invoice_customer_copy",
    "print_tax_invoice_accounting_copy",
    "print_tax_invoice_sales_copy",
    "show_tax_invoice_batch_serial",
)


def execute() -> None:
    """Move the print records, drop the retired fields, and seed registry rows."""
    _refresh_module_map()
    _repoint_module()
    frappe.reload_doc(PRINT_MODULE, "doctype", "print_document_configuration", force=True)
    frappe.reload_doc(PRINT_MODULE, "doctype", "print_copy_configuration", force=True)
    frappe.reload_doc(PRINT_MODULE, "doctype", "print_configuration_template", force=True)
    frappe.reload_doc(PRINT_MODULE, "doctype", "print_log", force=True)

    create_custom_fields(customer_setup.CUSTOM_FIELDS, ignore_validate=True)
    delete_custom_fields({"Customer": list(retired_customer_fields())}, bypass_hooks=True)

    _seed_templates()
    frappe.clear_cache()


def retired_customer_fields() -> tuple[str, ...]:
    """Return every Customer field the registry replaced."""
    fields: list[str] = []
    for prefix in RETIRED_DOCUMENT_PREFIXES:
        fields.extend(
            (
                f"{prefix}_document_preferences_section",
                f"{prefix}_document_preferences_column",
                f"use_{prefix}",
                f"show_{prefix}_date",
                f"{prefix}_language",
                f"{prefix}_original_count",
                f"{prefix}_copy_count",
            )
        )
    fields.extend(RETIRED_TAX_INVOICE_FIELDS)
    fields.append("document_preferences_column")
    return tuple(fields)


def _refresh_module_map() -> None:
    """Rebuild the module map so the new module resolves during this migration.

    ``frappe.local.module_app`` is built once at process init from the cached app
    module list, and ``frappe.clear_cache()`` does not rebuild it. A migration that
    runs right after ``Connect Diagnostics Print`` was added to ``modules.txt``
    therefore still sees the pre-checkout map, and every ``reload_doc`` below fails
    with ``Module Connect Diagnostics Print not found``.
    """
    cast(RedisWrapper, frappe.cache).delete_value("app_modules")
    cast(ClientCache, frappe.client_cache).delete_value("installed_app_modules")
    frappe.setup_module_map()


def _repoint_module() -> None:
    """Point existing Print Format and DocType records at the new module."""
    for print_format in PRINT_FORMATS:
        if frappe.db.exists("Print Format", print_format):
            frappe.db.set_value("Print Format", print_format, "module", PRINT_MODULE)

    for doctype in MOVED_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.db.set_value("DocType", doctype, "module", PRINT_MODULE)


def _seed_templates() -> None:
    """Give every Template a row for each registered document and copy."""
    templates = cast(list[str], frappe.get_all("Print Configuration Template", pluck="name"))
    if DEFAULT_TEMPLATE not in templates:
        default = frappe.new_doc("Print Configuration Template")
        default.update({"template_name": DEFAULT_TEMPLATE})
        seed_registry_rows(default)
        default.insert(ignore_permissions=True)
        templates.append(DEFAULT_TEMPLATE)

    for name in templates:
        template = frappe.get_doc("Print Configuration Template", name)
        if seed_registry_rows(template):
            template.save(ignore_permissions=True)

    _link_customers_without_template()


def _link_customers_without_template() -> None:
    """Point Customers with no Template at the Default one."""
    customers = cast(
        list[dict[str, str]],
        frappe.get_all(
            "Customer",
            filters={"print_configuration_template": ("in", ("", None))},
            fields=["name"],
        ),
    )
    updates = {row["name"]: {"print_configuration_template": DEFAULT_TEMPLATE} for row in customers}
    if updates:
        frappe.db.bulk_update("Customer", updates, update_modified=False)
