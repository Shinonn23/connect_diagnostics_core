# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Customer rules, kept deliberately thin so Sales can start selling immediately.

A Customer is usable the moment Sales saves it. There is no activation state and
no approval queue: the master data a sale eventually needs — a Thai billing
address, a matching tax ID, a delivery address — is checked where it is actually
needed, when a Sales Invoice is submitted, not before an order can be raised.

What remains here:

* Customer Code is the document name, so a change to it is a rename, and it is
  frozen once the Customer has transactions pointing at it
* payment terms and credit limits stay behind the Accounting Reviewer role;
  everyone else raises a ``Customer Credit Request``
* readiness is *calculated*, never stored — :func:`build_readiness_values` is the
  one place that decides what a Customer is still missing, and both the invoice
  gate and the Customer form read it live
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import frappe
import frappe.defaults
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.naming.customer import normalise_customer_code
from connect_diagnostics_core.setup import customer_onboarding

READY = "Ready"
MISSING = "Missing information"
NOT_APPLICABLE = "Not applicable"

# Documents that make a Customer Code permanent: renaming it once these exist
# would rewrite history that has already been sent out or filed.
TRANSACTION_DOCTYPES = ("Quotation", "Sales Order", "Sales Invoice", "Delivery Note")

_CUSTOMER_READINESS_FIELDS = (
    "name",
    "customer_name",
    "customer_group",
    "territory",
    "customer_code",
    "tax_id",
    "branch_code",
    "email_id",
)
_ADDRESS_READINESS_FIELDS = (
    "name",
    "address_type",
    "address_line1",
    "city",
    "county",
    "state",
    "pincode",
    "country",
    "tax_id",
    "branch_code",
    "is_primary_address",
    "is_shipping_address",
    "disabled",
)
_CONTACT_READINESS_FIELDS = (
    "name",
    "full_name",
    "first_name",
    "mobile_no",
    "phone",
    "email_id",
    "is_primary_contact",
)


def before_validate(doc: Document, method: str | None = None) -> None:
    """Normalise the Customer Code before Frappe validates or names the record."""
    doc.set("customer_code", normalise_customer_code(doc.get("customer_code")))


def validate(doc: Document, method: str | None = None) -> None:
    """Enforce the two invariants a Customer still has."""
    previous_doc = doc.get_doc_before_save()
    _validate_customer_code_change(doc, previous_doc)
    _validate_financial_data_access(doc, previous_doc)


def on_update(doc: Document, method: str | None = None) -> None:
    """Carry a Customer Code change through as a rename."""
    new_customer_code = cast(str | None, doc.flags.get("customer_code_rename_to"))
    if not new_customer_code or new_customer_code == doc.name:
        return

    old_name = doc.name
    customer_name = cast(str, doc.get("customer_name") or "")
    doc.flags.customer_code_rename_to = None
    frappe.rename_doc("Customer", old_name, new_customer_code, force=True, show_alert=False)
    doc.name = new_customer_code
    # ERPNext's Customer.after_rename sets Customer Name to the document name
    # when the site uses the legacy ``Customer Name`` naming preference.
    # Customer Code naming must never overwrite the business name.
    if customer_name:
        frappe.db.set_value(
            "Customer", new_customer_code, "customer_name", customer_name, update_modified=False
        )


