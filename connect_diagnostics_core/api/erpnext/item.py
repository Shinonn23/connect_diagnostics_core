# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext import dksh_item_mapping

CHANNEL_CD = dksh_item_mapping.CHANNEL_CD
CHANNEL_DKSH = dksh_item_mapping.CHANNEL_DKSH
CHANNEL_BOTH = dksh_item_mapping.CHANNEL_BOTH
VALID_CHANNELS = {CHANNEL_CD, CHANNEL_DKSH, CHANNEL_BOTH}


def validate(doc: Document, method: str | None = None) -> None:
    """Keep legacy Item flags synchronized with the Master mapping model."""
    channel = _text(doc.get("item_channel"))
    if channel not in VALID_CHANNELS:
        frappe.throw(_("Item Channel must be CD, DKSH, or CD and DKSH."))

    # Legacy fields remain for historical data and legacy searches. New DKSH code
    # ownership and transaction eligibility live in DKSH Item Mapping instead.
    doc.set("has_dksh_code", int(channel != CHANNEL_CD))
    doc.set("item_code_is_dksh_code", int(channel == CHANNEL_DKSH))
    if channel == CHANNEL_CD:
        doc.set("dksh_item_code", None)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_with_stock(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | str | None = None,
) -> list[tuple[Any, ...]]:
    """Return Item link-search rows, optionally limited to the configured DKSH mapping."""
    frappe.has_permission("Item", throw=True)
    search_string = f"%{txt}%"
    if isinstance(filters, str):
        filters = cast(dict[str, Any], json.loads(filters))
    query_filters = filters or {}
    warehouse: str = cast(str, query_filters.get("warehouse", ""))
    dksh_company = _get_dksh_company(query_filters)

    def format_rows(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
        return [(row[0], row[1], f"{row[2]:g} QTY.") for row in rows]

    params = {
        "txt": search_string,
        "start": start,
        "page_len": page_len,
        "dksh_company": dksh_company,
        "active_mapping_state": dksh_item_mapping.ACTIVE_STATE,
    }
    if warehouse:
        params["warehouse"] = warehouse
        rows = frappe.db.sql(
            """
            SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code AND b.warehouse = %(warehouse)s
            WHERE i.disabled = 0
              AND (
                i.name LIKE %(txt)s
                OR i.item_name LIKE %(txt)s
                OR i.dksh_item_code LIKE %(txt)s
                OR i.model LIKE %(txt)s
                OR EXISTS (
                    SELECT 1
                    FROM `tabItem Alternative Name` ian
                    WHERE ian.parent = i.name
                      AND ian.parenttype = 'Item'
                      AND ian.parentfield = 'alternative_names'
                      AND ian.name_value LIKE %(txt)s
                )
                OR EXISTS (
                    SELECT 1
                    FROM `tabDKSH Item Mapping` mapping
                    WHERE mapping.item = i.name
                      AND IFNULL(mapping.active, 0) = 1
                      AND mapping.mapping_state = %(active_mapping_state)s
                      AND mapping.dksh_item_code LIKE %(txt)s
                )
              )
              AND (
                %(dksh_company)s = ''
                OR EXISTS (
                    SELECT 1
                    FROM `tabDKSH Item Mapping` mapping
                    WHERE mapping.item = i.name
                      AND IFNULL(mapping.active, 0) = 1
                      AND mapping.mapping_state = %(active_mapping_state)s
                )
              )
            GROUP BY i.name
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )
    else:
        rows = frappe.db.sql(
            """
            SELECT i.name, i.item_name, IFNULL(SUM(b.actual_qty), 0) AS qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code
            WHERE i.disabled = 0
              AND (
                i.name LIKE %(txt)s
                OR i.item_name LIKE %(txt)s
                OR i.dksh_item_code LIKE %(txt)s
                OR i.model LIKE %(txt)s
                OR EXISTS (
                    SELECT 1
                    FROM `tabItem Alternative Name` ian
                    WHERE ian.parent = i.name
                      AND ian.parenttype = 'Item'
                      AND ian.parentfield = 'alternative_names'
                      AND ian.name_value LIKE %(txt)s
                )
                OR EXISTS (
                    SELECT 1
                    FROM `tabDKSH Item Mapping` mapping
                    WHERE mapping.item = i.name
                      AND IFNULL(mapping.active, 0) = 1
                      AND mapping.mapping_state = %(active_mapping_state)s
                      AND mapping.dksh_item_code LIKE %(txt)s
                )
              )
              AND (
                %(dksh_company)s = ''
                OR EXISTS (
                    SELECT 1
                    FROM `tabDKSH Item Mapping` mapping
                    WHERE mapping.item = i.name
                      AND IFNULL(mapping.active, 0) = 1
                      AND mapping.mapping_state = %(active_mapping_state)s
                )
              )
            GROUP BY i.name
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )
    return format_rows(rows)


def _get_dksh_company(filters: dict[str, Any]) -> str:
    company = _text(filters.get("company"))
    return company if dksh_item_mapping.is_dksh_company(company) else ""


def _text(value: object) -> str:
    return str(value or "").strip()
