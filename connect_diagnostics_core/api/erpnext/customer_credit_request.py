# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
import frappe.defaults
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.setup import customer_onboarding

GOVERNMENT_HOSPITAL_GROUP = "GOV. HOSPITAL"


def before_validate(doc: Document, method: str | None = None) -> None:
    """Set server-owned defaults before Frappe validates the credit-request workflow."""
    if not doc.get("company"):
        doc.set("company", _default_company())
    if doc.is_new():
        doc.set("credit_request_state", customer_onboarding.CREDIT_REQUEST_DRAFT_STATE)


def validate(doc: Document, method: str | None = None) -> None:
    """Keep credit requests scoped to active Customers and protected after review starts."""
    if doc.get("company") != _default_company():
        frappe.throw(_("Customer Credit Requests are limited to the default CD Company."))
    if float(doc.get("requested_credit_limit") or 0) <= 0:
        frappe.throw(_("Requested Credit Limit must be greater than zero."))
    if not doc.get("payment_terms"):
        frappe.throw(_("Payment Terms are required."))

    customer = _get_eligible_customer(cast(str, doc.get("customer")))
    _validate_protected_fields(doc)
    _validate_rejection_reason(doc)

    if doc.get("credit_request_state") == customer_onboarding.CREDIT_REQUEST_APPROVED_STATE:
        if customer_onboarding.CREDIT_APPROVER_ROLE not in set(frappe.get_roles()):
            frappe.throw(_("Only a Customer Credit Approver can approve a Customer Credit Request."))
    if customer.get("customer_group") == GOVERNMENT_HOSPITAL_GROUP:
        frappe.throw(
            _(
                "GOV. HOSPITAL credit is configured during Customer onboarding, not by Customer Credit Request."
            )
        )


def before_submit(doc: Document, method: str | None = None) -> None:
    """Reject direct submit attempts that do not represent an approved workflow transition."""
    if doc.get("credit_request_state") != customer_onboarding.CREDIT_REQUEST_APPROVED_STATE:
        frappe.throw(_("Customer Credit Request must be approved before submission."))
    if customer_onboarding.CREDIT_APPROVER_ROLE not in set(frappe.get_roles()):
        frappe.throw(_("Only a Customer Credit Approver can submit an approved Customer Credit Request."))
    doc.set("approved_by", frappe.session.user)
    doc.set("approved_on", now_datetime())


def on_submit(doc: Document, method: str | None = None) -> None:
    """Apply an approved CD credit limit and payment terms once, under a Customer lock."""
    if doc.get("credit_applied"):
        return

    customer_name = cast(str, doc.get("customer"))
    frappe.db.get_value("Customer", customer_name, "name", for_update=True)
    customer = cast(Document, frappe.get_doc("Customer", customer_name))
    _get_eligible_customer(customer_name, customer=customer)

    company = cast(str, doc.get("company"))
    credit_limit = float(doc.get("requested_credit_limit") or 0)
    _set_customer_credit_limit(customer, company, credit_limit)
    customer.set("payment_terms", doc.get("payment_terms"))
    customer.flags.allow_credit_request_update = True
    customer.save(ignore_permissions=True)

    frappe.db.set_value(
        "Customer Credit Request",
        doc.name,
        {
            "approved_by": doc.get("approved_by") or frappe.session.user,
            "approved_on": doc.get("approved_on") or now_datetime(),
            "credit_applied": 1,
        },
        update_modified=False,
    )


def _get_eligible_customer(customer_name: str, *, customer: Document | None = None) -> Document:
    if not customer_name:
        frappe.throw(_("Customer is required."))
    customer = customer or cast(Document, frappe.get_doc("Customer", customer_name))
    if customer.get("customer_onboarding_state") != customer_onboarding.CUSTOMER_ACTIVE_STATE:
        frappe.throw(_("Customer must be active before requesting credit."))
    return customer


def _validate_protected_fields(doc: Document) -> None:
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return
    if previous_doc.get("credit_request_state") == customer_onboarding.CREDIT_REQUEST_DRAFT_STATE:
        return
    protected_fields = ("customer", "company", "requested_credit_limit", "payment_terms", "reason")
    changed = [
        fieldname for fieldname in protected_fields if doc.get(fieldname) != previous_doc.get(fieldname)
    ]
    if changed:
        frappe.throw(_("Customer Credit Request fields cannot be changed after credit review begins."))


def _validate_rejection_reason(doc: Document) -> None:
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return
    if (
        previous_doc.get("credit_request_state") == customer_onboarding.PENDING_CREDIT_APPROVAL_STATE
        and doc.get("credit_request_state") == customer_onboarding.CREDIT_REQUEST_REJECTED_STATE
        and not str(doc.get("review_reason") or "").strip()
    ):
        frappe.throw(_("Review Reason is required when rejecting a Customer Credit Request."))


def _set_customer_credit_limit(customer: Document, company: str, credit_limit: float) -> None:
    for row in customer.get("credit_limits", []):
        if row.get("company") == company:
            row.set("credit_limit", credit_limit)
            row.set("bypass_credit_limit_check", 0)
            return
    customer.append(
        "credit_limits",
        {"company": company, "credit_limit": credit_limit, "bypass_credit_limit_check": 0},
    )


def _default_company() -> str:
    company = str(frappe.defaults.get_global_default("company") or "").strip()
    if not company:
        frappe.throw(_("A default Company is required for Customer credit controls."))
    return company