def build_readiness_values(
    *,
    customer: Mapping[str, Any],
    addresses: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Calculate what a Customer is still missing, without storing anything."""
    quotation_missing = [
        label
        for fieldname, label in (
            ("customer_code", "Customer Code"),
            ("customer_name", "Customer Name"),
            ("customer_group", "Customer Group"),
            ("territory", "Territory"),
        )
        if not _text(customer.get(fieldname))
    ]

    active_addresses = [address for address in addresses if not _truthy(address.get("disabled"))]
    billing_addresses = [
        address
        for address in active_addresses
        if _truthy(address.get("is_primary_address")) and _text(address.get("address_type")) == "Billing"
    ]
    tax_missing = _tax_readiness_gaps(customer, billing_addresses)
    delivery_status, delivery_missing = _delivery_readiness(active_addresses, contacts)
    email_status, email_missing = _email_readiness(customer, contacts)

    summary_parts: list[str] = []
    if quotation_missing:
        summary_parts.append(_("Quotation: {0}").format(", ".join(quotation_missing)))
    if tax_missing:
        summary_parts.append(_("Tax Invoice: {0}").format(", ".join(tax_missing)))
    if delivery_missing:
        summary_parts.append(_("Delivery: {0}").format(", ".join(delivery_missing)))
    if email_missing:
        summary_parts.append(_("Email: {0}").format(", ".join(email_missing)))

    return {
        "quotation_readiness": READY if not quotation_missing else MISSING,
        "delivery_readiness": delivery_status,
        "tax_invoice_readiness": READY if not tax_missing else MISSING,
        "email_readiness": email_status,
        "customer_readiness_summary": " | ".join(summary_parts),
    }


def get_readiness_for_customer(customer_name: str) -> dict[str, str]:
    """Calculate one Customer's readiness from its current Address and Contact records."""
    if not customer_name:
        return {}
    customer = cast(
        dict[str, Any] | None,
        frappe.db.get_value("Customer", customer_name, list(_CUSTOMER_READINESS_FIELDS), as_dict=True),
    )
    if not customer:
        return {}
    return build_readiness_values(
        customer=customer,
        addresses=_get_customer_addresses(customer_name),
        contacts=_get_customer_contacts(customer_name),
    )


def _tax_readiness_gaps(
    customer: Mapping[str, Any], billing_addresses: Sequence[Mapping[str, Any]]
) -> list[str]:
    tax_id = _text(customer.get("tax_id"))
    branch_code = _text(customer.get("branch_code"))
    missing: list[str] = []
    if not tax_id:
        missing.append(_("Customer Tax ID"))
    if not branch_code:
        missing.append(_("Customer Branch Code"))
    if len(billing_addresses) != 1:
        missing.append(_("exactly one active primary Billing Address"))
        return missing

    address = billing_addresses[0]
    for fieldname, label in (
        ("address_line1", "Address Line 1"),
        ("city", "City"),
        ("county", "County"),
        ("state", "State"),
        ("pincode", "Postal Code"),
    ):
        if not _text(address.get(fieldname)):
            missing.append(_("Billing Address {0}").format(_(label)))
    if _text(address.get("country")) != "Thailand":
        missing.append(_("Billing Address Country must be Thailand"))
    if tax_id and _text(address.get("tax_id")) != tax_id:
        missing.append(_("Billing Address Tax ID must match Customer Tax ID"))
    if branch_code and _text(address.get("branch_code")) != branch_code:
        missing.append(_("Billing Address Branch Code must match Customer Branch Code"))
    return missing


def _delivery_readiness(
    active_addresses: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    missing: list[str] = []
    shipping_addresses = [
        address for address in active_addresses if _truthy(address.get("is_shipping_address"))
    ]
    if len(shipping_addresses) != 1:
        missing.append(_("exactly one active preferred Shipping Address"))

    primary_contacts = [contact for contact in contacts if _truthy(contact.get("is_primary_contact"))]
    if len(primary_contacts) != 1:
        missing.append(_("exactly one primary Contact"))
    elif not (_text(primary_contacts[0].get("full_name")) or _text(primary_contacts[0].get("first_name"))):
        missing.append(_("Primary Contact name"))
    elif not (_text(primary_contacts[0].get("mobile_no")) or _text(primary_contacts[0].get("phone"))):
        missing.append(_("Primary Contact mobile number or phone"))

    return (READY if not missing else MISSING), missing


def _email_readiness(
    customer: Mapping[str, Any], contacts: Sequence[Mapping[str, Any]]
) -> tuple[str, list[str]]:
    if _text(customer.get("email_id")) or any(_text(contact.get("email_id")) for contact in contacts):
        return READY, []
    return MISSING, [_("Customer or Contact email address")]


def _get_customer_addresses(customer_name: str) -> list[dict[str, Any]]:
    address_names = _linked_document_names(customer_name, "Address")
    if not address_names:
        return []
    return cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Address",
            filters={"name": ["in", address_names]},
            fields=list(_ADDRESS_READINESS_FIELDS),
        ),
    )


