# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Immutable regulatory snapshots and controlled-override links on transactions."""

from __future__ import annotations

TRANSACTION_DOCTYPES = (
    "Purchase Order",
    "Purchase Receipt",
    "Stock Entry",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
)
ITEM_DOCTYPES = (
    "Purchase Order Item",
    "Purchase Receipt Item",
    "Stock Entry Detail",
    "Sales Order Item",
    "Delivery Note Item",
    "Sales Invoice Item",
)


def _snapshot_fields() -> list[dict[str, object]]:
    return [
        {
            "fieldname": "regulatory_snapshot_section",
            "label": "Medical Device Regulatory Snapshot",
            "fieldtype": "Section Break",
            "insert_after": "item_code",
            "collapsible": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_registration",
            "label": "Registration",
            "fieldtype": "Link",
            "options": "Medical Device Product Registration",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_snapshot_section",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_newcode",
            "label": "FDA NEWCODE",
            "fieldtype": "Data",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_registration",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_identifier",
            "label": "Identifier",
            "fieldtype": "Data",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_newcode",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_manufacturer",
            "label": "Regulatory Manufacturer",
            "fieldtype": "Link",
            "options": "Manufacturer",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_identifier",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_manufacturer_country",
            "label": "Regulatory Manufacturer Country",
            "fieldtype": "Link",
            "options": "Country",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_manufacturer",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_batch_no",
            "label": "Regulatory Batch No.",
            "fieldtype": "Data",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_manufacturer_country",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_serial_no",
            "label": "Regulatory Serial No.",
            "fieldtype": "Text",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_batch_no",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_product_expiry_date",
            "label": "Product Expiry Date",
            "fieldtype": "Date",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_serial_no",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_reporting_uom",
            "label": "Regulatory Reporting UOM",
            "fieldtype": "Link",
            "options": "UOM",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_product_expiry_date",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_reporting_qty",
            "label": "Regulatory Reporting Quantity",
            "fieldtype": "Float",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_reporting_uom",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_override",
            "label": "Regulatory Override",
            "fieldtype": "Link",
            "options": "Medical Device Regulatory Override",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_reporting_qty",
            "is_system_generated": 1,
        },
    ]


CUSTOM_FIELDS: dict[str, list[dict[str, object]]] = {doctype: _snapshot_fields() for doctype in ITEM_DOCTYPES}
CUSTOM_FIELDS.update(
    {
        doctype: [
            {
                "fieldname": "medical_device_regulatory_override",
                "label": "Medical Device Regulatory Override",
                "fieldtype": "Link",
                "options": "Medical Device Regulatory Override",
                "insert_after": "items",
                "no_copy": 1,
                "is_system_generated": 1,
            }
        ]
        for doctype in TRANSACTION_DOCTYPES
    }
)
