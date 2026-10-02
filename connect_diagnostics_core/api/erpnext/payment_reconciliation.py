# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Narrow synchronous native reconciliation for already approved Payment Entries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any, cast
from uuid import uuid4

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from frappe import _
from frappe.model.document import Document, clear_document_cache
from frappe.utils import flt

from connect_diagnostics_core.api.erpnext.payment_entry import get_payment_entry_dimension_fields
from connect_diagnostics_core.api.erpnext.payment_entry_workflow import (
    SUBMITTED_STATE,
    approval_payload,
    get_approval_digest,
)
from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_interactive_user,
    require_permission,
)

_CONTEXT_KEY = "_connect_diagnostics_payment_match_context"
_ROLES = ("Accounts User", "Accounts Manager")
_INVOICE_PARTY = {
    "Sales Invoice": ("Customer", "customer", "debit_to"),
    "Purchase Invoice": ("Supplier", "supplier", "credit_to"),
}
_SIGNED_FIELDS = (
    "approval_digest",
    "approval_maker_user",
    "approval_maker_at",
    "approval_checker_user",
    "approval_checker_at",
    "checked_by",
    "checked_at",
    "checked_signature",
    "approval_approver_user",
    "approval_approver_at",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
    "approval_submit_actor",
)


@dataclass(frozen=True)
class _Allocation:
    invoice_type: str
    invoice_name: str
    amount: float


@dataclass(frozen=True)
class _Capability:
    source: Document
    user: str
    payment: str
    before_digest: str
    expected_digest: str
    allocations: tuple[_Allocation, ...]


@dataclass
class _Context:
    source: Document
    capabilities: dict[str, _Capability]


def _fail(message: str) -> None:
    frappe.throw(_(message))


def _context() -> _Context | None:
    value = getattr(frappe.local, _CONTEXT_KEY, None)
    return value if isinstance(value, _Context) else None


def _positive(value: Any) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        _fail("Payment matching requires a numeric allocation.")
    if not 0 < amount < float("inf"):
        _fail("Payment matching requires a positive finite allocation.")
    return amount


def _same_amount(left: Any, right: Any) -> bool:
    return flt(left, 2) == flt(right, 2)


def _currency_value(value: Any, precision: int) -> Decimal:
    try:
        number = Decimal(str(value))
        unit = Decimal(1).scaleb(-precision)
        normalized = number.quantize(unit)
    except (InvalidOperation, TypeError, ValueError):
        _fail("Payment matching amount is not a valid currency value.")
    if not number.is_finite() or number != normalized:
        _fail("Payment matching amount exceeds the company currency precision.")
    return normalized


def _exact_number(value: Any, expected: int) -> bool:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return number.is_finite() and number == expected


def _locked_document(doctype: str, name: str) -> Document:
    row = frappe.db.get_value(doctype, name, "name", for_update=True)
    if row != name:
        _fail("Payment matching source document is missing.")
    return cast(Document, frappe.get_doc(doctype, name))


def _company_currency(company: str) -> str:
    currency = frappe.db.get_value("Company", company, "default_currency")
    if not currency:
        _fail("Payment matching company currency is unavailable.")
    return str(currency)


def _check_payment(source: Document, payment: Document, user: str, currency: str) -> None:
    if (
        payment.docstatus != 1
        or payment.get("workflow_state") != SUBMITTED_STATE
        or payment.get("company") != source.get("company")
        or payment.get("party_type") != source.get("party_type")
        or payment.get("party") != source.get("party")
        or payment.get("paid_from" if payment.get("payment_type") == "Receive" else "paid_to")
        != source.get("receivable_payable_account")
        or payment.get("payment_type") not in {"Pay", "Receive"}
    ):
        _fail("Payment matching source is outside the approved payment route.")
    if (
        payment.get("book_advance_payments_in_separate_party_account")
        or payment.get("paid_from_account_currency") != currency
        or payment.get("paid_to_account_currency") != currency
        or not _exact_number(payment.get("source_exchange_rate"), 1)
        or not _exact_number(payment.get("target_exchange_rate"), 1)
        or not _exact_number(payment.get("difference_amount"), 0)
        or any(row.get("is_exchange_gain_loss") for row in payment.get("deductions") or [])
    ):
        _fail("Payment matching requires ordinary company-currency unallocated funds.")
    if not all(payment.get(field) for field in _SIGNED_FIELDS):
        _fail("Payment matching requires complete historical signed approval.")
    require_distinct_actors(
        str(payment.get("approval_maker_user")),
        str(payment.get("approval_checker_user")),
        (),
    )
    require_distinct_actors(
        str(payment.get("approval_maker_user")),
        str(payment.get("approval_approver_user")),
        (str(payment.get("approval_checker_user")),),
    )
    require_permission(payment, "write")
    if user != frappe.session.user:
        _fail("Payment matching actor changed during authorization.")


