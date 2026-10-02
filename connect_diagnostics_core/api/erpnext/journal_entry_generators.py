# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Adapters for native ERPNext Journal Entry generators.

These functions deliberately create *draft* Journal Entries.  They are intended
to be registered by the activation task through Frappe's documented
``override_whitelisted_methods`` hook; importing this module has no side effects.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import frappe
from frappe import _
from frappe.utils.password import get_encryption_key


def save_trusted_generated_draft(doc: Any, context: dict[str, Any]) -> Any:
    """Persist a generator-created JE as draft for JournalEntryWorkflowMixin."""
    if not context.get("source_doctype") or not context.get("source_name"):
        frappe.throw(_("Generated Journal Entry provenance is incomplete."))
    if doc.docstatus:
        frappe.throw(_("Generated Journal Entry must be a draft before approval."))
    source_doctype = str(context["source_doctype"])
    source_name = str(context["source_name"])
    source_action = str(context.get("source_action") or "generated")
    operation_id = _operation_id(doc, context)
    existing = _find_existing_draft(source_doctype, source_name, operation_id)
    if existing and existing.name != doc.name:
        if not doc.is_new():
            frappe.delete_doc("Journal Entry", doc.name, force=True, ignore_permissions=True)
        return existing
    _draft_provenance(
        doc,
        source_doctype=source_doctype,
        source_name=source_name,
        source_action=source_action,
        operation_id=operation_id,
    )
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
    _seal_source_provenance(doc)
    return doc


def prepare_trusted_generated_draft(doc: Any, context: dict[str, Any]) -> Any | None:
    """Attach stable source provenance before a native generator's first save."""
    source_doctype = str(context.get("source_doctype") or "")
    source_name = str(context.get("source_name") or "")
    source_action = str(context.get("source_action") or "generated")
    if not source_doctype or not source_name:
        frappe.throw(_("Generated Journal Entry provenance is incomplete."))
    operation_id = _operation_id(doc, context)
    existing = _find_existing_draft(source_doctype, source_name, operation_id)
    if existing and existing.name != doc.name:
        return existing
    _draft_provenance(
        doc,
        source_doctype=source_doctype,
        source_name=source_name,
        source_action=source_action,
        operation_id=operation_id,
    )
    return None


def _operation_id(doc: Any, context: dict[str, Any]) -> str:
    """Return an identity from immutable source coordinates and an explicit key."""
    del doc
    coordinates = (
        str(context.get("source_doctype") or ""),
        str(context.get("source_name") or ""),
        str(context.get("source_action") or "generated"),
        str(context.get("operation_id") or ""),
    )
    return hashlib.sha256("\x1f".join(coordinates).encode("utf-8")).hexdigest()


def set_deferred_operation_key(doc: Any, context: dict[str, Any]) -> None:
    """Bind one deferred source-item/period operation before native save."""
    if context.get("source_action") != "process_deferred_accounting":
        return
    references = sorted(
        {
            "|".join(
                (
                    str(row.get("reference_type") or ""),
                    str(row.get("reference_name") or ""),
                    str(row.get("reference_detail_no") or ""),
                )
            )
            for row in (doc.get("accounts") or [])
            if row.get("reference_name") or row.get("reference_detail_no")
        }
    )
    operation_coordinates = (
        str(context.get("operation_base_id") or ""),
        str(doc.get("posting_date") or ""),
        *references,
    )
    context["operation_id"] = hashlib.sha256("\x1f".join(operation_coordinates).encode("utf-8")).hexdigest()


def _validate_source_provenance(doc: Any) -> tuple[str, str, str, str]:
    source_doctype = str(doc.get("approval_source_doctype") or "")
    source_name = str(doc.get("approval_source_name") or "")
    source_action = str(doc.get("approval_source_action") or "")
    operation_id = str(doc.get("approval_operation_id") or "")
    expected = _source_proof(source_doctype, source_name, source_action, operation_id, doc.name)
    if (
        not source_doctype
        or not source_name
        or not hmac.compare_digest(str(doc.get("approval_source_proof") or ""), expected)
    ):
        frappe.throw(_("Generated Journal Entry provenance is invalid."))
    return source_doctype, source_name, source_action, operation_id


