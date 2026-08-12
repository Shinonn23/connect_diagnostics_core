# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from connect_diagnostics_core.api.erpnext.workflow import (
    finalize_if_workflow_inactive,
    has_active_workflow,
    initialize_workflow_state,
)
from connect_diagnostics_core.setup.payment_approval import (
    AP_REVIEWER_ROLE,
    APPROVED_STATE,
    BASE_GRAND_TOTAL_FIELD,
    CANCELLED_STATE,
    EXECUTIVE_APPROVER_ROLE,
    PAYMENT_REQUEST_DOCTYPE,
    PENDING_AP_REVIEW_STATE,
    PENDING_EXECUTIVE_APPROVAL_STATE,
    REJECTED_STATE,
    WORKFLOW_STATE_FIELD,
)

PAYMENT_APPROVER_ROLES = frozenset({EXECUTIVE_APPROVER_ROLE, AP_REVIEWER_ROLE})
ACTIONABLE_WORKFLOW_STATES = frozenset(
    {PENDING_AP_REVIEW_STATE, PENDING_EXECUTIVE_APPROVAL_STATE, REJECTED_STATE}
)

PAYMENT_REQUEST_LOCK_FIELDS = (
    "docstatus",
    "payment_request_type",
    "company",
    "party_type",
    "party",
    "reference_doctype",
    "reference_name",
    "outstanding_amount",
    WORKFLOW_STATE_FIELD,
)


def before_validate(doc: Document, _method: str | None = None) -> None:
    initialize_workflow_state(doc)


def validate_payment_request_before_submit(doc: Document, _method: str) -> None:
    previous_doc = _get_previous_doc(doc)
    _validate_payment_request_fields(doc, previous_doc)

    payment_request_type = cast(str, doc.get("payment_request_type") or "")
    if payment_request_type != "Outward":
        _validate_inward_submitter()
        return

    finalize_if_workflow_inactive(doc, WORKFLOW_STATE_FIELD, APPROVED_STATE)
    _validate_verified_supplier_bank(doc)


def set_cancelled_workflow_state(doc: Document, _method: str) -> None:
    if not has_active_workflow(PAYMENT_REQUEST_DOCTYPE):
        doc.set(WORKFLOW_STATE_FIELD, CANCELLED_STATE)


def validate_before_discard(doc: Document, _method: str) -> None:
    approval_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if (
        doc.get("payment_request_type") != "Outward"
        or approval_state not in ACTIONABLE_WORKFLOW_STATES
        or not has_active_workflow(PAYMENT_REQUEST_DOCTYPE)
    ):
        return
    frappe.throw(
        _(
            "An Outward Payment Request in the approval workflow cannot be discarded. "
            "Complete the workflow instead."
        ),
        title=_("Payment approval is active"),
    )


def validate_payment_entry_before_submit(doc: Document, _method: str) -> None:
    if doc.get("payment_type") != "Pay":
        return
    if not doc.get("reference_no") or not doc.get("reference_date"):
        frappe.throw(_("Outgoing Payment Entry requires a reference number and reference date."))
    if not frappe.db.exists(
        "File",
        {"attached_to_doctype": "Payment Entry", "attached_to_name": doc.name},
    ):
        frappe.throw(_("Outgoing Payment Entry requires payment evidence as an attachment."))

    allocated_rows = _get_allocated_reference_rows(doc)
    if not allocated_rows:
        frappe.throw(
            _("Outgoing Payment Entry must allocate its full amount to at least one reference."),
            title=_("Payment Request required"),
        )

    unallocated_precision = doc.precision("unallocated_amount")
    if flt(doc.get("unallocated_amount"), unallocated_precision) != 0:
        frappe.throw(
            _("Outgoing Payment Entry must have zero unallocated amount before submission."),
            title=_("Full allocation required"),
        )

    allocation_by_request: dict[str, float] = {}
    for row in allocated_rows:
        payment_request_name = cast(str, row.get("payment_request") or "")
        if not payment_request_name:
            frappe.throw(
                _("Row {0}: Every allocated reference must have a Payment Request.").format(row.idx),
                title=_("Payment Request required"),
            )
        allocation_by_request[payment_request_name] = allocation_by_request.get(
            payment_request_name, 0.0
        ) + abs(flt(row.get("allocated_amount"), row.precision("allocated_amount")))

    locked_requests = _lock_payment_requests(tuple(sorted(allocation_by_request)))
    for row in allocated_rows:
        payment_request_name = cast(str, row.get("payment_request"))
        _validate_payment_request_matches_reference(
            doc,
            row,
            payment_request_name,
            locked_requests[payment_request_name],
        )

    outstanding_precision = frappe.get_precision(PAYMENT_REQUEST_DOCTYPE, "outstanding_amount")
    for payment_request_name, allocated_amount in allocation_by_request.items():
        outstanding_amount = flt(
            locked_requests[payment_request_name].get("outstanding_amount"),
            outstanding_precision,
        )
        if outstanding_amount <= 0 or flt(allocated_amount, outstanding_precision) > outstanding_amount:
            frappe.throw(
                _("Allocated amount exceeds the remaining amount of Payment Request {0}.").format(
                    frappe.bold(payment_request_name)
                ),
                title=_("Payment Request amount exceeded"),
            )


