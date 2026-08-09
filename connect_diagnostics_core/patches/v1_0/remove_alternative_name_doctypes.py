# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire the Alternative Names feature on Customer, Item, and Supplier.

Deletes the ``alternative_names`` Table Custom Field on each parent doctype,
then force-deletes the three child DocTypes (and their tables, dropping any
existing alternative-name rows). Idempotent: a no-op once already removed.
"""

import frappe

CUSTOM_FIELDS = (
    "Customer-alternative_names",
    "Item-alternative_names",
    "Supplier-alternative_names",
)

CHILD_DOCTYPES = (
    "Customer Alternative Name",
    "Item Alternative Name",
    "Supplier Alternative Name",
)


def execute():
    for custom_field in CUSTOM_FIELDS:
        if frappe.db.exists("Custom Field", custom_field):
            frappe.delete_doc("Custom Field", custom_field, force=True, ignore_missing=True)

    for doctype in CHILD_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)

    frappe.db.commit()
