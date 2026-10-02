# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Register the "Storage Location" ERPNext Inventory Dimension.

The dimension adds a `storage_location` field to every stock transaction child
table plus the Stock Ledger Entry and Stock Closing Balance, so on-hand quantity
can be tracked per rack / zone below the Warehouse.
"""

from __future__ import annotations

import frappe
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_documents
from frappe import _
from frappe.model.document import Document

DIMENSION_NAME = "Storage Location"
REFERENCE_DOCTYPE = "Storage Location"
TARGET_FIELDNAME = "storage_location"
_GENERATED_FIELDNAMES = (
    "storage_location",
    "to_storage_location",
    "from_storage_location",
    "rejected_storage_location",
)
_IGNORED_INVENTORY_DOCTYPES = frozenset(
    {"Serial and Batch Bundle", "Serial and Batch Entry", "Pick List Item", "Maintenance Visit Purpose"}
)
_TO_LOCATION_DOCTYPES = frozenset({"Stock Entry Detail", "Sales Invoice Item", "Delivery Note Item"})
_FROM_LOCATION_DOCTYPES = frozenset({"Purchase Invoice Item", "Purchase Receipt Item"})

# ERPNext's Inventory Dimension always inserts its generated fields in a collapsible
# section at the very bottom of each form. We relocate every generated field next to
# the warehouse field it qualifies. Each entry maps a generated fieldname to the
# candidate warehouse fieldnames to anchor it after, in order of preference.
_FIELD_WAREHOUSE_ANCHORS = {
    "storage_location": ("warehouse", "s_warehouse", "t_warehouse", "set_warehouse"),
    "to_storage_location": ("t_warehouse", "warehouse"),
    "from_storage_location": ("warehouse", "from_warehouse"),
    "rejected_storage_location": ("rejected_warehouse", "warehouse"),
}


def ensure_configuration() -> None:
    """Create the Storage Location inventory dimension idempotently, then relocate
    its generated fields next to the warehouse field on every affected doctype.
    """
    _ensure_dimension()
    reposition_dimension_fields()


def _ensure_dimension() -> None:
    """Create the dimension once.

    Skips when it already exists: re-saving an Inventory Dimension that has stock
    ledger entries raises DoNotChangeError, and its custom-field creation is a
    side effect of insert, so a plain existence guard is both safe and sufficient.
    """
    existing_fields = _check_field_collisions()
    existing = frappe.db.get_value(
        "Inventory Dimension",
        DIMENSION_NAME,
        [
            "dimension_name",
            "reference_document",
            "source_fieldname",
            "target_fieldname",
            "apply_to_all_doctypes",
            "validate_negative_stock",
        ],
        as_dict=True,
    )
    if existing:
        if (
            existing.dimension_name != DIMENSION_NAME
            or existing.reference_document != REFERENCE_DOCTYPE
            or existing.source_fieldname != TARGET_FIELDNAME
            or existing.target_fieldname != TARGET_FIELDNAME
            or not existing.apply_to_all_doctypes
            or not existing.validate_negative_stock
        ):
            frappe.throw(_("Existing Storage Location Inventory Dimension has incompatible settings."))
        if not _expected_native_fields().issubset(existing_fields):
            frappe.throw(_("Existing Storage Location Inventory Dimension is missing native stock fields."))
        return
    if existing_fields:
        frappe.throw(_("Storage Location fields exist without their Inventory Dimension."))
    frappe.get_doc(
        {
            "doctype": "Inventory Dimension",
            "dimension_name": DIMENSION_NAME,
            "reference_document": REFERENCE_DOCTYPE,
            "apply_to_all_doctypes": 1,
            "validate_negative_stock": 1,
        }
    ).insert(ignore_permissions=True)


def _expected_native_fields() -> set[tuple[str, str]]:
    """Mirror ERPNext's generated Link fields for the installed inventory documents."""
    expected = {
        ("Stock Ledger Entry", TARGET_FIELDNAME),
        ("Stock Closing Balance", TARGET_FIELDNAME),
    }
    for (doctype,) in get_inventory_documents():
        if doctype in _IGNORED_INVENTORY_DOCTYPES:
            continue
        expected.add((doctype, TARGET_FIELDNAME))
        if doctype in _TO_LOCATION_DOCTYPES:
            expected.add((doctype, f"to_{TARGET_FIELDNAME}"))
        elif doctype in _FROM_LOCATION_DOCTYPES:
            expected.add((doctype, f"from_{TARGET_FIELDNAME}"))
            expected.add((doctype, f"rejected_{TARGET_FIELDNAME}"))
    return expected


def _check_field_collisions() -> set[tuple[str, str]]:
    existing_fields: set[tuple[str, str]] = set()
    for field_doctype in ("DocField", "Custom Field"):
        for field in frappe.get_all(
            field_doctype,
            filters={"fieldname": ("in", _GENERATED_FIELDNAMES)},
            fields=["parent" if field_doctype == "DocField" else "dt", "fieldname", "fieldtype", "options"],
        ):
            if field.fieldtype != "Link" or field.options != REFERENCE_DOCTYPE:
                frappe.throw(
                    _("Storage Location dimension field {0} has incompatible type or reference.").format(
                        field.fieldname
                    )
                )
            existing_fields.add((str(field.get("parent") or field.get("dt")), str(field.fieldname)))
    return existing_fields


def reposition_dimension_fields() -> None:
    """Move each generated Storage Location field to sit right after its warehouse.

    Idempotent: a field is only saved when its `insert_after` needs changing. Field
    ordering is driven by `insert_after` at meta build time, so updating it (and the
    cache clear that Custom Field.on_update triggers) is sufficient to reposition.
    """
    generated_fields = frappe.get_all(
        "Custom Field",
        filters={
            "fieldname": ("in", tuple(_FIELD_WAREHOUSE_ANCHORS)),
            "options": REFERENCE_DOCTYPE,
        },
        fields=["name", "dt", "fieldname", "insert_after"],
    )
    for row in generated_fields:
        anchor = _resolve_warehouse_field(row.dt, _FIELD_WAREHOUSE_ANCHORS[row.fieldname])
        if not anchor or row.insert_after == anchor:
            continue
        field = frappe.get_doc("Custom Field", row.name)
        assert isinstance(field, Document)
        field.insert_after = anchor
        field.save(ignore_permissions=True)


def _resolve_warehouse_field(doctype: str, candidates: tuple[str, ...]) -> str | None:
    meta = frappe.get_meta(doctype)
    for candidate in candidates:
        if meta.get_field(candidate):
            return candidate
    return None