def _validate_payment_request_fields(doc: Document, previous_doc: Document | None) -> None:
    _validate_creator_unchanged(doc, previous_doc)
    _validate_pending_request_immutability(doc, previous_doc)
    if doc.get("payment_request_type") != "Outward":
        return
    _maintain_base_grand_total(doc, previous_doc)


def _get_previous_doc(doc: Document) -> Document | None:
    get_doc_before_save = getattr(doc, "get_doc_before_save", None)
    if not callable(get_doc_before_save):
        return None
    return cast(Document | None, get_doc_before_save())


def _maintain_base_grand_total(doc: Document, previous_doc: Document | None) -> None:
    expected_base_grand_total = _calculate_base_grand_total(doc)
    doc.set(BASE_GRAND_TOTAL_FIELD, expected_base_grand_total)


def _validate_pending_request_immutability(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or not has_active_workflow(PAYMENT_REQUEST_DOCTYPE):
        return
    if previous_doc.get("payment_request_type") != "Outward":
        return
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "")
    if previous_state not in {PENDING_AP_REVIEW_STATE, PENDING_EXECUTIVE_APPROVAL_STATE}:
        return
    locked_fields = (
        "payment_request_type",
        "company",
        "party_type",
        "party",
        "reference_doctype",
        "reference_name",
        "outstanding_amount",
    )
    if any(doc.get(fieldname) != previous_doc.get(fieldname) for fieldname in locked_fields):
        frappe.throw(
            _("Payment Request details cannot change while approval is pending."),
            title=_("Payment Request is locked"),
        )
    previous_amount = flt(previous_doc.get(BASE_GRAND_TOTAL_FIELD), doc.precision(BASE_GRAND_TOTAL_FIELD))
    current_amount = flt(doc.get(BASE_GRAND_TOTAL_FIELD), doc.precision(BASE_GRAND_TOTAL_FIELD))
    expected_amount = _calculate_base_grand_total(doc)
    if current_amount != previous_amount or expected_amount != previous_amount:
        frappe.throw(
            _("The company-currency amount of a Payment Request cannot change while approval is pending."),
            title=_("Payment Request amount cannot change"),
        )


def _calculate_base_grand_total(doc: Document) -> float:
    company = cast(str, doc.get("company") or "")
    currency = cast(str, doc.get("currency") or "")
    reference_doctype = cast(str, doc.get("reference_doctype") or "")
    reference_name = cast(str, doc.get("reference_name") or "")
    if not company or not currency or not reference_doctype or not reference_name:
        frappe.throw(
            _("Company, currency, and reference document are required for payment approval."),
            title=_("Payment approval amount unavailable"),
        )

    company_currency = cast(
        str,
        frappe.get_cached_value("Company", company, "default_currency") or "",
    )
    if not company_currency:
        frappe.throw(
            _("Company {0} must have a default currency.").format(frappe.bold(company)),
            title=_("Company currency required"),
        )

    reference_meta = frappe.get_meta(reference_doctype)
    reference_fields = [
        fieldname
        for fieldname in ("company", "currency", "conversion_rate")
        if reference_meta.has_field(fieldname)
    ]
    reference = frappe.db.get_value(
        reference_doctype,
        reference_name,
        reference_fields,
        as_dict=True,
    )
    if not reference:
        frappe.throw(
            _("Reference document {0} {1} does not exist.").format(
                frappe.bold(reference_doctype), frappe.bold(reference_name)
            ),
            title=_("Invalid payment reference"),
        )

    reference_company = cast(str, reference.get("company") or "")
    if reference_company and reference_company != company:
        frappe.throw(
            _("Payment Request company must match its reference document."),
            title=_("Company mismatch"),
        )
    reference_currency = cast(str, reference.get("currency") or "")
    if reference_currency and reference_currency != currency:
        frappe.throw(
            _("Payment Request currency must match its reference document."),
            title=_("Currency mismatch"),
        )

    conversion_rate = 1.0
    if currency != company_currency:
        conversion_rate = flt(reference.get("conversion_rate"))
        if conversion_rate <= 0:
            frappe.throw(
                _(
                    "Reference document {0} {1} must have a positive conversion rate for payment approval."
                ).format(frappe.bold(reference_doctype), frappe.bold(reference_name)),
                title=_("Conversion rate required"),
            )

    precision = doc.precision(BASE_GRAND_TOTAL_FIELD)
    return flt(flt(doc.get("grand_total")) * conversion_rate, precision)


