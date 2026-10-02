# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Expose native Asset.customer for a confirmed installation."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

DOCTYPE = "Asset"
FIELD = "customer"
PROPERTIES = (
    ("allow_on_submit", "1", "Check"),
    ("depends_on", 'eval:doc.asset_owner == "Customer" || doc.docstatus == 1', "Data"),
    ("read_only_depends_on", "eval:doc.docstatus == 1", "Data"),
)


def preflight() -> None:
    native = frappe.db.get_value("DocField", {"parent": DOCTYPE, "fieldname": FIELD}, "name")
    if not native:
        frappe.throw(_("Native Asset customer field is required for installation."))
    for property_name, value, property_type in PROPERTIES:
        existing = frappe.db.get_value(
            "Property Setter",
            {"doc_type": DOCTYPE, "field_name": FIELD, "property": property_name},
            ["value", "property_type"],
            as_dict=True,
        )
        if existing and (str(existing.value) != value or existing.property_type != property_type):
            frappe.throw(_("Existing Asset customer settings require owner disposition."))


def apply_configuration() -> None:
    preflight()
    for property_name, value, property_type in PROPERTIES:
        if not frappe.db.exists(
            "Property Setter", {"doc_type": DOCTYPE, "field_name": FIELD, "property": property_name}
        ):
            make_property_setter(DOCTYPE, FIELD, property_name, value, property_type)
    frappe.clear_cache(doctype=DOCTYPE)
