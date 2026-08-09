# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Introduce the Customer sales document requirement fields.

``use_customer_po`` is renamed to ``source_purchase_order_copy_required``. The
old name claimed the field held the Customer's own purchase order, which it
never did: it asks whether the Customer wants a copy of the Purchase Order *we*
placed with our supplier, to confirm where the goods came from. The old name
also collided with the standard ``Sales Order.po_no`` ("Customer's Purchase
Order"), so it read as the opposite of what it does.

The default also flips from 1 to 0. It was set for every Customer, but the
business register shows only a handful actually ask for the copy, so a blanket
1 would put a requirement on Customers that never had one. Existing values are
carried across unchanged; only Customers that never had a row take the new
default.

``quotation_required`` is new and starts at 0 for everyone; the import patch
sets it for the Customers that require a quotation first.

Idempotent and a no-op on fresh installs, where ``after_install`` creates the
fields under their current names directly.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ensure_new_field,
    _field_def,
    _ident,
)
from connect_diagnostics_core.setup import customer as customer_setup

OLD_FIELD = "use_customer_po"
NEW_FIELD = "source_purchase_order_copy_required"


def execute() -> None:
    """Rename the source Purchase Order flag and add the Quotation requirement."""
    create_custom_fields(customer_setup.CUSTOM_FIELDS, ignore_validate=True)
    _ensure_new_field("Customer", NEW_FIELD, _field_def("Customer", NEW_FIELD))

    if frappe.db.has_column("Customer", OLD_FIELD) and frappe.db.has_column("Customer", NEW_FIELD):
        customer = frappe.qb.DocType("Customer")
        frappe.qb.update(customer).set(customer[_ident(NEW_FIELD)], customer[_ident(OLD_FIELD)]).where(
            customer[_ident(OLD_FIELD)].isnotnull()
        ).run()

    _drop_old("Customer", OLD_FIELD)
    frappe.db.commit()