def _check_invoice(source: Document, invoice: Document, payment: Document, currency: str) -> None:
    party_type, party_field, account_field = _INVOICE_PARTY[invoice.doctype]
    if (
        invoice.docstatus != 1
        or invoice.get("is_return")
        or invoice.get("company") != source.get("company")
        or source.get("party_type") != party_type
        or invoice.get(party_field) != source.get("party")
        or invoice.get(account_field) != source.get("receivable_payable_account")
        or invoice.get("currency") != currency
        or not _exact_number(invoice.get("conversion_rate"), 1)
        or payment.get("party_type") != party_type
    ):
        _fail("Payment matching target must be an ordinary same-party company-currency invoice.")
    if not frappe.has_permission(invoice.doctype, ptype="read", doc=invoice, user=frappe.session.user):
        raise frappe.PermissionError(_("Payment matching invoice is outside your permission scope."))
    for dimension in get_payment_entry_dimension_fields(payment):
        fieldname = dimension.fieldname
        if invoice.meta.has_field(fieldname):
            if payment.get(fieldname) != invoice.get(fieldname):
                _fail("Payment and invoice accounting dimensions differ.")
            if source.get(fieldname) and source.get(fieldname) != invoice.get(fieldname):
                _fail("Payment matching tool accounting scope differs from the invoice.")


def _expected_payload(
    payment: Document, allocations: tuple[_Allocation, ...], account: str
) -> dict[str, Any]:
    """Use only native in-memory amount/reference helpers; never run the native update helper."""
    expected = cast(PaymentEntry, frappe.get_doc(payment.as_dict()))
    for allocation in allocations:
        row = expected.append(
            "references",
            {
                "reference_doctype": allocation.invoice_type,
                "reference_name": allocation.invoice_name,
                "allocated_amount": allocation.amount,
                "exchange_rate": 1,
                "exchange_gain_loss": 0,
                "account": account,
                "dimensions": None,
            },
        )
        row.docstatus = 1
        expected.setup_party_account_field()
        expected.set_missing_values()
        expected.set_missing_ref_details(
            update_ref_details_only_for=[(allocation.invoice_type, allocation.invoice_name)]
        )
        if row.get("outstanding_amount"):
            row.outstanding_amount = flt(row.outstanding_amount) - allocation.amount
    expected.set_amounts()
    return approval_payload(expected)


def _prepare(source: Document, skip_ref_details_update_for_pe: bool) -> dict[str, _Capability]:
    allocation_rows = list(source.get("allocation") or [])
    if not any(row.get("reference_type") == "Payment Entry" for row in allocation_rows):
        return {}
    if skip_ref_details_update_for_pe:
        _fail("Queued Payment Entry reconciliation requires a separate approved route.")
    user = require_interactive_user(source, _ROLES, "write")
    if not allocation_rows:
        _fail("Payment matching requires allocations.")
    payment_names: set[str] = set()
    invoice_keys: set[tuple[str, str]] = set()
    for row in allocation_rows:
        if (
            row.get("reference_type") != "Payment Entry"
            or row.get("invoice_type") not in _INVOICE_PARTY
            or not row.get("reference_name")
            or not row.get("invoice_number")
            or row.get("reference_row")
        ):
            _fail("Mixed or unsupported payment matching allocations are not allowed.")
        _positive(row.get("allocated_amount"))
        payment_names.add(str(row.reference_name))
        invoice_keys.add((str(row.invoice_type), str(row.invoice_number)))
    payments = {name: _locked_document("Payment Entry", name) for name in sorted(payment_names)}
    invoices = {key: _locked_document(*key) for key in sorted(invoice_keys)}
    company = str(source.get("company") or "")
    currency = _company_currency(company)
    precision = frappe.get_precision(
        "Payment Reconciliation Allocation", "allocated_amount", currency=currency
    )
    for payment in payments.values():
        _check_payment(source, payment, user, currency)
    for (doctype, name), invoice in invoices.items():
        for row in allocation_rows:
            if row.invoice_type == doctype and row.invoice_number == name:
                _check_invoice(source, invoice, payments[str(row.reference_name)], currency)
    grouped: dict[str, list[_Allocation]] = defaultdict(list)
    payment_totals: dict[str, Decimal] = defaultdict(Decimal)
    invoice_totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in allocation_rows:
        payment = payments[str(row.reference_name)]
        invoice = invoices[(str(row.invoice_type), str(row.invoice_number))]
        amount = _currency_value(row.allocated_amount, precision)
        if amount <= 0:
            _fail("Payment matching requires a positive allocation.")
        name = str(payment.name)
        key = (str(invoice.doctype), str(invoice.name))
        available = _currency_value(payment.get("unallocated_amount"), precision)
        outstanding = _currency_value(invoice.get("outstanding_amount"), precision)
        if (
            _currency_value(row.get("unreconciled_amount"), precision) != available
            or _currency_value(row.get("amount"), precision) != available - payment_totals[name]
            or not _exact_number(row.get("exchange_rate"), 1)
            or not _exact_number(row.get("difference_amount"), 0)
            or row.get("is_advance")
            or row.get("currency") != currency
            or (row.get("cost_center") and row.get("cost_center") != payment.get("cost_center"))
        ):
            _fail("Payment matching allocation differs from current server values.")
        payment_totals[name] += amount
        invoice_totals[key] += amount
        if not 0 < payment_totals[name] <= available or not 0 < invoice_totals[key] <= outstanding:
            _fail("Payment matching exceeds available funds or invoice outstanding.")
        grouped[name].append(_Allocation(key[0], key[1], float(amount)))
    return {
        name: _Capability(
            source=source,
            user=user,
            payment=name,
            before_digest=get_approval_digest(payment),
            expected_digest=critical_digest(
                _expected_payload(
                    payment, tuple(grouped[name]), str(source.get("receivable_payable_account"))
                )
            ),
            allocations=tuple(grouped[name]),
        )
        for name, payment in payments.items()
    }


