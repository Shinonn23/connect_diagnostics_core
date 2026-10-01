# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fail-closed controls for the native Journal Entry approval workflow."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import get_encryption_key

from connect_diagnostics_core.api.frappe.approval_controls import (
    critical_digest,
    require_distinct_actors,
    require_permission,
    resolve_user,
)

APPROVED_STATE = "Journal Entry Approved"
SUBMITTED_STATE = "Journal Entry Submitted"
CANCELLED_STATE = "Journal Entry Cancelled"
SCHEMA = "journal-entry-approval-v1"
_STATES = frozenset(
    {
        "Journal Entry Draft",
        "Journal Entry Pending Review",
        "Journal Entry Reviewed",
        "Journal Entry Approved",
        "Journal Entry Submitted",
        "Journal Entry Returned",
        "Journal Entry Rejected",
        "Journal Entry Cancelled",
    }
)
_EXCLUDED = frozenset(
    {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parenttype",
        "parentfield",
        "workflow_state",
        "approval_digest",
        "approval_critical_digest",
        "approval_digest_schema",
        "approval_maker_user",
        "approval_maker_at",
        "approval_checker_user",
        "approval_checker_at",
        "approval_approver_user",
        "approval_approver_at",
        "approval_checker_employee",
        "approval_checker_signature",
        "approval_approver_employee",
        "approval_approver_signature",
        "approval_submit_proof",
        "approval_cancel_proof",
        "approval_source_doctype",
        "approval_source_name",
        "approval_source_action",
        "approval_operation_id",
    }
)
PARENT_FIELDS = frozenset(
    {
        "company",
        "posting_date",
        "voucher_type",
        "finance_book",
        "multi_currency",
        "cheque_no",
        "cheque_date",
        "bill_no",
        "bill_date",
        "due_date",
        "clearance_date",
        "inter_company_journal_entry_reference",
        "reversal_of",
        "is_opening",
        "user_remark",
        "remark",
        "mode_of_payment",
        "payment_order",
        "stock_entry",
        "write_off_amount",
        "write_off_based_on",
        "tax_withholding_category",
        "tax_withholding_group",
        "apply_tds",
        "ignore_tax_withholding_threshold",
        "override_tax_withholding_entries",
        "for_payment",
        "process_deferred_accounting",
        "is_system_generated",
        "periodic_entry_difference_account",
        "for_all_stock_asset_accounts",
        "stock_asset_account",
        "party_not_required",
        "create_tax_invoice",
        "company_tax_address",
        "approval_source_doctype",
        "approval_source_name",
        "approval_source_action",
        "approval_operation_id",
        "approval_source_proof",
    }
)
ACCOUNT_FIELDS = frozenset(
    {
        "account",
        "party_type",
        "party",
        "account_currency",
        "exchange_rate",
        "debit_in_account_currency",
        "credit_in_account_currency",
        "debit",
        "credit",
        "reference_type",
        "reference_name",
        "reference_due_date",
        "reference_detail_no",
        "is_advance",
        "advance_voucher_type",
        "advance_voucher_no",
        "bank_account",
        "project",
        "cost_center",
        "user_remark",
        "against_account",
        "is_tax_withholding_account",
        "department",
        "territory",
        "customer",
        "supplier",
        "tax_base_amount",
        "tax_invoice_date",
        "tax_invoice_number",
        "petty_cash_holder",
        "petty_cash_holder_name",
        "is_petty_cash_account",
    }
)
TAX_DETAIL_FIELDS = frozenset(
    {
        "company_tax_address",
        "supplier",
        "customer",
        "party_name",
        "tax_invoice_number",
        "tax_invoice_date",
        "tax_base_amount",
        "tax_amount",
    }
)
NUMERIC_ACCOUNT_FIELDS = frozenset(
    {
        "exchange_rate",
        "debit_in_account_currency",
        "credit_in_account_currency",
        "debit",
        "credit",
        "tax_base_amount",
    }
)
NUMERIC_TAX_DETAIL_FIELDS = frozenset({"tax_base_amount", "tax_amount"})


def _plain(value: Any) -> Any:
    if isinstance(value, Document):
        return {str(k): _plain(v) for k, v in value.as_dict().items()}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _decimal(value: Any, precision: int) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-precision)), "f")


