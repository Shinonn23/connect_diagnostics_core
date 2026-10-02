# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed reservation field on native Repost Item Valuation."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE = "Repost Item Valuation"
FIELD = {
    "fieldname": "reservation_warehouses",
    "label": "Reserved Warehouses",
    "fieldtype": "Table",
    "options": "Repost Warehouse Reservation",
    "insert_after": "recreate_stock_ledgers",
    "hidden": 1,
    "read_only": 1,
    "no_copy": 1,
    "is_system_generated": 1,
}


def preflight() -> None:
    if frappe.db.exists("DocField", {"parent": DOCTYPE, "fieldname": FIELD["fieldname"]}):
        frappe.throw(_("Repost Warehouse reservation field conflicts with a native field."))
    existing = frappe.db.get_value(
        "Custom Field", {"dt": DOCTYPE, "fieldname": FIELD["fieldname"]}, list(FIELD), as_dict=True
    )
    if existing and any(
        (existing.get(key) or (0 if isinstance(value, int) else "")) != value for key, value in FIELD.items()
    ):
        frappe.throw(_("Existing Repost Warehouse reservation field requires owner disposition."))


def ensure_configuration() -> None:
    preflight()
    create_custom_fields({DOCTYPE: [FIELD]}, update=True)
