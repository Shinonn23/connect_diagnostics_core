# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.setup import procure_to_pay as p2p


def before_validate(doc: Document, _method: str | None = None) -> None:
    if doc.is_new():
        doc.set("supplier_onboarding_state", p2p.SUPPLIER_DRAFT)
        doc.set("disabled", 1)


def validate_supplier_onboarding(doc: Document, _method: str | None = None) -> None:
    previous = doc.get_doc_before_save()
    state = cast(str, doc.get("supplier_onboarding_state") or "")
    if not state:
        frappe.throw(_("Supplier onboarding state is required."))
    previous_state = cast(str, previous.get("supplier_onboarding_state") or "") if previous else ""
    if state == p2p.SUPPLIER_ACTIVE:
        if previous_state != state:
            _require_user(p2p.SASIN_USER, "activate a Supplier")
            if not _has_verified_bank_account(doc.name):
                frappe.throw(_("Supplier must have a verified Bank Account before activation."))
        doc.set("disabled", 0)
    elif state == p2p.SUPPLIER_LEGACY_ACTIVE:
        doc.set("disabled", 0)
    else:
        doc.set("disabled", 1)
    if previous and previous.get("supplier_onboarding_state") != state:
        if state == p2p.SUPPLIER_ACTIVATION:
            _require_user(p2p.KIATTISAK_USER, "verify a Supplier")
        if (
            state == p2p.SUPPLIER_DRAFT
            and previous.get("supplier_onboarding_state") == p2p.SUPPLIER_VERIFICATION
        ):
            _require_user(p2p.KIATTISAK_USER, "return a Supplier")
    if previous and previous.get("supplier_onboarding_state") in {
        p2p.SUPPLIER_ACTIVE,
        p2p.SUPPLIER_LEGACY_ACTIVE,
    }:
        protected = ("supplier_name", "tax_id", "branch_code", "payment_terms", "default_bank_account")
        if any(doc.get(field) != previous.get(field) for field in protected):
            frappe.throw(
                _("Active Supplier details must be changed through an approved Supplier Bank Change Request.")
            )


def validate_bank_account(doc: Document, _method: str | None = None) -> None:
    if doc.get("party_type") != "Supplier":
        return
    previous = doc.get_doc_before_save()
    is_awaiting_approval = frappe.db.exists(
        p2p.BANK_CHANGE_REQUEST,
        {
            "bank_account": doc.name,
            "bank_change_request_state": ["in", [p2p.BANK_APPROVAL, p2p.BANK_VERIFIED]],
            "docstatus": ["<", 2],
        },
    )
    if previous and (previous.get("supplier_bank_verification_status") == "Verified" or is_awaiting_approval):
        protected = ("party", "bank", "bank_account_no", "account_name", "branch_code")
        if any(doc.get(field) != previous.get(field) for field in protected):
            frappe.throw(
                _(
                    "Verified Supplier Bank Account details must be changed through a Supplier Bank Change Request."
                )
            )


def before_validate_bank_change_request(doc: Document, _method: str | None = None) -> None:
    if doc.is_new():
        doc.set("bank_change_request_state", p2p.BANK_DRAFT)


def validate_bank_change_request(doc: Document, _method: str | None = None) -> None:
    bank = frappe.db.get_value("Bank Account", doc.get("bank_account"), ["party_type", "party"], as_dict=True)
    if not bank or bank.get("party_type") != "Supplier" or bank.get("party") != doc.get("supplier"):
        frappe.throw(_("Bank Account must belong to the selected Supplier."))
    previous = doc.get_doc_before_save()
    if not previous or previous.get("bank_change_request_state") == doc.get("bank_change_request_state"):
        return
    state = cast(str, doc.get("bank_change_request_state"))
    if state == p2p.BANK_APPROVAL:
        _require_user(p2p.KIATTISAK_USER, "verify Supplier bank details")
        if doc.get("owner") == frappe.session.user:
            frappe.throw(_("The bank change requester cannot verify the same request."))
        doc.set("verified_by", frappe.session.user)
        doc.set("verified_on", now_datetime())
    elif state == p2p.BANK_VERIFIED:
        _require_user(p2p.SASIN_USER, "approve a Supplier bank change")
        doc.set("approved_by", frappe.session.user)
        doc.set("approved_on", now_datetime())


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
    approved_request_exists = frappe.db.exists(
        p2p.BANK_CHANGE_REQUEST,
        {
            "bank_account": doc.get("bank_account"),
            "bank_change_request_state": p2p.BANK_VERIFIED,
            "docstatus": 1,
        },
    )
    if not approved_request_exists:
        frappe.db.set_value(
            "Bank Account",
            doc.get("bank_account"),
            {"supplier_bank_verification_status": "Unverified", "supplier_bank_change_request": None},
            update_modified=False,
        )


def _has_verified_bank_account(supplier: str | None) -> bool:
    return bool(
        frappe.db.exists(
            "Bank Account",
            {
                "party_type": "Supplier",
                "party": supplier,
                "disabled": 0,
                "supplier_bank_verification_status": "Verified",
            },
        )
    )


def _require_user(user: str, action: str) -> None:
    if frappe.session.user not in {"Administrator", user}:
        frappe.throw(_("Only {0} can {1}.").format(user, action))


def validate(doc: Any, method: str | None = None) -> None:
    validate_supplier_onboarding(cast(Document, doc), method)


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
