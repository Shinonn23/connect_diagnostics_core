# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext import dksh_item_mapping
from connect_diagnostics_core.setup import dksh_item_mapping as dksh_item_mapping_setup
from connect_diagnostics_core.setup import sales_order_item

LEGACY_MAPPING_DOCTYPE = "Partner Item Mapping"
MAPPING_DOCTYPE = dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE


def execute() -> None:
    """Migrate active legacy DKSH mappings without deleting their child-table history."""
    create_custom_fields(sales_order_item.CUSTOM_FIELDS, ignore_validate=True)
    dksh_item_mapping_setup.ensure_configuration()
    _migrate_active_partner_item_mappings()
    _backfill_draft_dksh_sales_orders()
    _reset_sales_order_item_grid_settings()
    frappe.clear_cache(doctype=MAPPING_DOCTYPE)
    frappe.clear_cache(doctype="Sales Order")
    frappe.clear_cache(doctype="Item")


def _migrate_active_partner_item_mappings() -> None:
    if not frappe.db.table_exists(LEGACY_MAPPING_DOCTYPE):
        return

    company = dksh_item_mapping.get_dksh_company()

    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            LEGACY_MAPPING_DOCTYPE,
            filters={"parenttype": "Item", "partner_company": company},
            fields=["name", "parent", "external_item_code", "uom", "active"],
            order_by="parent asc, idx asc, name asc",
        ),
    )
    active_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    active_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not int(row.get("active") or 0):
            continue
        item_code = _text(row.get("parent"))
        external_item_code = _text(row.get("external_item_code"))
        if not item_code or not external_item_code:
            _log_issue(
                "Skipped an active Partner Item Mapping without both an Item and an External Item Code."
            )
            continue
        active_by_item[item_code].append(row)
        active_by_code[external_item_code].append(row)

    conflicting_items = {item_code for item_code, mappings in active_by_item.items() if len(mappings) > 1}
    conflicting_codes = {code for code, mappings in active_by_code.items() if len(mappings) > 1}
    for item_code in sorted(conflicting_items):
        _log_issue(f"Skipped {item_code}; it has more than one active legacy DKSH mapping.")
    for external_item_code in sorted(conflicting_codes):
        _log_issue(f"Skipped DKSH code {external_item_code}; it is active on more than one legacy Item.")

    existing_mappings = cast(
        list[dict[str, Any]],
        frappe.get_all(
            MAPPING_DOCTYPE,
            fields=["name", "item", "dksh_item_code"],
            order_by="name asc",
        ),
    )
    existing_item_codes = {_text(row.get("item")) for row in existing_mappings}
    existing_dksh_codes = {_text(row.get("dksh_item_code")) for row in existing_mappings}

    for item_code in sorted(active_by_item):
        if item_code in conflicting_items:
            continue
        legacy_mapping = active_by_item[item_code][0]
        external_item_code = _text(legacy_mapping.get("external_item_code"))
        if external_item_code in conflicting_codes:
            continue
        if item_code in existing_item_codes:
            continue
        if external_item_code in existing_dksh_codes:
            _log_issue(
                f"Skipped {item_code}; DKSH code {external_item_code} already exists in DKSH Item Mapping."
            )
            continue

        item = cast(
            dict[str, Any] | None,
            frappe.db.get_value(
                "Item",
                item_code,
                ["item_channel", *dksh_item_mapping.ITEM_MASTER_FIELDS],
                as_dict=True,
            ),
        )
        if not item:
            _log_issue(f"Skipped {item_code}; the legacy mapping's Item no longer exists.")
            continue

        item_channel = _text(item.get("item_channel"))
        mapping_channel = (
            dksh_item_mapping.CHANNEL_DKSH
            if item_channel == dksh_item_mapping.CHANNEL_DKSH
            else dksh_item_mapping.CHANNEL_BOTH
        )
        mapping = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": MAPPING_DOCTYPE,
                    "item": item_code,
                    "item_channel": mapping_channel,
                    **{fieldname: item.get(fieldname) for fieldname in dksh_item_mapping.ITEM_MASTER_FIELDS},
                }
            ),
        )
        mapping.insert(ignore_permissions=True)
        frappe.db.set_value(
            MAPPING_DOCTYPE,
            mapping.name,
            {
                "mapping_state": dksh_item_mapping.ACTIVE_STATE,
                "active": 1,
                "dksh_item_code": external_item_code,
                "request_sent_on": mapping.creation,
                "request_sent_by": mapping.owner,
            },
            update_modified=False,
        )
        _synchronize_item_for_migrated_mapping(item_code, mapping_channel, external_item_code)
        existing_item_codes.add(item_code)
        existing_dksh_codes.add(external_item_code)


def _synchronize_item_for_migrated_mapping(item_code: str, item_channel: str, dksh_item_code: str) -> None:
    frappe.db.set_value(
        "Item",
        item_code,
        {
            "item_channel": item_channel,
            "has_dksh_code": 1,
            "item_code_is_dksh_code": int(item_channel == dksh_item_mapping.CHANNEL_DKSH),
            "dksh_item_code": dksh_item_code,
        },
        update_modified=False,
    )


def _backfill_draft_dksh_sales_orders() -> None:
    company = dksh_item_mapping.get_dksh_company()

    draft_orders = cast(
        list[str],
        frappe.get_all(
            "Sales Order",
            filters={"company": company, "docstatus": 0},
            pluck="name",
            order_by="name asc",
        ),
    )
    if not draft_orders:
        return

    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Sales Order Item",
            filters={"parent": ["in", draft_orders]},
            fields=["name", "item_code"],
            order_by="parent asc, idx asc",
        ),
    )
    item_codes = sorted({_text(row.get("item_code")) for row in rows if _text(row.get("item_code"))})
    if not item_codes:
        return

    mappings = cast(
        list[dict[str, Any]],
        frappe.get_all(
            MAPPING_DOCTYPE,
            filters={
                "item": ["in", item_codes],
                "active": 1,
                "mapping_state": dksh_item_mapping.ACTIVE_STATE,
            },
            fields=["name", "item"],
            order_by="item asc, name asc",
        ),
    )
    mapping_by_item = {_text(mapping.get("item")): _text(mapping.get("name")) for mapping in mappings}
    updates = {
        _text(row.get("name")): {"dksh_item_mapping": mapping_by_item[_text(row.get("item_code"))]}
        for row in rows
        if _text(row.get("item_code")) in mapping_by_item
    }
    if updates:
        frappe.db.bulk_update("Sales Order Item", updates, update_modified=False)


def _reset_sales_order_item_grid_settings() -> None:
    settings = cast(
        list[dict[str, Any]],
        frappe.db.sql(
            "SELECT user, data FROM `__UserSettings` WHERE doctype = 'Sales Order' ORDER BY user ASC",
            as_dict=True,
        ),
    )
    for setting in settings:
        user = _text(setting.get("user"))
        data = _parse_user_settings(_text(setting.get("data")))
        grid_view = data.get("GridView")
        if not isinstance(grid_view, dict) or "Sales Order Item" not in grid_view:
            continue
        del grid_view["Sales Order Item"]
        frappe.db.sql(
            "UPDATE `__UserSettings` SET data = %(data)s WHERE user = %(user)s AND doctype = 'Sales Order'",
            {"data": json.dumps(data), "user": user},
        )
        cache = frappe.cache
        if cache is not None:
            cache.hset("_user_settings", f"Sales Order::{user}", None)


def _parse_user_settings(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _log_issue(message: str) -> None:
    frappe.logger(__name__).warning(message)


def _text(value: object) -> str:
    return str(value or "").strip()
