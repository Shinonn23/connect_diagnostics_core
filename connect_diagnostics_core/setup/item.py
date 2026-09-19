"""Custom field / property setter definitions for Item."""

from __future__ import annotations

import json

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

CUSTOM_FIELDS = {
    "Item": [
        {
            "fieldname": "regulatory_tab",
            "label": "Regulatory",
            "fieldtype": "Tab Break",
            "insert_after": "barcodes",
            "is_system_generated": 1,
        },
        {
            "fieldname": "medical_device_regulatory_section",
            "label": "Medical Device Regulatory",
            "fieldtype": "Section Break",
            "insert_after": "regulatory_tab",
            "depends_on": "eval:doc.is_medical_device",
            "is_system_generated": 1,
        },
        {
            "fieldname": "is_medical_device",
            "label": "Is Medical Device",
            "fieldtype": "Check",
            "insert_after": "has_variants",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_registration_requirement",
            "label": "Registration Requirement",
            "fieldtype": "Select",
            "options": "Required\nExempt\nNot Applicable",
            "default": "Not Applicable",
            "insert_after": "medical_device_regulatory_section",
            "is_system_generated": 1,
        },
        {
            "fieldname": "medical_device_category",
            "label": "Medical Device Category",
            "fieldtype": "Select",
            "options": "\nIVD\nNon-IVD\nOther",
            "insert_after": "regulatory_registration_requirement",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_owner",
            "label": "Regulatory Owner",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "medical_device_category",
            "is_system_generated": 1,
        },
        {
            "fieldname": "regulatory_current_section",
            "label": "Current Regulatory Coverage",
            "fieldtype": "Section Break",
            "insert_after": "regulatory_owner",
            "depends_on": "eval:doc.is_medical_device",
            "is_system_generated": 1,
        },
        {
            "fieldname": "current_medical_device_registration",
            "label": "Current Registration",
            "fieldtype": "Link",
            "options": "Medical Device Product Registration",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "regulatory_current_section",
            "is_system_generated": 1,
        },
        {
            "fieldname": "current_newcode",
            "label": "Current NEWCODE",
            "fieldtype": "Data",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "current_medical_device_registration",
            "is_system_generated": 1,
        },
        {
            "fieldname": "current_registration_expiry",
            "label": "Current Registration Expiry",
            "fieldtype": "Date",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "current_newcode",
            "is_system_generated": 1,
        },
        {
            "fieldname": "current_registration_status",
            "label": "Current Registration Status",
            "fieldtype": "Data",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "current_registration_expiry",
            "is_system_generated": 1,
        },
        {
            "fieldname": "opening_tab",
            "label": "Opening",
            "fieldtype": "Tab Break",
            "insert_after": "current_registration_status",
            "is_system_generated": 1,
        },
        {
            "fieldname": "opening_balance_section",
            "label": "Opening Balance",
            "fieldtype": "Section Break",
            "insert_after": "opening_tab",
            "is_system_generated": 1,
        },
        {
            "fieldname": "opening_column_break",
            "fieldtype": "Column Break",
            "insert_after": "opening_balance_section",
            "is_system_generated": 1,
        },
        {
            "fieldname": "shelf_life_section",
            "label": "Shelf Life",
            "fieldtype": "Section Break",
            "insert_after": "serial_no_series",
            "is_system_generated": 1,
        },
        {
            "fieldname": "min_remaining_shelf_life",
            "label": "Min Remaining Shelf Life",
            "fieldtype": "Int",
            "insert_after": "shelf_life_section",
        },
        {
            "fieldname": "max_storage_days",
            "label": "Max Storage Days",
            "fieldtype": "Int",
            "insert_after": "min_remaining_shelf_life",
        },
        {
            "fieldname": "product_group",
            "label": "Product Group",
            "fieldtype": "Link",
            "insert_after": "item_group",
            "options": "Product Group",
        },
        {
            "fieldname": "storage_condition",
            "label": "Storage Condition",
            "fieldtype": "Link",
            "insert_after": "valuation_method",
            "options": "Storage Condition",
        },
        {
            "fieldname": "is_deposit_item",
            "label": "Is Deposit Item",
            "fieldtype": "Check",
            "insert_after": "is_stock_item",
            "depends_on": "eval:!doc.is_stock_item",
            "is_system_generated": 1,
        },
        {
            "fieldname": "section_break_6buh1",
            "label": "Thai Tax",
            "fieldtype": "Section Break",
            "insert_after": "item_tax_section_break",
            "is_system_generated": 1,
        },
        {
            "fieldname": "withholding_tax_type",
            "label": "Withholding Tax Type (Customer)",
            "fieldtype": "Link",
            "insert_after": "section_break_6buh1",
            "description": "Select withholding tax type for service amount withheld when received from customer.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
        {
            "fieldname": "column_break_lhwzh",
            "fieldtype": "Column Break",
            "insert_after": "withholding_tax_type",
            "is_system_generated": 1,
        },
        {
            "fieldname": "withholding_tax_type_pay_supplier",
            "label": "Withholding Tax Type (Supplier)",
            "fieldtype": "Link",
            "insert_after": "column_break_lhwzh",
            "description": "Select withholding tax type for service amount withheld when paying a supplier.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
        {
            "fieldname": "withholding_tax_type_pay_individual",
            "label": "Withholding Tax Type (Individual)",
            "fieldtype": "Link",
            "insert_after": "withholding_tax_type_pay_supplier",
            "description": "Select withholding tax type for service amount withheld when paying an individual.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Item": [
        ("barcodes", "hidden", "0", "Check"),
        ("item_code", "hidden", "0", "Check"),
        ("item_code", "reqd", "1", "Check"),
    ],
}

# Fields relocated via a DocType-level `field_order` Property Setter (the same mechanism
# Customize Form uses). This is required for standard DocFields, which have no per-field
# `insert_after` override at all — but it is *also* required for our own Custom Fields once
# they already exist on a site: CustomField.validate() only recomputes `idx` from
# `insert_after` when the field is newly inserted (frappe.custom.doctype.custom_field
# .custom_field.CustomField.validate), so editing `insert_after` in CUSTOM_FIELDS above is a
# no-op for a field that was created by an earlier version of this file. `ensure_configuration`
# below computes the desired order dynamically from live meta so it stays correct across
# ERPNext upgrades instead of freezing a static field list.
_OPENING_STOCK_FIELDS = ("opening_stock",)
_OPENING_VALUATION_FIELDS = ("valuation_rate", "standard_rate")
# Kept out of the "Serial Nos / Batches" section: that section is specifically about how
# batches/serials are identified and created, while these are general per-item thresholds
# used regardless of whether batching is even enabled (min_remaining_shelf_life drives
# short_expiry_report; max_storage_days is the same kind of warehousing threshold).
_SHELF_LIFE_FIELDS = ("shelf_life_section", "min_remaining_shelf_life", "max_storage_days")
_SHELF_LIFE_ANCHOR = "serial_no_series"


def ensure_configuration() -> None:
    """Move Opening Stock / Valuation Rate / Standard Selling Rate into the Opening tab, and
    the Shelf Life fields to directly follow Serial No Series — the last field of the core
    "Serial Nos / Batches" section, so Shelf Life starts cleanly after it instead of nesting
    inside that section."""
    doctype = "Item"
    meta = frappe.get_meta(doctype)
    live_order = [field.fieldname for field in meta.fields if field.fieldname]
    desired_order = live_order

    opening_required = (
        *_OPENING_STOCK_FIELDS,
        *_OPENING_VALUATION_FIELDS,
        "opening_balance_section",
        "opening_column_break",
    )
    if all(fieldname in desired_order for fieldname in opening_required):
        desired_order = _reordered_for_opening_tab(desired_order)

    shelf_life_required = (*_SHELF_LIFE_FIELDS, _SHELF_LIFE_ANCHOR)
    if all(fieldname in desired_order for fieldname in shelf_life_required):
        desired_order = _relocated_after_anchor(desired_order, _SHELF_LIFE_FIELDS, _SHELF_LIFE_ANCHOR)

    if desired_order == live_order:
        return

    _set_field_order(doctype, desired_order)


def _reordered_for_opening_tab(current_order: list[str]) -> list[str]:
    moved = {*_OPENING_STOCK_FIELDS, *_OPENING_VALUATION_FIELDS}
    remaining = [fieldname for fieldname in current_order if fieldname not in moved]

    section_index = remaining.index("opening_balance_section")
    remaining[section_index + 1 : section_index + 1] = list(_OPENING_STOCK_FIELDS)

    column_index = remaining.index("opening_column_break")
    remaining[column_index + 1 : column_index + 1] = list(_OPENING_VALUATION_FIELDS)

    return remaining


def _relocated_after_anchor(current_order: list[str], fields: tuple[str, ...], anchor: str) -> list[str]:
    moved = set(fields)
    remaining = [fieldname for fieldname in current_order if fieldname not in moved]

    anchor_index = remaining.index(anchor)
    remaining[anchor_index + 1 : anchor_index + 1] = list(fields)

    return remaining


def _set_field_order(doctype: str, order: list[str]) -> None:
    value = json.dumps(order)
    name = frappe.db.get_value("Property Setter", {"doc_type": doctype, "property": "field_order"}, "name")
    if name:
        property_setter = frappe.get_doc("Property Setter", name)
        property_setter.set("value", value)
        property_setter.save(ignore_permissions=True)
        return
    make_property_setter(
        doctype,
        None,
        "field_order",
        value,
        "Small Text",
        for_doctype=True,
        validate_fields_for_doctype=False,
    )
