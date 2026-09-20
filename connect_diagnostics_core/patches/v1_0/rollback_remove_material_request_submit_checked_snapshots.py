# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Restore the removed MR snapshot schema; record values require backup restore."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.patches.v1_0.remove_material_request_submit_checked_snapshots import (
    REMOVED_FIELDS,
)


def execute() -> None:
    fields = []
    for fieldname, fieldtype, options in REMOVED_FIELDS:
        field = {
            "fieldname": fieldname,
            "label": f"Print Action: {fieldname.replace('_', ' ').title()}",
            "fieldtype": fieldtype,
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        }
        if options:
            field["options"] = options
        fields.append(field)
    create_custom_fields({"Material Request": fields}, update=True, ignore_validate=True)