def validate_generated_source_cancel(doc: Any) -> None:
    """Validate a linked AVA before native JE cancellation starts."""
    if doc.get("approval_source_action") != "asset_value_adjustment":
        return
    source_doctype, source_name, _action, _operation = _validate_source_provenance(doc)
    if source_doctype != "Asset Value Adjustment":
        frappe.throw(_("Asset Value Adjustment Journal Entry provenance is invalid."))
    frappe.db.get_value(source_doctype, source_name, "name", for_update=True)
    source = frappe.get_doc(source_doctype, source_name)
    if source.docstatus != 1 or source.journal_entry != doc.name:
        frappe.throw(_("The linked Asset Value Adjustment is not ready for cancellation."))


def complete_generated_source_cancel(doc: Any, method: str | None = None) -> None:
    """Cancel a linked AVA only after native JE cancellation has completed."""
    del method
    if doc.get("approval_source_action") != "asset_value_adjustment":
        return
    source_doctype, source_name, _action, _operation = _validate_source_provenance(doc)
    frappe.db.get_value(source_doctype, source_name, "name", for_update=True)
    source = frappe.get_doc(source_doctype, source_name)
    if (
        source_doctype != "Asset Value Adjustment"
        or source.docstatus != 1
        or source.journal_entry != doc.name
    ):
        frappe.throw(_("The linked Asset Value Adjustment is not ready for cancellation."))
    frappe.flags.journal_entry_asset_value_adjustment_cancel = source.name
    try:
        source.flags.ignore_permissions = True
        source.cancel()
    finally:
        frappe.flags.pop("journal_entry_asset_value_adjustment_cancel", None)


def reconcile_approved_bank_journal_entry(doc: Any, method: str | None = None) -> None:
    """Allocate a Bank Transaction only after native JE submission succeeds.

    This is a post-submit hook candidate.  It fails closed unless the JE carries
    complete app-owned provenance and the source still exists; approval guards are
    owned by ``journal_entry_workflow`` and run before this handler.
    """
    del method
    if doc.doctype != "Journal Entry" or doc.docstatus != 1:
        return
    if not all(
        frappe.get_meta("Journal Entry").has_field(field)
        for field in ("approval_source_doctype", "approval_source_name", "approval_source_action")
    ):
        return
    if (
        doc.get("approval_source_doctype") != "Bank Transaction"
        or doc.get("approval_source_action") != "bank_reconciliation"
    ):
        return
    bank_transaction_name = str(doc.get("approval_source_name") or "")
    expected_proof = _source_proof(
        "Bank Transaction", bank_transaction_name, "bank_reconciliation", "", doc.name
    )
    if not hmac.compare_digest(str(doc.get("approval_source_proof") or ""), expected_proof):
        frappe.throw(_("Bank Reconciliation Journal Entry provenance is invalid."))
    if not bank_transaction_name or not frappe.db.exists("Bank Transaction", bank_transaction_name):
        frappe.throw(_("Approved Bank Reconciliation Journal Entry has no valid Bank Transaction source."))
    bank_transaction = frappe.db.get_value(
        "Bank Transaction",
        bank_transaction_name,
        ["name", "deposit", "withdrawal"],
        as_dict=True,
        for_update=True,
    )
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers

    amount = float(bank_transaction.deposit or bank_transaction.withdrawal or 0)
    reconcile_vouchers(
        bank_transaction_name,
        frappe.as_json([{"payment_doctype": "Journal Entry", "payment_name": doc.name, "amount": amount}]),
        is_new_voucher=True,
    )


def complete_approved_generated_source(doc: Any, method: str | None = None) -> None:
    """Apply source-side effects only after the approved JE has posted native GL."""
    reconcile_approved_bank_journal_entry(doc, method)
    if doc.doctype != "Journal Entry" or doc.docstatus != 1:
        return
    if doc.get("approval_source_action") != "asset_value_adjustment":
        return
    source_doctype, source_name, _action, _operation = _validate_source_provenance(doc)
    if source_doctype != "Asset Value Adjustment":
        frappe.throw(_("Asset Value Adjustment Journal Entry provenance is invalid."))
    frappe.db.get_value(source_doctype, source_name, "name", for_update=True)
    source = frappe.get_doc(source_doctype, source_name)
    if source.docstatus != 1 or source.journal_entry != doc.name:
        frappe.throw(_("Approved Journal Entry is not linked to its Asset Value Adjustment."))
    source.update_asset()
    from erpnext.assets.doctype.asset_activity.asset_activity import add_asset_activity

    add_asset_activity(
        source.asset,
        _("Asset's value adjusted after approved Journal Entry {0}").format(
            frappe.utils.get_link_to_form("Journal Entry", doc.name)
        ),
    )


