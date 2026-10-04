# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Add null-safe Demo/Loan fulfillment links and cost snapshot fields."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.procure_to_pay import CUSTOM_FIELDS

FIELDNAMES = {
    "Material Request": frozenset(
        {
            "request_usage",
            "destination_type",
            "responsible_employee",
            "destination_customer",
            "destination_address",
            "asset_location",
            "expected_return_date",
        }
    ),
    "Material Request Item": frozenset(
        {"fulfillment_route", "allocated_asset", "unit_cost_ex_vat", "cost_source"}
    ),
    "Asset Movement": frozenset({"material_request"}),
    "Asset Capitalization": frozenset({"material_request"}),
    "Quality Inspection": frozenset({"material_request"}),
}
NEW_FIELDS = {
    doctype: [field for field in CUSTOM_FIELDS.get(doctype, []) if field["fieldname"] in fieldnames]
    for doctype, fieldnames in FIELDNAMES.items()
}


def execute() -> None:
    create_custom_fields(NEW_FIELDS, update=True, ignore_validate=True)
