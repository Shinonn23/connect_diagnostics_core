# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

from connect_diagnostics_core.naming import party_dksh


def validate(doc: Any, method: str | None = None) -> None:
    party_dksh.validate(doc, method)


def on_update(doc: Any, method: str | None = None) -> None:
    party_dksh.issue_cd_code_on_update(doc, method)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None = None,
) -> list[tuple]:
    """Link search for Customer that also matches DKSH code and alternative names.

    Registered as the ``standard_queries`` handler for Customer, so it applies to
    every Customer link field. Mirrors the cross-field search used for Item.
    """
    frappe.has_permission("Customer", throw=True)

    like = f"%{txt}%"
    return frappe.get_list(
        "Customer",
        filters=filters or {},
        or_filters=[
            ["Customer", "name", "like", like],
            ["Customer", "customer_name", "like", like],
            ["Customer", "dksh_customer_code", "like", like],
            ["Customer Alternative Name", "name_value", "like", like],
        ],
        fields=["name", "customer_name"],
        limit_start=start,
        limit_page_length=page_len,
        order_by="name asc",
        distinct=True,
        as_list=True,
    )