def _field_precision(doctype: str, fieldname: str) -> int:
    field = frappe.get_meta(doctype).get_field(fieldname)
    return int(field.precision or frappe.get_precision(doctype, fieldname) or 6) if field else 6


def approval_payload(doc: Document) -> dict[str, Any]:
    """Build the deterministic v1 posting payload, preserving child row order."""
    payload: dict[str, Any] = {}
    for key, value in doc.as_dict().items():
        if key in PARENT_FIELDS:
            payload[str(key)] = _plain(value)
    payload["accounts"] = []
    dynamic = _enabled_dimensions()
    account_meta = frappe.get_meta("Journal Entry Account")
    for row in doc.get("accounts") or []:
        item: dict[str, Any] = {}
        for key in ACCOUNT_FIELDS | dynamic:
            if account_meta.has_field(key):
                value = row.get(key)
                if key in NUMERIC_ACCOUNT_FIELDS:
                    value = _decimal(value, _field_precision("Journal Entry Account", key))
                item[key] = _plain(value)
        payload["accounts"].append(item)
    payload["tax_invoice_details"] = []
    tax_meta = frappe.get_meta("Journal Entry Tax Invoice Detail")
    for row in doc.get("tax_invoice_details") or []:
        item = {}
        for key in TAX_DETAIL_FIELDS:
            if tax_meta.has_field(key):
                value = row.get(key)
                if key in NUMERIC_TAX_DETAIL_FIELDS:
                    value = _decimal(value, _field_precision("Journal Entry Tax Invoice Detail", key))
                item[key] = _plain(value)
        payload["tax_invoice_details"].append(item)
    return payload


def _enabled_dimensions() -> frozenset[str]:
    try:
        return frozenset(
            str(row.get("fieldname"))
            for row in frappe.get_all("Accounting Dimension", filters={"disabled": 0}, fields=["fieldname"])
            if row.get("fieldname")
        )
    except Exception as exc:
        frappe.throw(_("Journal Entry accounting dimensions cannot be resolved: {0}").format(str(exc)))
        return frozenset()


def get_approval_digest(doc: Document) -> str:
    """Return the versioned digest required by Review, Approve, and Submit."""
    return "je-approval-v1:" + critical_digest(approval_payload(doc))


