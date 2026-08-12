# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.workflow import (
    finalize_if_workflow_inactive,
    initialize_workflow_state,
)
from connect_diagnostics_core.setup import procure_to_pay as p2p

SUBMITTED_STATE_BY_DOCTYPE = {
    "Material Request": p2p.MR_APPROVED,
    "Purchase Order": p2p.PO_APPROVED,
    "Purchase Receipt": p2p.RECEIPT_ACCEPTED,
    "Purchase Invoice": p2p.PI_VERIFIED,
}


def before_validate(doc: Document, _method: str | None = None) -> None:
    initialize_workflow_state(doc)


def validate_material_request(doc: Document, _method: str | None = None) -> None:
    if not doc.get("purchase_reason"):
        frappe.throw(_("Purchase Reason is required."))


def validate_purchase_order(doc: Document, _method: str | None = None) -> None:
    if doc.get("p2p_workflow_state") not in {p2p.PO_FINANCE, p2p.PO_EXCEPTION, p2p.PO_APPROVED}:
        return
    _validate_purchase_order_exception(doc)


def _validate_purchase_order_exception(doc: Document) -> None:
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


def validate_purchase_invoice(doc: Document, _method: str | None = None) -> None:
    if doc.get("p2p_workflow_state") not in {p2p.PI_VERIFICATION, p2p.PI_EXCEPTION, p2p.PI_VERIFIED}:
        return
    _validate_purchase_invoice_exception(doc)


def _validate_purchase_invoice_exception(doc: Document) -> None:
    for row in doc.get("items", []):
        if not row.get("purchase_order") and not doc.get("p2p_exception_reason"):
            frappe.throw(_("Purchase Invoice rows without a Purchase Order require a P2P Exception Reason."))
        if (
            row.get("is_stock_item")
            and not row.get("purchase_receipt")
            and not doc.get("p2p_exception_reason")
        ):
            frappe.throw(
                _("Stock Purchase Invoice rows require a Purchase Receipt or a P2P Exception Reason.")
            )


def validate_before_submit(doc: Document, _method: str | None = None) -> None:
    if doc.doctype == "Purchase Order":
        _validate_purchase_order_exception(doc)
    elif doc.doctype == "Purchase Invoice":
        _validate_purchase_invoice_exception(doc)
    finalize_if_workflow_inactive(doc, "p2p_workflow_state", SUBMITTED_STATE_BY_DOCTYPE[doc.doctype])
