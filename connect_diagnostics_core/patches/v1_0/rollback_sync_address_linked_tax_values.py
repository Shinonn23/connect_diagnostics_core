# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for sync_address_linked_tax_values.

Best-effort: recomputes the same linked-source selection as the forward patch
and clears Address.tax_id/branch_code back to empty wherever the current value
still matches what the forward patch would have set. Lossy — the prior value
(if any) was never backed up, so this cannot distinguish "set by the
migration" from "already matched the linked source before the migration ran".
Idempotent.
"""

from __future__ import annotations

from typing import Any

import frappe

from connect_diagnostics_core.patches.v1_0.sync_address_linked_tax_values import (
    ADDRESS_TAX_FIELDS,
    AddressTaxSource,
    _get_address_values,
    _get_existing_fields,
    _get_linked_address_tax_sources,
    _get_value,
    _select_address_tax_sources,
)


def execute() -> None:
    address_fields = _get_existing_fields("Address", ADDRESS_TAX_FIELDS)
    if "tax_id" not in address_fields:
        return

    sources = _get_linked_address_tax_sources(include_branch="branch_code" in address_fields)
    selected_sources = _select_address_tax_sources(sources)
    if not selected_sources:
        return

    address_values = _get_address_values(tuple(selected_sources), address_fields)
    cleared = 0
    for address, source in selected_sources.items():
        current_values = address_values.get(address)
        if not current_values:
            continue

        values_to_clear = _get_address_values_to_clear(current_values, source, address_fields)
        if not values_to_clear:
            continue

        frappe.db.set_value("Address", address, values_to_clear, update_modified=False)
        cleared += 1

    if cleared:
        frappe.db.commit()


def _get_address_values_to_clear(
    address_values: Any,
    source: AddressTaxSource,
    address_fields: tuple[str, ...],
) -> dict[str, str]:
    values: dict[str, str] = {}

    if source.tax_id and _get_value(address_values, "tax_id") == source.tax_id:
        values["tax_id"] = ""
    if (
        "branch_code" in address_fields
        and source.branch_code
        and _get_value(address_values, "branch_code") == source.branch_code
    ):
        values["branch_code"] = ""

    return values
