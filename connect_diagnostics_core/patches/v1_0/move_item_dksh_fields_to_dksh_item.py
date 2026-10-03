# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Move the five DKSH reference fields off Item into the DKSH Item DocType.

The codes were Custom Fields on Item, which forced every DKSH code to belong to a
CD Item. DKSH also sells stand-alone products with no CD Item, so the codes now
live in their own ``DKSH Item`` master with an optional ``item`` link. This patch
copies each Item that carries any DKSH value into one ``DKSH Item`` record, then
drops the five Custom Fields and their columns.

The record name is the DKSH Item Code, so an Item with DKSH reference values but no
``dksh_item_code`` cannot be represented and is skipped with a logged warning; DEV
has 1,290 Items, all five fields blank, so nothing moves there.

Idempotent: an existing ``DKSH Item`` for the same code is updated, not duplicated,
and a second run after the columns are dropped is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import (
    _drop_old,
    _ident,
)

CODE_FIELD = "dksh_item_code"
DKSH_MODULE = "Connect Diagnostics DKSH"
REFERENCE_FIELDS = (
    "supplier_product_code",
    "mat_group_code",
    "mat_group4_code",
    "material_type_code",
)
DKSH_FIELDS = (CODE_FIELD, *REFERENCE_FIELDS)


def execute() -> None:
    """Copy Item DKSH values into DKSH Item records, then drop the Item fields."""
    present = [field for field in DKSH_FIELDS if frappe.db.has_column("Item", field)]
    if not present:
        return

    frappe.reload_doc(DKSH_MODULE, "doctype", "dksh_item", force=True)

    skipped = 0
    for row in _items_with_dksh_values(present):
        code = _text(row.get(CODE_FIELD))
        if not code:
            if any(_text(row.get(field)) for field in REFERENCE_FIELDS):
                skipped += 1
            continue
        _upsert_dksh_item(cast(str, row["name"]), code, row)

    if skipped:
        frappe.logger(__name__).warning(
            "move_item_dksh_fields_to_dksh_item: skipped %s Item(s) with DKSH reference "
            "values but no DKSH Item Code to name the record.",
            skipped,
        )

    for field in DKSH_FIELDS:
        _drop_old("Item", field)
    frappe.db.commit()


def _items_with_dksh_values(present: list[str]) -> list[dict[str, Any]]:
    item = frappe.qb.DocType("Item")
    query = frappe.qb.from_(item).select(item.name, *[item[_ident(field)] for field in present])
    condition = None
    for field in present:
        column = item[_ident(field)].isnotnull() & (item[_ident(field)] != "")
        condition = column if condition is None else (condition | column)
    if condition is not None:
        query = query.where(condition)
    return cast(list[dict[str, Any]], query.run(as_dict=True))


def _upsert_dksh_item(item_name: str, code: str, row: dict[str, Any]) -> None:
    values = {field: _text(row.get(field)) for field in REFERENCE_FIELDS}
    existing = frappe.db.get_value("DKSH Item", {CODE_FIELD: code}, "name")
    if existing:
        doc = cast(Any, frappe.get_doc("DKSH Item", existing))
        doc.item = item_name
        for field, value in values.items():
            doc.set(field, value)
        doc.save(ignore_permissions=True)
        return
    frappe.get_doc(
        {
            "doctype": "DKSH Item",
            CODE_FIELD: code,
            "item": item_name,
            **values,
        }
    ).insert(ignore_permissions=True)


def _text(value: Any) -> str:
    return str(value or "").strip()