def _set_if_present(doc: Any, fieldname: str, value: Any) -> None:
    """Set an app-owned provenance field only when the installed schema has it."""
    if frappe.get_meta(doc.doctype).has_field(fieldname):
        doc.set(fieldname, value)


def _source_proof(
    source_doctype: str,
    source_name: str,
    source_action: str,
    operation_id: str,
    journal_entry_name: str,
) -> str:
    key = get_encryption_key().encode("utf-8")
    message = "|".join(
        (
            str(getattr(frappe.local, "site", "")),
            source_doctype,
            source_name,
            source_action,
            operation_id,
            journal_entry_name,
        )
    )
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _draft_provenance(
    doc: Any,
    *,
    source_doctype: str,
    source_name: str,
    source_action: str,
    operation_id: str | None = None,
) -> Any:
    _set_if_present(doc, "approval_source_doctype", source_doctype)
    _set_if_present(doc, "approval_source_name", source_name)
    _set_if_present(doc, "approval_source_action", source_action)
    if not operation_id:
        frappe.throw(_("Generated Journal Entry operation ID is required."))
    _set_if_present(doc, "approval_operation_id", operation_id)
    return doc


def seal_trusted_generated_draft(doc: Any) -> None:
    """Seal prepared provenance after native insertion, without saving or committing."""
    _seal_source_provenance(doc)


def _seal_source_provenance(doc: Any) -> None:
    proof = _source_proof(
        str(doc.get("approval_source_doctype") or ""),
        str(doc.get("approval_source_name") or ""),
        str(doc.get("approval_source_action") or ""),
        str(doc.get("approval_operation_id") or ""),
        str(doc.name),
    )
    doc.set("approval_source_proof", proof)
    doc.db_set("approval_source_proof", proof, update_modified=False)


def _find_existing_draft(
    source_doctype: str, source_name: str, operation_id: str | None = None
) -> Any | None:
    filters: dict[str, Any] = {
        "docstatus": 0,
        "approval_source_doctype": source_doctype,
        "approval_source_name": source_name,
    }
    if operation_id:
        filters["approval_operation_id"] = operation_id
    if not frappe.get_meta("Journal Entry").has_field("approval_source_doctype"):
        return None
    name = frappe.db.get_value("Journal Entry", filters, "name", for_update=True)
    return frappe.get_doc("Journal Entry", name) if name else None


