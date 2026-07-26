# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Idempotent setup for DKSH-owned sales masters."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.model.document import Document

from connect_diagnostics_core.config.dksh import (
    DKSH_PRICE_LIST_CURRENCY,
    DKSH_STANDARD_SELLING_PRICE_LIST,
)

PRICE_LIST_DOCTYPE = "Price List"
MANAGED_PRICE_LIST_VALUES: dict[str, str | int] = {
    "price_list_name": DKSH_STANDARD_SELLING_PRICE_LIST,
    "currency": DKSH_PRICE_LIST_CURRENCY,
    "selling": 1,
    "enabled": 1,
}


def ensure_configuration() -> None:
    """Create or repair the app-owned selling Price List without changing Item Prices."""
    current = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            PRICE_LIST_DOCTYPE,
            DKSH_STANDARD_SELLING_PRICE_LIST,
            list(MANAGED_PRICE_LIST_VALUES),
            as_dict=True,
        ),
    )
    if current is None:
        _insert_price_list()
    else:
        changes = {
            fieldname: value
            for fieldname, value in MANAGED_PRICE_LIST_VALUES.items()
            if current.get(fieldname) != value
        }
        if changes:
            # Price List.save() calls ERPNext's update_item_price(). This direct,
            # scoped update deliberately preserves every existing Item Price.
            frappe.db.set_value(
                PRICE_LIST_DOCTYPE,
                DKSH_STANDARD_SELLING_PRICE_LIST,
                changes,
                update_modified=False,
            )

    cache = frappe.cache
    if cache:
        cache.hdel("price_list_details", DKSH_STANDARD_SELLING_PRICE_LIST)
    frappe.clear_cache(doctype=PRICE_LIST_DOCTYPE)


def _insert_price_list() -> None:
    """Insert the managed master without invoking Price List.on_update()."""
    price_list = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": PRICE_LIST_DOCTYPE,
                "name": DKSH_STANDARD_SELLING_PRICE_LIST,
                "buying": 0,
                **MANAGED_PRICE_LIST_VALUES,
            }
        ),
    )
    price_list.db_insert()
