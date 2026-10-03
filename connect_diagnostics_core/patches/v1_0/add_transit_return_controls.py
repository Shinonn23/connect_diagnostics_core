# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Add the null-safe links used by native transit, QA, and resolution flows."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.employee import CUSTOM_FIELDS as EMPLOYEE_FIELDS
from connect_diagnostics_core.setup.procure_to_pay import CUSTOM_FIELDS as P2P_FIELDS

FIELDNAMES = {
    "Employee": {"borrow_warehouse"},
    "Company": {
        "borrow_in_transit_warehouse",
        "return_qa_hold_warehouse",
        "return_repair_warehouse",
        "return_qa_hold_location",
        "return_repair_location",
    },
    "Quality Inspection": {
        "return_dispatch_transfer",
        "return_disposition",
        "release_stock_entry",
        "repair_stock_entry",
    },
    "Stock Entry": {"return_dispatch_transfer", "borrowed_item_resolution"},
    "Asset Movement": {"material_request", "return_dispatch_transfer", "borrowed_item_resolution"},
}
ALL_FIELDS = {
    "Employee": EMPLOYEE_FIELDS["Employee"],
    **{doctype: fields for doctype, fields in P2P_FIELDS.items() if doctype != "Employee"},
}
NEW_FIELDS = {
    doctype: [field for field in ALL_FIELDS[doctype] if field["fieldname"] in fieldnames]
    for doctype, fieldnames in FIELDNAMES.items()
}


def execute() -> None:
    create_custom_fields(NEW_FIELDS, update=True, ignore_validate=True)