def _reference_identity_valid(
    doc: Document, previous: Document, allocations: tuple[_Allocation, ...]
) -> bool:
    old_rows = list(previous.get("references") or [])
    new_rows = list(doc.get("references") or [])
    if len(new_rows) != len(old_rows) + len(allocations):
        return False
    old_names = [row.get("name") for row in old_rows]
    if not all(old_names) or [row.get("name") for row in new_rows[: len(old_rows)]] != old_names:
        return False
    appended = new_rows[len(old_rows) :]
    generated_names = [row.get("name") for row in appended if row.get("name")]
    if len(set(generated_names)) != len(generated_names) or set(generated_names) & set(old_names):
        return False
    for row, allocation in zip(appended, allocations, strict=True):
        if (
            row.get("doctype") != "Payment Entry Reference"
            or row.get("parent") != doc.name
            or row.get("parentfield") != "references"
            or row.get("parenttype") != "Payment Entry"
            or int(row.get("docstatus") or 0) != 1
            or row.get("reference_doctype") != allocation.invoice_type
            or row.get("reference_name") != allocation.invoice_name
            or not _same_amount(row.get("allocated_amount"), allocation.amount)
        ):
            return False
    return True


def consume_matching_capability(doc: Document, previous: Document) -> None:
    """Consume an exact, private native matching capability for one Payment Entry save."""
    context = _context()
    name = str(doc.name or "")
    capability = context.capabilities.get(name) if context else None
    if (
        not context
        or not capability
        or capability.source is not context.source
        or capability.user != frappe.session.user
        or capability.payment != name
        or capability.before_digest != get_approval_digest(previous)
        or capability.expected_digest != critical_digest(approval_payload(doc))
        or not _reference_identity_valid(doc, previous, capability.allocations)
    ):
        _fail("Submitted Payment Entry reference changes require authorized native reconciliation.")
    assert context is not None
    del context.capabilities[name]


def _record_matching(capabilities: Mapping[str, _Capability]) -> None:
    for name, capability in capabilities.items():
        allocations = ", ".join(
            f"{allocation.invoice_type} {allocation.invoice_name}: {allocation.amount:.2f}"
            for allocation in capability.allocations
        )
        content = escape(
            f"Payment Reconciliation by {capability.user}: {allocations}",
            quote=True,
        )
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Payment Entry",
                "reference_name": name,
                "content": content,
            }
        ).insert(ignore_permissions=True)


class PaymentReconciliationWorkflowMixin:
    """Validate and scope synchronous native Payment Entry matching effects."""

    def reconcile_allocations(self, skip_ref_details_update_for_pe: bool = False) -> None:
        source = cast(Document, self)
        capabilities = _prepare(source, skip_ref_details_update_for_pe)
        if not capabilities:
            cast(Any, super()).reconcile_allocations(skip_ref_details_update_for_pe)
            return
        if _context():
            _fail("Nested Payment Entry reconciliation is not authorized.")
        context = _Context(source=source, capabilities=dict(capabilities))
        savepoint = f"pe_match_{uuid4().hex}"
        frappe.db.savepoint(savepoint)
        setattr(frappe.local, _CONTEXT_KEY, context)
        try:
            cast(Any, super()).reconcile_allocations(skip_ref_details_update_for_pe)
            if context.capabilities:
                _fail("Native Payment Entry reconciliation did not consume every allocation.")
            _record_matching(capabilities)
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            for name in capabilities:
                clear_document_cache("Payment Entry", name)
            raise
        finally:
            if getattr(frappe.local, _CONTEXT_KEY, None) is context:
                delattr(frappe.local, _CONTEXT_KEY)
