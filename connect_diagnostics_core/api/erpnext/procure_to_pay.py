# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.setup import procure_to_pay as p2p

SUBMITTED_STATE_BY_DOCTYPE = {
    "Material Request": p2p.MR_APPROVED,
    "Purchase Order": p2p.PO_APPROVED,
    "Purchase Receipt": p2p.RECEIPT_ACCEPTED,
    "Purchase Invoice": p2p.PI_VERIFIED,
}


def before_validate(doc: Document, _method: str | None = None) -> None:
    states = {
        "Material Request": p2p.MR_DRAFT,
        "Purchase Order": p2p.PO_DRAFT,
        "Purchase Receipt": p2p.RECEIPT_DRAFT,
        "Purchase Invoice": p2p.PI_DRAFT,
    }
    if doc.is_new():
        doc.set("p2p_workflow_state", states[doc.doctype])


def validate_material_request(doc: Document, _method: str | None = None) -> None:
    if not doc.get("purchase_reason"):
        frappe.throw(_("Purchase Reason is required."))
    _validate_executive_transition(doc, p2p.MR_PENDING, p2p.MR_APPROVED)


def validate_purchase_order(doc: Document, _method: str | None = None) -> None:
    _validate_verifier_transition(doc, p2p.PO_FINANCE)
    _validate_executive_transition(doc, p2p.PO_EXCEPTION, p2p.PO_APPROVED)
    if doc.get("p2p_workflow_state") in {p2p.PO_FINANCE, p2p.PO_EXCEPTION, p2p.PO_APPROVED}:
        material_requests = {
            row.get("material_request") for row in doc.get("items", []) if row.get("material_request")
        }
        approved_requests = set(
            frappe.get_all(
                "Material Request",
                filters={
                    "name": ["in", material_requests],
                    "docstatus": 1,
                    "p2p_workflow_state": p2p.MR_APPROVED,
                },
                pluck="name",
            )
        )
        missing = [
            row.idx for row in doc.get("items", []) if row.get("material_request") not in approved_requests
        ]
        if missing and not doc.get("p2p_exception_reason"):
            frappe.throw(
                _("Purchase Order rows without an approved Material Request require a P2P Exception Reason.")
            )


def validate_purchase_receipt(doc: Document, _method: str | None = None) -> None:
    previous = doc.get_doc_before_save()
    if (
        previous
        and previous.get("p2p_workflow_state") == p2p.RECEIPT_CHECK
        and doc.get("p2p_workflow_state") == p2p.RECEIPT_ACCEPTED
        and "Stock Manager" not in frappe.get_roles()
        and frappe.session.user != "Administrator"
    ):
        frappe.throw(_("Only a Stock Manager can accept goods."))


def validate_purchase_invoice(doc: Document, _method: str | None = None) -> None:
    _validate_verifier_transition(doc, p2p.PI_VERIFICATION)
    _validate_executive_transition(doc, p2p.PI_EXCEPTION, p2p.PI_VERIFIED)
    if doc.get("p2p_workflow_state") in {p2p.PI_VERIFICATION, p2p.PI_EXCEPTION, p2p.PI_VERIFIED}:
        for row in doc.get("items", []):
            if not row.get("purchase_order") and not doc.get("p2p_exception_reason"):
                frappe.throw(
                    _("Purchase Invoice rows without a Purchase Order require a P2P Exception Reason.")
                )
            if (
                row.get("is_stock_item")
                and not row.get("purchase_receipt")
                and not doc.get("p2p_exception_reason")
            ):
                frappe.throw(
                    _("Stock Purchase Invoice rows require a Purchase Receipt or a P2P Exception Reason.")
                )


def validate_before_submit(doc: Document, _method: str | None = None) -> None:
    required_state = SUBMITTED_STATE_BY_DOCTYPE[doc.doctype]
    if doc.get("p2p_workflow_state") != required_state:
        frappe.throw(_("{0} must complete its approval workflow before submission.").format(doc.doctype))


def _has_approved_material_request(material_request: str | None) -> bool:
    if not material_request:
        return False
    material_request_state = frappe.db.get_value(
        "Material Request",
        material_request,
        ["docstatus", "p2p_workflow_state"],
        as_dict=True,
    )
    return bool(
        material_request_state
        and material_request_state.get("docstatus") == 1
        and material_request_state.get("p2p_workflow_state") == p2p.MR_APPROVED
    )


def _validate_verifier_transition(doc: Document, pending: str) -> None:
    previous = doc.get_doc_before_save()
    if (
        previous
        and previous.get("p2p_workflow_state") == pending
        and doc.get("p2p_workflow_state") != pending
        and frappe.session.user not in {"Administrator", p2p.KIATTISAK_USER}
    ):
        frappe.throw(_("Only the P2P Finance Verifier can complete this review."))


def _validate_executive_transition(doc: Document, pending: str, approved: str) -> None:
    previous = doc.get_doc_before_save()
    if (
        not previous
        or previous.get("p2p_workflow_state") != pending
        or doc.get("p2p_workflow_state") != approved
    ):
        return
    if frappe.session.user not in {"Administrator", p2p.SASIN_USER, p2p.ARIRAT_USER}:
        frappe.throw(_("Only Sasin or Arirat can approve this P2P transaction."))
    if doc.get("owner") == frappe.session.user:
        frappe.throw(_("The document owner cannot approve the same P2P transaction."))
