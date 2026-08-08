# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reverse ``add_customer_sales_requirements``.

Recreates ``use_customer_po`` with its original definition, copies the values
back from ``source_purchase_order_copy_required``, then removes the fields the
patch introduced. ``quotation_required`` is dropped outright because nothing
held that value before the patch.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

from connect_diagnostics_core.patches.v1_0.add_customer_sales_requirements import NEW_FIELD, OLD_FIELD
from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _ident

INTRODUCED_FIELDS = ("sales_requirements_section", "quotation_required", NEW_FIELD)

ORIGINAL_FIELD = {
    "fieldname": OLD_FIELD,
    "label": "Attach Source Purchase Order Copy",
    "fieldtype": "Check",
    "insert_after": "purchase_order_copy_preferences_section",
    "default": "1",
    "description": (
        "Attach a copy of the source Purchase Order to confirm the origin "
        "of the products sold to this customer."
    ),
}

RESTORED_COPY_COUNT = {
    "fieldname": "purchase_order_copy_count",
    "label": "Copy Count",
    "fieldtype": "Int",
    "insert_after": OLD_FIELD,
    "default": "1",
    "non_negative": 1,
    "depends_on": f"eval:doc.{OLD_FIELD}",
}


def execute() -> None:
    """Restore the original field and remove what the patch added."""
    create_custom_fields({"Customer": [ORIGINAL_FIELD, RESTORED_COPY_COUNT]}, ignore_validate=True)

    if frappe.db.has_column("Customer", NEW_FIELD) and frappe.db.has_column("Customer", OLD_FIELD):
        customer = frappe.qb.DocType("Customer")
        frappe.qb.update(customer).set(customer[_ident(OLD_FIELD)], customer[_ident(NEW_FIELD)]).where(
            customer[_ident(NEW_FIELD)].isnotnull()
        ).run()

    delete_custom_fields({"Customer": list(INTRODUCED_FIELDS)}, bypass_hooks=True)
    frappe.db.commit()
