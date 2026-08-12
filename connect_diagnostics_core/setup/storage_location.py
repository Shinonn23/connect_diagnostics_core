# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Register the "Storage Location" ERPNext Inventory Dimension.

The dimension adds a `storage_location` field to every stock transaction child
table plus the Stock Ledger Entry and Stock Closing Balance, so on-hand quantity
can be tracked per rack / zone below the Warehouse. Stock Count reads it to build
per-location count sheets.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

DIMENSION_NAME = "Storage Location"
REFERENCE_DOCTYPE = "Storage Location"
TARGET_FIELDNAME = "storage_location"

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
    if frappe.db.exists("Inventory Dimension", DIMENSION_NAME):
        return
    frappe.get_doc(
        {
            "doctype": "Inventory Dimension",
            "dimension_name": DIMENSION_NAME,
            "reference_document": REFERENCE_DOCTYPE,
            "apply_to_all_doctypes": 1,
        }
    ).insert(ignore_permissions=True)


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
