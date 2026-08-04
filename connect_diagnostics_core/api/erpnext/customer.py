# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
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

_CUSTOMER_READINESS_FIELDS = (
    "name",
    "customer_name",
    "customer_group",
    "territory",
    "customer_code",
    "tax_id",
    "branch_code",
    "email_id",
    "no_delivery_required",
    "no_delivery_reason",
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
    """Set server-owned defaults before Frappe validates the Customer workflow."""
    if doc.is_new():
        doc.set("customer_onboarding_state", customer_onboarding.CUSTOMER_REQUEST_STATE)
        doc.set("disabled", 1)
    doc.set("customer_code", normalise_customer_code(doc.get("customer_code")))


def validate(doc: Document, method: str | None = None) -> None:
    """Enforce Customer Code, readiness, and onboarding invariants."""
    previous_doc = doc.get_doc_before_save()
    _validate_customer_code_change(doc, previous_doc)
    _validate_financial_data_access(doc, previous_doc)
    readiness_values = build_readiness_values(
        customer=doc.as_dict(),
        addresses=_get_customer_addresses(doc.name) if doc.name else (),
        contacts=_get_customer_contacts(doc.name) if doc.name else (),
    )
    doc.update(readiness_values)
    _validate_onboarding_transition(doc, previous_doc, readiness_values)


def on_update(doc: Document, method: str | None = None) -> None:
    """Rename draft/conversion records safely and retain current readiness fields."""
    new_customer_code = cast(str | None, doc.flags.get("customer_code_rename_to"))
    if new_customer_code and new_customer_code != doc.name:
        old_name = doc.name
        customer_name = cast(str, doc.get("customer_name") or "")
        doc.flags.customer_code_rename_to = None
        frappe.rename_doc(
            "Customer",
            old_name,
            new_customer_code,
            force=True,
            show_alert=False,
        )
        doc.name = new_customer_code
        # ERPNext's Customer.after_rename sets Customer Name to the document name
        # when the site uses the legacy ``Customer Name`` naming preference.
        # Customer Code naming must never overwrite the business name.
        if customer_name:
            frappe.db.set_value(
                "Customer",
                new_customer_code,
                "customer_name",
                customer_name,
                update_modified=False,
            )
    refresh_customer_readiness(doc.name or "")


def refresh_linked_customer_readiness(doc: Document, method: str | None = None) -> None:
    """Refresh readiness for every Customer dynamically linked to an Address/Contact."""
    linked_customers = _linked_customer_names_from_document(doc)
    previous_doc = doc.get_doc_before_save()
    if previous_doc:
        # An Address or Contact can be unlinked without being deleted.  Its
        # current dynamic links no longer identify the Customer that lost it,
        # so refresh both the before-save and current link sets.
        linked_customers.update(_linked_customer_names_from_document(previous_doc))
    _refresh_customer_readiness_for_names(sorted(linked_customers))


def refresh_customer_readiness(customer_name: str) -> dict[str, str]:
    """Persist readiness without re-saving Customer or triggering workflow side effects."""
    if not customer_name:
        return {}
    return _refresh_customer_readiness_for_names([customer_name]).get(customer_name, {})


def _refresh_customer_readiness_for_names(
    customer_names: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Recalculate linked Customer readiness with batched, field-level queries."""
    names = sorted({name for name in customer_names if name})
    if not names:
        return {}

    customers = cast(
        list[dict[str, Any]],
        frappe.get_all("Customer", filters={"name": ["in", names]}, fields=list(_CUSTOMER_READINESS_FIELDS)),
    )
    if not customers:
        return {}

    names = sorted(cast(str, customer_row["name"]) for customer_row in customers)
    links = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": ["in", names],
                "parenttype": ["in", ["Address", "Contact"]],
            },
            fields=["parent", "parenttype", "link_name"],
        ),
    )
    address_names = sorted(
        {cast(str, link["parent"]) for link in links if link.get("parenttype") == "Address"}
    )
    contact_names = sorted(
        {cast(str, link["parent"]) for link in links if link.get("parenttype") == "Contact"}
    )
    addresses_by_name = _readiness_records_by_name("Address", address_names, _ADDRESS_READINESS_FIELDS)
    contacts_by_name = _readiness_records_by_name("Contact", contact_names, _CONTACT_READINESS_FIELDS)
    addresses_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contacts_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        customer_name = cast(str, link["link_name"])
        linked_name = cast(str, link["parent"])
        if link.get("parenttype") == "Address" and linked_name in addresses_by_name:
            addresses_by_customer[customer_name].append(addresses_by_name[linked_name])
        elif link.get("parenttype") == "Contact" and linked_name in contacts_by_name:
            contacts_by_customer[customer_name].append(contacts_by_name[linked_name])

    values_by_customer = {
        cast(str, customer_row["name"]): build_readiness_values(
            customer=customer_row,
            addresses=addresses_by_customer[cast(str, customer_row["name"])],
            contacts=contacts_by_customer[cast(str, customer_row["name"])],
        )
        for customer_row in customers
    }
    frappe.db.bulk_update("Customer", values_by_customer, update_modified=False)
    return values_by_customer


def _readiness_records_by_name(
    doctype: str,
    names: Sequence[str],
    fields: Sequence[str],
) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    records = cast(
        list[dict[str, Any]],
        frappe.get_all(doctype, filters={"name": ["in", list(names)]}, fields=list(fields)),
    )
    return {cast(str, record["name"]): record for record in records}


def build_readiness_values(
    *,
    customer: Mapping[str, Any],
    addresses: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Calculate informational document readiness from Customer, Address, and Contact data."""
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
    quotation_status = READY if not quotation_missing else MISSING

    active_addresses = [address for address in addresses if not _truthy(address.get("disabled"))]
    billing_addresses = [
        address
        for address in active_addresses
        if _truthy(address.get("is_primary_address")) and _text(address.get("address_type")) == "Billing"
    ]
    tax_missing = _tax_readiness_gaps(customer, billing_addresses)
    tax_status = READY if not tax_missing else MISSING

    delivery_status, delivery_missing = _delivery_readiness(customer, active_addresses, contacts)
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
        "quotation_readiness": quotation_status,
        "delivery_readiness": delivery_status,
        "tax_invoice_readiness": tax_status,
        "email_readiness": email_status,
        "customer_readiness_summary": " | ".join(summary_parts),
    }


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
    customer: Mapping[str, Any],
    active_addresses: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if _truthy(customer.get("no_delivery_required")):
        if _text(customer.get("no_delivery_reason")):
            return NOT_APPLICABLE, []
        return MISSING, [_("No Delivery Reason")]

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


def _linked_customer_names_from_document(doc: Document) -> set[str]:
    return {
        cast(str, link.get("link_name"))
        for link in doc.get("links", [])
        if link.get("link_doctype") == "Customer" and link.get("link_name")
    }


def _validate_customer_code_change(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc:
        return

    old_code = normalise_customer_code(previous_doc.get("customer_code"))
    new_code = normalise_customer_code(doc.get("customer_code"))
    if old_code == new_code:
        return

    state = _text(previous_doc.get("customer_onboarding_state"))
    if state == customer_onboarding.CUSTOMER_ACTIVE_STATE:
        frappe.throw(_("Customer Code cannot be changed after activation."))
    if frappe.db.exists("Customer", new_code):
        frappe.throw(_("Customer Code {0} already exists.").format(frappe.bold(new_code)))
    doc.flags.customer_code_rename_to = new_code


def _validate_financial_data_access(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or doc.flags.get("allow_credit_request_update"):
        return
    payment_terms_changed = _text(doc.get("payment_terms")) != _text(previous_doc.get("payment_terms"))
    credit_limits_changed = _credit_limits_signature(doc) != _credit_limits_signature(previous_doc)
    if not (payment_terms_changed or credit_limits_changed):
        return
    if customer_onboarding.ACCOUNTING_REVIEWER_ROLE not in set(frappe.get_roles()):
        frappe.throw(_("Only a Customer Accounting Reviewer can change payment terms or credit limits."))


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


def _validate_onboarding_transition(
    doc: Document,
    previous_doc: Document | None,
    readiness_values: Mapping[str, str],
) -> None:
    state = _text(doc.get("customer_onboarding_state"))
    if not state:
        frappe.throw(_("Customer Onboarding State is required."))
    if doc.is_new() and state != customer_onboarding.CUSTOMER_REQUEST_STATE:
        frappe.throw(_("New Customers must start in Customer Request."))

    previous_state = _text(previous_doc.get("customer_onboarding_state")) if previous_doc else ""
    if previous_doc and previous_state != state:
        if state == customer_onboarding.CUSTOMER_REQUEST_STATE:
            correction_reason = _text(doc.get("correction_reason"))
            if not correction_reason:
                frappe.throw(_("A Correction Reason is required when returning a Customer for correction."))
        elif (
            previous_state == customer_onboarding.CUSTOMER_REQUEST_STATE
            and state == customer_onboarding.PENDING_DUPLICATE_STATE
        ):
            # A reviewer saves the correction reason before using the standard
            # workflow action. Clear it once Sales sends the corrected record
            # back so every later return requires a newly documented reason.
            doc.set("correction_reason", None)
        if previous_state == customer_onboarding.PENDING_DUPLICATE_STATE:
            _validate_active_it_ub_duplicate_verifier()
        if (
            previous_state == customer_onboarding.PENDING_ACCOUNTING_STATE
            and state != customer_onboarding.CUSTOMER_REQUEST_STATE
        ):
            _validate_accounting_review(doc)
    if state == customer_onboarding.CUSTOMER_ACTIVE_STATE:
        if previous_state != customer_onboarding.CUSTOMER_ACTIVE_STATE:
            _validate_activation_readiness(readiness_values)
        doc.set("disabled", 0)
    else:
        doc.set("disabled", 1)


def _validate_active_it_ub_duplicate_verifier() -> None:
    if customer_onboarding.DUPLICATE_VERIFIER_ROLE not in set(frappe.get_roles()):
        frappe.throw(_("Only a Customer Duplicate Verifier can complete duplicate verification."))
    active_employee = frappe.db.exists(
        "Employee",
        {
            "user_id": frappe.session.user,
            "status": "Active",
            "department": customer_onboarding.IT_UB_DEPARTMENT,
        },
    )
    if not active_employee:
        frappe.throw(_("Customer Duplicate Verifier must be an active Employee in IT - UB."))


def _validate_accounting_review(doc: Document) -> None:
    if _text(doc.get("customer_group")) == "GOV. HOSPITAL":
        if not _text(doc.get("payment_terms")):
            frappe.throw(_("Payment Terms are required for GOV. HOSPITAL Customers."))
        if _credit_limit_for_default_company(doc) <= 0:
            frappe.throw(_("A positive CD credit limit is required for GOV. HOSPITAL Customers."))
        return

    if not frappe.db.exists("Payment Terms Template", "Cash"):
        frappe.throw(_("Payment Terms Template Cash is required for Customer onboarding."))
    doc.set("payment_terms", "Cash")
    doc.set("credit_limits", [])


def _credit_limit_for_default_company(doc: Document) -> float:
    company = _default_company()
    for row in doc.get("credit_limits", []):
        if _text(row.get("company")) == company:
            return float(row.get("credit_limit") or 0)
    return 0


def _default_company() -> str:
    company = _text(frappe.defaults.get_global_default("company"))
    if not company:
        frappe.throw(_("A default Company is required for Customer credit controls."))
    return company


def _validate_activation_readiness(readiness_values: Mapping[str, str]) -> None:
    missing: list[str] = []
    if readiness_values.get("tax_invoice_readiness") != READY:
        missing.append(_("Tax Invoice readiness"))
    if readiness_values.get("delivery_readiness") not in {READY, NOT_APPLICABLE}:
        missing.append(_("Delivery readiness"))
    if missing:
        frappe.throw(_("Customer cannot be activated until {0} is complete.").format(", ".join(missing)))


@frappe.whitelist()
def get_customer_readiness(customer: str) -> dict[str, Any]:
    """Return current readiness values for the Customer form without changing state."""
    frappe.has_permission("Customer", "read", customer, throw=True)
    values = refresh_customer_readiness(customer)
    return {"data": values, "message": _("Customer readiness refreshed.")}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
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
    active_filters: dict[str, Any] | list[list[Any]]
    if isinstance(filters, dict):
        active_filters = {
            **filters,
            "disabled": 0,
            "customer_onboarding_state": customer_onboarding.CUSTOMER_ACTIVE_STATE,
        }
    else:
        active_filters = [
            *(filters or []),
            ["Customer", "disabled", "=", 0],
            ["Customer", "customer_onboarding_state", "=", customer_onboarding.CUSTOMER_ACTIVE_STATE],
        ]
    return active_filters


def _text(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}