def _validate_creator_unchanged(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or doc.get("owner") == previous_doc.get("owner"):
        return
    frappe.throw(
        _("The creator of a Payment Request cannot be changed."),
        title=_("Payment Request creator cannot be changed"),
    )


def _validate_inward_submitter() -> None:
    if frappe.session.user == "Administrator":
        return
    roles = set(frappe.get_roles())
    if not PAYMENT_APPROVER_ROLES.intersection(roles) or "Accounts Manager" in roles:
        return
    frappe.throw(
        _("Payment approver roles do not grant permission to submit an Inward Payment Request."),
        title=_("Accounts Manager role required"),
    )


def _get_allocated_reference_rows(doc: Document) -> list[Document]:
    allocated_rows: list[Document] = []
    for row in cast(list[Document], doc.get("references") or []):
        precision = row.precision("allocated_amount")
        if flt(row.get("allocated_amount"), precision) != 0:
            allocated_rows.append(row)
    return allocated_rows


def _lock_payment_requests(payment_request_names: tuple[str, ...]) -> dict[str, Any]:
    locked_requests: dict[str, Any] = {}
    for payment_request_name in payment_request_names:
        payment_request = frappe.db.get_value(
            PAYMENT_REQUEST_DOCTYPE,
            payment_request_name,
            list(PAYMENT_REQUEST_LOCK_FIELDS),
            as_dict=True,
            for_update=True,
        )
        if not payment_request:
            frappe.throw(
                _("Payment Request {0} does not exist.").format(frappe.bold(payment_request_name)),
                title=_("Invalid Payment Request"),
            )
        locked_requests[payment_request_name] = payment_request
    return locked_requests


def _validate_payment_request_matches_reference(
    payment_entry: Document,
    reference_row: Document,
    payment_request_name: str,
    payment_request: Any,
) -> None:
    if payment_request.get("payment_request_type") != "Outward":
        _throw_reference_mismatch(reference_row, payment_request_name, "must be Outward")
    if int(payment_request.get("docstatus") or 0) != 1:
        _throw_reference_mismatch(reference_row, payment_request_name, "must be submitted")
    if (
        has_active_workflow(PAYMENT_REQUEST_DOCTYPE)
        and payment_request.get(WORKFLOW_STATE_FIELD) != APPROVED_STATE
    ):
        _throw_reference_mismatch(reference_row, payment_request_name, "must be approved")

    expected_values = {
        "company": payment_entry.get("company"),
        "party_type": payment_entry.get("party_type"),
        "party": payment_entry.get("party"),
        "reference_doctype": reference_row.get("reference_doctype"),
        "reference_name": reference_row.get("reference_name"),
    }
    for fieldname, expected_value in expected_values.items():
        if payment_request.get(fieldname) != expected_value:
            _throw_reference_mismatch(
                reference_row,
                payment_request_name,
                _("has a different {0}").format(fieldname.replace("_", " ")),
            )


def _validate_verified_supplier_bank(doc: Document) -> None:
    if doc.get("party_type") != "Supplier":
        return
    bank_account = cast(str, doc.get("bank_account") or "")
    if not bank_account:
        frappe.throw(_("Outward Supplier Payment Request requires a verified Bank Account."))
    bank = frappe.db.get_value(
        "Bank Account",
        bank_account,
        ["party_type", "party", "disabled", "supplier_bank_verification_status"],
        as_dict=True,
    )
    if not bank or bank.get("party_type") != "Supplier" or bank.get("party") != doc.get("party"):
        frappe.throw(_("Payment Request Bank Account must belong to its Supplier."))
    if bank.get("disabled") or bank.get("supplier_bank_verification_status") != "Verified":
        frappe.throw(_("Payment Request Bank Account must be verified before approval."))


def _throw_reference_mismatch(
    reference_row: Document,
    payment_request_name: str,
    reason: str,
) -> None:
    frappe.throw(
        _("Row {0}: Payment Request {1} {2}.").format(
            reference_row.idx,
            frappe.bold(payment_request_name),
            reason,
        ),
        title=_("Invalid Payment Request"),
    )