def _get_customer_contacts(customer_name: str) -> list[dict[str, Any]]:
    contact_names = _linked_document_names(customer_name, "Contact")
    if not contact_names:
        return []
    return cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Contact",
            filters={"name": ["in", contact_names]},
            fields=list(_CONTACT_READINESS_FIELDS),
        ),
    )


def _linked_document_names(customer_name: str, parenttype: str) -> list[str]:
    return cast(
        list[str],
        frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": customer_name,
                "parenttype": parenttype,
            },
            pluck="parent",
        ),
    )


def _validate_customer_code_change(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc:
        return

    old_code = normalise_customer_code(previous_doc.get("customer_code"))
    new_code = normalise_customer_code(doc.get("customer_code"))
    if old_code == new_code:
        return

    if _has_transactions(cast(str, doc.name)):
        frappe.throw(_("Customer Code cannot be changed once the Customer has transactions."))
    if frappe.db.exists("Customer", new_code):
        frappe.throw(_("Customer Code {0} already exists.").format(frappe.bold(new_code)))
    doc.flags.customer_code_rename_to = new_code


def _has_transactions(customer_name: str) -> bool:
    """Report whether anything has been raised against this Customer yet."""
    if not customer_name:
        return False
    for doctype in TRANSACTION_DOCTYPES:
        field = "party_name" if doctype == "Quotation" else "customer"
        if frappe.db.exists(doctype, {field: customer_name, "docstatus": ["<", 2]}):
            return True
    return False


def _validate_financial_data_access(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or doc.flags.get("allow_credit_request_update"):
        return
    payment_terms_changed = _text(doc.get("payment_terms")) != _text(previous_doc.get("payment_terms"))
    credit_limits_changed = _credit_limits_signature(doc) != _credit_limits_signature(previous_doc)
    if not (payment_terms_changed or credit_limits_changed):
        return
    if customer_onboarding.ACCOUNTING_REVIEWER_ROLE not in set(frappe.get_roles()):
        frappe.throw(
            _(
                "Only a Customer Accounting Reviewer can change payment terms or credit limits. "
                "Raise a Customer Credit Request instead."
            )
        )


def _credit_limits_signature(doc: Document) -> tuple[tuple[str, float, int], ...]:
    rows: list[tuple[str, float, int]] = []
    for row in doc.get("credit_limits", []):
        rows.append(
            (
                _text(row.get("company")),
                float(row.get("credit_limit") or 0),
                int(row.get("bypass_credit_limit_check") or 0),
            )
        )
    return tuple(sorted(rows))


@frappe.whitelist()
def get_customer_readiness(customer: str) -> dict[str, Any]:
    """Return what the Customer is still missing, for the form to show."""
    frappe.has_permission("Customer", "read", customer, throw=True)
    return {"data": get_readiness_for_customer(customer), "message": ""}


@frappe.whitelist()
def customer_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | list[list[Any]] | None = None,
) -> list[tuple[Any, ...]]:
    """Return only transaction-eligible Customers matched by code, name, or alternative name."""
    frappe.has_permission("Customer", throw=True)
    like = f"%{txt}%"
    return frappe.get_list(
        "Customer",
        filters=_active_customer_filters(filters),
        or_filters=[
            ["Customer", "name", "like", like],
            ["Customer", "customer_code", "like", like],
            ["Customer", "customer_name", "like", like],
            ["Customer Alternative Name", "name_value", "like", like],
        ],
        fields=["name", "customer_name"],
        limit_start=start,
        limit_page_length=page_len,
        order_by="name asc",
        distinct=True,
        as_list=True,
    )


def _active_customer_filters(
    filters: dict[str, Any] | list[list[Any]] | None,
) -> dict[str, Any] | list[list[Any]]:
    """Eligibility is now just "not disabled" — there is no activation state."""
    active_filters: dict[str, Any] | list[list[Any]]
    if isinstance(filters, dict):
        active_filters = {**filters, "disabled": 0}
    else:
        active_filters = [*(filters or []), ["Customer", "disabled", "=", 0]]
    return active_filters


def _text(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: object) -> bool:
    return bool(value) and str(value) not in {"0", "False"}
