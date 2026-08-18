# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
import frappe.defaults
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


def before_validate(doc: Document, method: str | None = None) -> None:
    """Set server-owned defaults before Frappe validates the credit request."""
    if not doc.get("company"):
        doc.set("company", _default_company())


def validate(doc: Document, method: str | None = None) -> None:
    """Keep credit requests scoped to active Customers with valid credit terms."""
    if doc.get("company") != _default_company():
        frappe.throw(_("Customer Credit Requests are limited to the default CD Company."))
    if float(doc.get("requested_credit_limit") or 0) <= 0:
        frappe.throw(_("Requested Credit Limit must be greater than zero."))
    if not doc.get("payment_terms"):
        frappe.throw(_("Payment Terms are required."))

    # Every Customer asks for credit the same way, including GOV. HOSPITAL.
    _get_eligible_customer(cast(str, doc.get("customer")))


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
    if customer.get("disabled"):
        frappe.throw(_("Credit cannot be requested for a disabled Customer."))
    return customer


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
