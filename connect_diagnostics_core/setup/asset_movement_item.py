# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Add receiver and immutable receipt evidence to native Asset movement rows."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE = "Asset Movement Item"
HISTORY_INDEX = "asset_parent"
FIELDS = [
    {
        "fieldname": "installation_customer",
        "label": "Installation Customer",
        "fieldtype": "Link",
        "options": "Customer",
        "insert_after": "target_location",
        "no_copy": 1,
        "in_list_view": 1,
        "read_only": 0,
        "hidden": 0,
        "allow_on_submit": 0,
        "reqd": 0,
        "ignore_user_permissions": 0,
        "is_system_generated": 1,
    },
    {
        "fieldname": "installation_previous_customer",
        "label": "Previous Installation Customer",
        "fieldtype": "Link",
        "options": "Customer",
        "insert_after": "installation_customer",
        "no_copy": 1,
        "in_list_view": 0,
        "read_only": 1,
        "hidden": 0,
        "allow_on_submit": 0,
        "reqd": 0,
        "ignore_user_permissions": 1,
        "is_system_generated": 1,
    },
    {
        "fieldname": "receiver_user",
        "label": "Receiver",
        "fieldtype": "Link",
        "options": "User",
        "insert_after": "to_employee",
        "no_copy": 1,
        "in_list_view": 1,
        "read_only": 0,
        "hidden": 0,
        "allow_on_submit": 0,
        "reqd": 0,
        "ignore_user_permissions": 0,
        "is_system_generated": 1,
    },
    {
        "fieldname": "accepted_by",
        "label": "Received by",
        "fieldtype": "Link",
        "options": "User",
        "insert_after": "receiver_user",
        "no_copy": 1,
        "in_list_view": 1,
        "read_only": 1,
        "hidden": 0,
        "allow_on_submit": 1,
        "reqd": 0,
        "ignore_user_permissions": 1,
        "is_system_generated": 1,
    },
    {
        "fieldname": "accepted_at",
        "label": "Received at",
        "fieldtype": "Datetime",
        "options": "",
        "insert_after": "accepted_by",
        "no_copy": 1,
        "in_list_view": 1,
        "read_only": 1,
        "hidden": 0,
        "allow_on_submit": 1,
        "reqd": 0,
        "ignore_user_permissions": 0,
        "is_system_generated": 1,
    },
]


def preflight() -> None:
    """Read every collision before making any metadata changes."""
    if frappe.db.table_exists(DOCTYPE):
        indexes = frappe.db.sql("SHOW INDEX FROM `tabAsset Movement Item`", as_dict=True)
        columns = [
            str(row.Column_name)
            for row in sorted(indexes, key=lambda row: int(row.Seq_in_index))
            if row.Key_name == HISTORY_INDEX
        ]
        if columns and columns != ["asset", "parent"]:
            frappe.throw(_("Existing Asset Movement Item history index requires owner disposition."))
    for field in FIELDS:
        name = str(field["fieldname"])
        if frappe.db.exists("DocField", {"parent": DOCTYPE, "fieldname": name}):
            frappe.throw(_("Asset Movement receipt fields conflict with native fields."))
        existing = frappe.db.get_value(
            "Custom Field", {"dt": DOCTYPE, "fieldname": name}, list(field), as_dict=True
        )
        if existing and any(
            (existing.get(key) or (0 if isinstance(value, int) else "")) != value
            for key, value in field.items()
        ):
            frappe.throw(_("Existing Asset Movement receipt fields require owner disposition."))


def apply_configuration() -> None:
    preflight()
    create_custom_fields({DOCTYPE: FIELDS}, update=True)
    frappe.db.add_index(DOCTYPE, ["asset", "parent"], HISTORY_INDEX)
