# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.setup import procure_to_pay as p2p


def validate_bank_change_request(doc: Document, _method: str | None = None) -> None:
    bank = frappe.db.get_value("Bank Account", doc.get("bank_account"), ["party_type", "party"], as_dict=True)
    if not bank or bank.get("party_type") != "Supplier" or bank.get("party") != doc.get("supplier"):
        frappe.throw(_("Bank Account must belong to the selected Supplier."))


def on_submit_bank_change_request(doc: Document, _method: str | None = None) -> None:
    frappe.db.set_value(
        "Bank Account",
        doc.get("bank_account"),
        {"supplier_bank_verification_status": "Verified", "supplier_bank_change_request": doc.name},
        update_modified=False,
    )
    frappe.db.set_value(
        "Supplier",
        doc.get("supplier"),
        "default_bank_account",
        doc.get("bank_account"),
        update_modified=False,
    )


def on_cancel_bank_change_request(doc: Document, _method: str | None = None) -> None:
    another_submitted_request_exists = frappe.db.exists(
        p2p.BANK_CHANGE_REQUEST,
        {
            "bank_account": doc.get("bank_account"),
            "docstatus": 1,
            "name": ["!=", doc.name],
        },
    )
    if not another_submitted_request_exists:
        frappe.db.set_value(
            "Bank Account",
            doc.get("bank_account"),
            {"supplier_bank_verification_status": "Unverified", "supplier_bank_change_request": None},
            update_modified=False,
        )


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
    """Link search for Supplier that also matches by name.

    Registered as the ``standard_queries`` handler for Supplier, so it applies to
    every Supplier link field.
    """
    frappe.has_permission("Supplier", throw=True)

    like = f"%{txt}%"
    return frappe.get_list(
        "Supplier",
        filters=filters or {},
        or_filters=[
            ["Supplier", "name", "like", like],
            ["Supplier", "supplier_name", "like", like],
        ],
        fields=["name", "supplier_name"],
        limit_start=start,
        limit_page_length=page_len,
        order_by="name asc",
        distinct=True,
        as_list=True,
    )
