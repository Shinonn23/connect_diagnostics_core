# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def supplier_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None = None,
) -> list[tuple]:
    """Link search for Supplier that also matches alternative names.

    Registered as the ``standard_queries`` handler for Supplier, so it applies to
    every Supplier link field. Mirrors the cross-field search used for Item.
    """
    frappe.has_permission("Supplier", throw=True)

    like = f"%{txt}%"
    return frappe.get_list(
        "Supplier",
        filters=filters or {},
        or_filters=[
            ["Supplier", "name", "like", like],
            ["Supplier", "supplier_name", "like", like],
            ["Supplier Alternative Name", "name_value", "like", like],
        ],
        fields=["name", "supplier_name"],
        limit_start=start,
        limit_page_length=page_len,
        order_by="name asc",
        distinct=True,
        as_list=True,
    )