@frappe.whitelist()
def create_journal_entry_bts(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Create the native Bank Reconciliation Tool JE as a draft.

    The Bank Transaction is intentionally not allocated here.  Allocation is a
    posting side effect and must happen only after the native JE Workflow submits
    the approved JE.
    """
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
        create_journal_entry_bts as native_create_journal_entry_bts,
    )

    bank_transaction_name = str(kwargs.get("bank_transaction_name") or (args[0] if args else ""))
    if not bank_transaction_name:
        frappe.throw(_("Bank Transaction is required."))
    frappe.has_permission("Bank Transaction", "read", bank_transaction_name, throw=True)
    frappe.has_permission("Bank Transaction", "write", bank_transaction_name, throw=True)
    frappe.has_permission("Journal Entry", "create", throw=True)
    # Lock the source before checking provenance.  This serializes retries and
    # prevents two requests from both generating an allocation candidate.
    frappe.db.get_value("Bank Transaction", bank_transaction_name, "name", for_update=True)
    if not frappe.db.exists("Bank Transaction", bank_transaction_name):
        frappe.throw(_("Bank Transaction does not exist."))
    existing = _find_existing_draft("Bank Transaction", bank_transaction_name)
    if existing:
        return {
            "bank_transaction": bank_transaction_name,
            "journal_entry": existing.name,
            "pending_approval": True,
        }

    # ``allow_edit`` is the documented native route that returns an unsaved JE.
    kwargs["allow_edit"] = True
    if args:
        kwargs["bank_transaction_name"] = args[0]
        args = args[1:]
    journal_entry = native_create_journal_entry_bts(*args, **kwargs)
    if isinstance(journal_entry, dict):
        journal_entry = frappe.get_doc(journal_entry)
    if journal_entry.docstatus != 0:
        frappe.throw(_("The Bank Reconciliation generator must return a draft Journal Entry."))
    _draft_provenance(
        journal_entry,
        source_doctype="Bank Transaction",
        source_name=bank_transaction_name,
        source_action="bank_reconciliation",
        operation_id=hashlib.sha256(
            f"Bank Transaction:{bank_transaction_name}:bank_reconciliation".encode()
        ).hexdigest(),
    )
    journal_entry.insert()
    _seal_source_provenance(journal_entry)
    return {
        "bank_transaction": bank_transaction_name,
        "journal_entry": journal_entry.name,
        "pending_approval": True,
    }


@frappe.whitelist()
def create_petty_cash_journal_entry(
    posting_date: str,
    petty_cash_holder: str,
    from_account: str,
    to_account: str,
    amount: float,
    type: str,
    operation_id: str,
) -> dict[str, Any]:
    """Create an idempotent pending Thailand petty-cash JE.

    No holder balance is updated: that balance remains derived from submitted GL
    entries.  ``operation_id`` is mandatory so client retries reuse one draft.
    """
    if type not in {"topup", "withdraw"}:
        frappe.throw(_("Petty cash operation must be topup or withdraw."))
    if not operation_id:
        frappe.throw(_("Operation ID is required."))
    try:
        UUID(operation_id)
    except (ValueError, AttributeError, TypeError):
        frappe.throw(_("Operation ID must be a valid UUID."))
    try:
        amount_decimal = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        frappe.throw(_("Amount must be a positive finite number."))
    if (
        not math.isfinite(float(amount_decimal))
        or amount_decimal <= 0
        or Decimal(str(amount)) != amount_decimal
    ):
        frappe.throw(_("Amount must be a positive number with at most 2 decimal places."))
    amount = float(amount_decimal)
    try:
        date.fromisoformat(str(posting_date))
    except (TypeError, ValueError):
        frappe.throw(_("Posting date must be a valid date."))
    frappe.has_permission("Petty Cash Holder", "write", petty_cash_holder, throw=True)
    frappe.has_permission("Journal Entry", "create", throw=True)
    frappe.db.get_value("Petty Cash Holder", petty_cash_holder, "name", for_update=True)
    holder = frappe.get_doc("Petty Cash Holder", petty_cash_holder)
    if holder.disabled:
        frappe.throw(_("Petty Cash Holder is disabled."))
    expected_from = (
        holder.cash_bank_account_for_petty_cash_top_up if type == "topup" else holder.petty_cash_account
    )
    expected_to = (
        holder.petty_cash_account if type == "topup" else holder.cash_bank_account_for_petty_cash_withdraw
    )
    if from_account != expected_from or to_account != expected_to:
        frappe.throw(_("Petty cash accounts do not match the holder configuration."))
    account_rows = frappe.db.get_all(
        "Account",
        filters={"name": ["in", [from_account, to_account]]},
        fields=["name", "company", "account_currency", "disabled", "is_group"],
    )
    accounts = {row.name: row for row in account_rows}
    if len(accounts) != 2 or from_account == to_account:
        frappe.throw(_("Petty cash accounts must be two distinct existing accounts."))
    if any(row.disabled or row.is_group for row in accounts.values()):
        frappe.throw(_("Petty cash accounts must be enabled ledger accounts."))
    companies = {row.company for row in accounts.values()}
    if len(companies) != 1:
        frappe.throw(_("Petty cash accounts must belong to the same company."))
    account_currency = next(iter(accounts.values())).account_currency
    if any(row.account_currency != account_currency for row in accounts.values()):
        frappe.throw(_("Petty cash accounts must use the same currency."))
    stable_operation_id = hashlib.sha256(
        f"Petty Cash Holder:{petty_cash_holder}:{type}:{operation_id}".encode()
    ).hexdigest()
    existing = _find_existing_draft("Petty Cash Holder", petty_cash_holder, stable_operation_id)
    if existing:
        return {"name": existing.name, "pending_approval": True}
    journal_entry = frappe.new_doc("Journal Entry")
    journal_entry.update(
        {"voucher_type": "Cash Entry", "posting_date": posting_date, "company": next(iter(companies))}
    )
    debit = {"account": to_account, "debit_in_account_currency": amount, "credit_in_account_currency": 0}
    credit = {"account": from_account, "debit_in_account_currency": 0, "credit_in_account_currency": amount}
    if type == "topup":
        debit["petty_cash_holder"] = petty_cash_holder
    else:
        credit["petty_cash_holder"] = petty_cash_holder
    journal_entry.append("accounts", debit)
    journal_entry.append("accounts", credit)
    _draft_provenance(
        journal_entry,
        source_doctype="Petty Cash Holder",
        source_name=petty_cash_holder,
        source_action=type,
        operation_id=stable_operation_id,
    )
    journal_entry.insert()
    _seal_source_provenance(journal_entry)
    return {"name": journal_entry.name, "pending_approval": True}
