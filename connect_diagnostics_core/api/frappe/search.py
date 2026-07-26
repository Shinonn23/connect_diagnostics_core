# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.desk import search as frappe_search

from connect_diagnostics_core.api.erpnext.dksh_item_mapping import DKSH_ITEM_MAPPING_DOCTYPE
from connect_diagnostics_core.api.erpnext.sales_order import DKSH_ITEM_MAPPING_QUERY


@frappe.whitelist()
def search_link(
    doctype: str,
    txt: str,
    query: str | None = None,
    filters: str | dict[str, Any] | list[Any] | None = None,
    page_length: int = 10,
    searchfield: str | None = None,
    reference_doctype: str | None = None,
    ignore_user_permissions: bool = False,
    *,
    link_fieldname: str | None = None,
) -> list[dict[str, str]]:
    """Keep all standard Link searches unchanged except DKSH Sales Order Item Code."""
    if doctype != DKSH_ITEM_MAPPING_DOCTYPE or query != DKSH_ITEM_MAPPING_QUERY:
        return cast(
            list[dict[str, str]],
            frappe_search.search_link(
                doctype,
                txt,
                query,
                filters,
                page_length,
                searchfield,
                reference_doctype,
                ignore_user_permissions,
                link_fieldname=link_fieldname,
            ),
        )

    rows = cast(
        list[tuple[Any, ...]],
        frappe_search.search_widget(
            doctype,
            txt.strip(),
            query,
            searchfield=searchfield,
            page_length=page_length,
            filters=filters,
            reference_doctype=reference_doctype,
            ignore_user_permissions=ignore_user_permissions,
            link_fieldname=link_fieldname,
        ),
    )
    return [
        {
            "value": str(row[0]),
            "label": str(row[1]),
            "description": str(row[2] or ""),
        }
        for row in rows
    ]