def approval_digest_schema(doc: Document | None = None) -> str:
    """Return canonical schema evidence; dimensions are resolved independently per request."""
    del doc
    dimensions: list[str] = []
    try:
        dimensions = sorted(_enabled_dimensions())
    except Exception as exc:
        frappe.throw(_("Journal Entry approval schema cannot be resolved: {0}").format(str(exc)))
    parent_meta = frappe.get_meta("Journal Entry")
    account_meta = frappe.get_meta("Journal Entry Account")
    tax_meta = frappe.get_meta("Journal Entry Tax Invoice Detail")
    installed_parent = sorted(field for field in PARENT_FIELDS if parent_meta.has_field(field))
    installed_account = sorted(field for field in ACCOUNT_FIELDS if account_meta.has_field(field))
    installed_tax = sorted(field for field in TAX_DETAIL_FIELDS if tax_meta.has_field(field))
    precision = {
        f"Journal Entry Account.{field}": _field_precision("Journal Entry Account", field)
        for field in sorted(NUMERIC_ACCOUNT_FIELDS & set(installed_account))
    }
    precision.update(
        {
            f"Journal Entry Tax Invoice Detail.{field}": _field_precision(
                "Journal Entry Tax Invoice Detail", field
            )
            for field in sorted(NUMERIC_TAX_DETAIL_FIELDS & set(installed_tax))
        }
    )
    return json.dumps(
        {
            "version": SCHEMA,
            "parent": installed_parent,
            "account": installed_account,
            "tax_invoice_detail": installed_tax,
            "dimensions": dimensions,
            "precision": precision,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    _clear(doc)
    doc.set("approval_maker_user", frappe.session.user)
    doc.set("approval_maker_at", frappe.utils.now_datetime())


def _signature(user: str) -> tuple[str, str]:
    row = frappe.db.get_value("Employee", {"user_id": user}, ["name", "approval_signature"], as_dict=True)
    if not row or not row.get("name") or not row.get("approval_signature"):
        frappe.throw(_("Each approval actor must have a linked Employee and approval signature."))
    return str(row.get("name")), str(row.get("approval_signature"))


def _clear(doc: Document) -> None:
    for field in (
        "approval_digest",
        "approval_critical_digest",
        "approval_digest_schema",
        "approval_checker_user",
        "approval_checker_at",
        "approval_checker_employee",
        "approval_checker_signature",
        "approval_approver_user",
        "approval_approver_at",
        "approval_approver_employee",
        "approval_approver_signature",
        "approval_submit_proof",
        "approval_cancel_proof",
        "approval_submit_actor",
        "approval_cancel_actor",
    ):
        doc.set(field, None)


def capture_checker_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    maker = str(doc.get("approval_maker_user") or "")
    if not maker:
        frappe.throw(_("Journal Entry Maker evidence is required before review."))
    require_distinct_actors(maker, frappe.session.user)
    employee, signature = _signature(frappe.session.user)
    digest = get_approval_digest(doc)
    doc.set("approval_digest", digest)
    doc.set("approval_critical_digest", digest)
    doc.set("approval_digest_schema", approval_digest_schema(doc))
    doc.set("approval_checker_user", frappe.session.user)
    doc.set("approval_checker_at", frappe.utils.now_datetime())
    doc.set("approval_checker_employee", employee)
    doc.set("approval_checker_signature", signature)


def capture_approver_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("approval_digest") != get_approval_digest(doc) or doc.get(
        "approval_digest_schema"
    ) != approval_digest_schema(doc):
        frappe.throw(_("The Journal Entry changed after review and must be reviewed again."))
    maker = str(doc.get("approval_maker_user") or "")
    if not maker:
        frappe.throw(_("Journal Entry Maker evidence is required before approval."))
    require_distinct_actors(maker, frappe.session.user, (str(doc.get("approval_checker_user") or ""),))
    employee, signature = _signature(frappe.session.user)
    doc.set("approval_approver_user", frappe.session.user)
    doc.set("approval_approver_at", frappe.utils.now_datetime())
    doc.set("approval_approver_employee", employee)
    doc.set("approval_approver_signature", signature)


def clear_approval_snapshots(doc: Document, method: str | None = None) -> None:
    del method
    _clear(doc)


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    if previous and previous.get("workflow_state") in {
        "Journal Entry Reviewed",
        APPROVED_STATE,
        "Journal Entry Rejected",
    }:
        if get_approval_digest(previous) != get_approval_digest(doc):
            frappe.throw(
                _("Critical Journal Entry fields cannot change after review. Return it for correction first.")
            )
    if doc.get("workflow_state") and doc.get("workflow_state") not in _STATES:
        frappe.throw(_("Journal Entry has an invalid approval state."))


def _marker(action: str, doc: Document, proof: str) -> bool:
    return getattr(frappe.flags, f"journal_entry_{action}_execution", None) == {
        "doctype": doc.doctype,
        "name": doc.name,
        "proof": proof,
    }


def _proof(
    action: str,
    doc: Document,
    source: str,
    target: str,
    digest: str,
    schema: str,
    actor: str,
) -> str:
    key = get_encryption_key().encode("utf-8")
    message = "|".join(
        (
            action,
            str(getattr(frappe.local, "site", "")),
            str(doc.doctype),
            str(doc.name),
            digest,
            schema,
            source,
            target,
            resolve_user(actor),
        )
    )
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _actor_has_permission(doc: Document, actor: str, permission: str) -> None:
    if not frappe.has_permission(doc.doctype, ptype=permission, doc=doc, user=actor):
        frappe.throw(
            _("The Workflow actor no longer has permission for this Journal Entry action."),
            frappe.PermissionError,
        )


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    try:
        validate_workflow(doc)
        persisted = cast(
            dict[str, Any] | None,
            frappe.db.get_value(
                "Journal Entry",
                doc.name,
                [
                    "workflow_state",
                    "approval_digest",
                    "approval_digest_schema",
                    "approval_submit_proof",
                    "approval_submit_actor",
                    "approval_maker_user",
                    "approval_checker_user",
                    "approval_approver_user",
                    "approval_checker_signature",
                    "approval_approver_signature",
                ],
                as_dict=True,
                for_update=True,
            ),
        )
        if not persisted:
            frappe.throw(_("Journal Entry approval is missing or stale."))
        assert persisted is not None
        proof = str(persisted.get("approval_submit_proof") or "")
        actor = str(persisted.get("approval_submit_actor") or "")
        schema = str(persisted.get("approval_digest_schema") or "")
        expected_proof = _proof(
            "submit", doc, APPROVED_STATE, SUBMITTED_STATE, get_approval_digest(doc), schema, actor
        )
        if (
            persisted.get("workflow_state") != APPROVED_STATE
            or doc.get("workflow_state") != SUBMITTED_STATE
            or persisted.get("approval_digest") != get_approval_digest(doc)
            or doc.get("approval_digest") != persisted.get("approval_digest")
            or doc.get("approval_digest_schema") != persisted.get("approval_digest_schema")
            or not proof
            or not hmac.compare_digest(proof, expected_proof)
            or not hmac.compare_digest(str(doc.get("approval_submit_proof") or ""), proof)
            or resolve_user(str(doc.get("approval_submit_actor") or "")) != resolve_user(actor)
        ):
            frappe.throw(_("Journal Entry approval is missing or stale."))
        if not _marker("submit", doc, proof):
            frappe.throw(_("Journal Entry submission must use the approved Workflow action."))
        if (
            persisted.get("approval_digest_schema") != approval_digest_schema(doc)
            or not persisted.get("approval_checker_signature")
            or not persisted.get("approval_approver_signature")
        ):
            frappe.throw(_("Current signed checker and approver evidence is required."))
        if not persisted.get("approval_maker_user"):
            frappe.throw(_("Current Maker evidence is required."))
        require_distinct_actors(
            str(persisted.get("approval_maker_user") or ""),
            str(persisted.get("approval_approver_user") or ""),
            (str(persisted.get("approval_checker_user") or ""),),
        )
        _actor_has_permission(doc, actor, "submit")
        frappe.db.set_value("Journal Entry", doc.name, "approval_submit_proof", None, update_modified=False)
        doc.set("approval_submit_proof", None)
    finally:
        frappe.flags.journal_entry_submit_execution = None


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        persisted = frappe.db.get_value(
            "Journal Entry",
            doc.name,
            [
                "workflow_state",
                "docstatus",
                "approval_digest",
                "approval_digest_schema",
                "approval_cancel_proof",
                "approval_cancel_actor",
            ],
            as_dict=True,
            for_update=True,
        )
        proof = str(persisted.get("approval_cancel_proof") if persisted else "")
        actor = str(persisted.get("approval_cancel_actor") if persisted else "")
        schema = str(persisted.get("approval_digest_schema") if persisted else "")
        expected_proof = _proof(
            "cancel",
            doc,
            SUBMITTED_STATE,
            CANCELLED_STATE,
            str(doc.get("approval_digest") or ""),
            schema,
            actor,
        )
        if (
            not persisted
            or persisted.get("workflow_state") != SUBMITTED_STATE
            or persisted.get("docstatus") != 1
            or doc.get("workflow_state") != CANCELLED_STATE
            or persisted.get("approval_digest") != doc.get("approval_digest")
            or doc.get("approval_digest_schema") != persisted.get("approval_digest_schema")
            or persisted.get("approval_digest_schema") != approval_digest_schema(doc)
            or not proof
            or not hmac.compare_digest(proof, expected_proof)
            or not hmac.compare_digest(str(doc.get("approval_cancel_proof") or ""), proof)
            or resolve_user(str(doc.get("approval_cancel_actor") or "")) != resolve_user(actor)
        ):
            frappe.throw(_("Journal Entry cancellation must use its native Workflow action."))
        if not _marker("cancel", doc, proof):
            frappe.throw(_("Journal Entry cancellation must use its native Workflow action."))
        _actor_has_permission(doc, actor, "cancel")
        frappe.db.set_value("Journal Entry", doc.name, "approval_cancel_proof", None, update_modified=False)
        doc.set("approval_cancel_proof", None)
    finally:
        frappe.flags.journal_entry_cancel_execution = None


def authorize_transition(doc: Document, action: str) -> None:
    """Mark a native Workflow transition as the only submit/cancel entry point."""
    if action not in {"submit", "cancel"}:
        frappe.throw(_("Journal Entry transition action is not allowed."))
    target = SUBMITTED_STATE if action == "submit" else CANCELLED_STATE
    source = APPROVED_STATE if action == "submit" else SUBMITTED_STATE
    if doc.get("workflow_state") != target:
        frappe.throw(_("Journal Entry transition has an invalid target state."))
    persisted = frappe.db.get_value(
        "Journal Entry",
        doc.name,
        [
            "workflow_state",
            "docstatus",
            "approval_digest",
            "approval_digest_schema",
            "approval_maker_user",
            "approval_checker_user",
            "approval_approver_user",
            "approval_checker_signature",
            "approval_approver_signature",
        ],
        as_dict=True,
        for_update=True,
    )
    if not persisted or persisted.get("workflow_state") != source:
        frappe.throw(_("Journal Entry transition has an invalid source state."))
    expected_status = 0 if action == "submit" else 1
    if persisted.get("docstatus") != expected_status:
        frappe.throw(_("Journal Entry transition has an invalid document status."))
    digest = get_approval_digest(doc)
    schema = approval_digest_schema(doc)
    if persisted.get("approval_digest") != digest or persisted.get("approval_digest_schema") != schema:
        frappe.throw(_("Journal Entry approval is missing or stale."))
    if not persisted.get("approval_checker_signature") or not persisted.get("approval_approver_signature"):
        frappe.throw(_("Current signed checker and approver evidence is required."))
    if not persisted.get("approval_maker_user"):
        frappe.throw(_("Current Maker evidence is required."))
    require_distinct_actors(
        str(persisted.get("approval_maker_user") or ""),
        str(persisted.get("approval_approver_user") or ""),
        (str(persisted.get("approval_checker_user") or ""),),
    )
    actor = resolve_user(frappe.session.user)
    require_permission(doc, action)
    if action == "cancel":
        from connect_diagnostics_core.api.erpnext.journal_entry_generators import (
            validate_generated_source_cancel,
        )

        validate_generated_source_cancel(doc)
    fieldname = "approval_submit_proof" if action == "submit" else "approval_cancel_proof"
    actor_field = "approval_submit_actor" if action == "submit" else "approval_cancel_actor"
    proof = _proof(action, doc, source, target, digest, schema, actor)
    doc.set(fieldname, proof)
    doc.set(actor_field, actor)
    if hasattr(doc, "db_set"):
        frappe.db.set_value(
            "Journal Entry",
            doc.name,
            {fieldname: proof, actor_field: actor},
            update_modified=False,
        )
    setattr(
        frappe.flags,
        f"journal_entry_{action}_execution",
        {"doctype": doc.doctype, "name": doc.name, "proof": proof},
    )


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    authorize_transition(doc, "submit")


def authorize_cancel_transition(doc: Document, method: str | None = None) -> None:
    del method
    authorize_transition(doc, "cancel")


class JournalEntryWorkflowMixin:
    """Small extension point retaining the installed ERPNext controller behavior."""

    def before_submit(self: Any) -> None:
        super().before_submit()

    def before_cancel(self: Any) -> None:
        super().before_cancel()

    def submit(self: Any) -> Any:
        context = getattr(frappe.flags, "journal_entry_draft_context", None)
        if context:
            from connect_diagnostics_core.api.erpnext.journal_entry_generators import (
                save_trusted_generated_draft,
            )

            return save_trusted_generated_draft(cast(Document, self), context)
        return super().submit()

    def save(self: Any, *args: Any, **kwargs: Any) -> Any:
        context = getattr(frappe.flags, "journal_entry_draft_context", None)
        if not context:
            return super().save(*args, **kwargs)
        from connect_diagnostics_core.api.erpnext.journal_entry_generators import (
            _seal_source_provenance,
            prepare_trusted_generated_draft,
            set_deferred_operation_key,
        )

        set_deferred_operation_key(self, context)
        existing = prepare_trusted_generated_draft(cast(Document, self), context)
        if existing:
            return existing
        result = super().save(*args, **kwargs)
        _seal_source_provenance(self)
        return result
