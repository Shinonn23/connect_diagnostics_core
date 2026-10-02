# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Approval evidence and native boundaries for whole-Asset disposal."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

import frappe
from erpnext.accounts.doctype.journal_entry.journal_entry import JournalEntry
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from connect_diagnostics_core.api.frappe import approval_controls

DOCTYPE = "Asset Disposal Request"
MAKER_ROLE = "Asset Administrator"
REVIEWER_ROLE = "Accounts User"
APPROVER_ROLE = "C-Level Approver"
STATE_DRAFT = "Asset Disposal Draft"
STATE_REVIEW = "Asset Disposal Pending Review"
STATE_APPROVAL = "Asset Disposal Pending Approval"
STATE_APPROVED = "Asset Disposal Approved"
STATE_SUBMITTED = "Asset Disposal Submitted"
STATE_RETURNED = "Asset Disposal Returned"
STATE_REJECTED = "Asset Disposal Rejected"
STATE_ABANDONED = "Asset Disposal Abandoned"
STATE_RESET_REVIEW = "Asset Disposal Reset Pending Review"
STATE_RESET_APPROVAL = "Asset Disposal Reset Pending Approval"
STATE_RESET_APPROVED = "Asset Disposal Reset Approved"
STATE_EXECUTION_ABANDONED = "Asset Disposal Execution Abandoned"

_REQUEST_GRANTS = "_connect_asset_disposal_request_grants"
_NATIVE_GRANTS = "_connect_asset_disposal_native_grants"
_REASON_GRANT = "_connect_asset_disposal_reason_grant"
_RESET_EXECUTION = "_connect_asset_disposal_reset_execution"
_SALE_TAX_CONTEXT = "_connect_asset_disposal_sale_tax_context"
_MUTABLE_REQUEST = frozenset(
    {
        "purpose",
        "reason",
        "asset",
        "request_date",
        "disposal_date",
        "customer",
        "posting_date",
        "item_code",
        "sell_qty",
        "rate",
        "currency",
        "taxes_template",
    }
)
_SERVER_REQUEST = frozenset(
    {
        "company",
        "asset_quantity",
        "maker_user",
        "maker_at",
        "reviewer_user",
        "reviewer_at",
        "approver_user",
        "approver_at",
        "approval_digest_schema",
        "approval_digest",
        "approved_intent_json",
        "asset_baseline_json",
        "sale_candidate_projection",
        "disposal_gl_projection",
        "return_reason",
        "rejection_reason",
        "reset_maker_user",
        "reset_maker_at",
        "reset_reviewer_user",
        "reset_reviewer_at",
        "reset_approver_user",
        "reset_approver_at",
        "reset_reason",
        "reset_digest",
        "reset_return_reason",
        "disposal_status",
        "sales_invoice",
        "disposal_journal_entry",
        "generated_journal_entries",
        "execution_id",
        "execution_phase",
        "execute_started_at",
        "execute_completed_at",
        "stage1_schedule_snapshot_json",
        "stage1_schedule_snapshot_digest",
        "stage1_operation_id",
        "final_schedule_snapshot_json",
        "final_schedule_snapshot_digest",
        "reset_completed_at",
    }
)
_METADATA = frozenset(
    {
        "name",
        "doctype",
        "parent",
        "parenttype",
        "parentfield",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
        "workflow_state",
        "status",
    }
)


@dataclass
class _RequestGrant:
    doc: Any
    state: str
    fields: frozenset[str]
    consumed: bool = False


@dataclass
class _NativeGrant:
    document: Any
    request: str
    asset: str
    phase: str
    operation_id: str
    consumed: bool = False
    sale_consumed: bool = False


@dataclass
class _SaleTaxContext:
    request: Any
    invoice: Any | None = None


def _request_grants() -> list[_RequestGrant]:
    value = getattr(frappe.local, _REQUEST_GRANTS, None)
    if value is None:
        value = []
        setattr(frappe.local, _REQUEST_GRANTS, value)
    return value


def authorize_request_update(doc: Any, state: str, fields: set[str]) -> None:
    """Allow precisely one server-created state/evidence delta on this object."""
    if doc.doctype != DOCTYPE or not state or not fields <= _SERVER_REQUEST | {"workflow_state"}:
        frappe.throw(_("Invalid Asset Disposal Request authorization."))
    _request_grants().append(_RequestGrant(doc, state, frozenset(fields | {"workflow_state"})))


def _consume_request_grant(doc: Any, state: str, changed: set[str]) -> None:
    grants = _request_grants()
    for index, grant in enumerate(grants):
        if grant.doc is doc and grant.state == state and changed <= grant.fields and not grant.consumed:
            grant.consumed = True
            grants.pop(index)
            if not grants:
                delattr(frappe.local, _REQUEST_GRANTS)
            return
    frappe.throw(_("Asset Disposal Request update requires its exact approved action."))


@contextmanager
def native_disposal_capability(request: Any, phase: str, operation_id: str) -> Iterator[None]:
    """Scope native ERPNext effects to the current synchronous Execute call."""
    if request.doctype != DOCTYPE or request.docstatus != 1 or not operation_id:
        frappe.throw(_("Asset disposal execution authorization is invalid."))
    grant = _NativeGrant(request, request.name, request.asset, phase, operation_id)
    stack = getattr(frappe.local, _NATIVE_GRANTS, None)
    if stack is None:
        stack = []
        setattr(frappe.local, _NATIVE_GRANTS, stack)
    stack.append(grant)
    try:
        yield None
    finally:
        stack.remove(grant)
        if not stack:
            delattr(frappe.local, _NATIVE_GRANTS)


def _native_grant(asset: str, phase: str | None = None) -> _NativeGrant | None:
    stack = getattr(frappe.local, _NATIVE_GRANTS, ())
    if not stack:
        return None
    grant = stack[-1]
    if grant.asset == asset and (phase is None or grant.phase == phase):
        return grant
    return None


@contextmanager
def _sale_tax_context(request: Any, invoice: Any | None = None) -> Iterator[_SaleTaxContext]:
    if getattr(frappe.local, _SALE_TAX_CONTEXT, None):
        frappe.throw(_("Asset disposal Sale tax selection is already active."))
    context = _SaleTaxContext(request, invoice)
    setattr(frappe.local, _SALE_TAX_CONTEXT, context)
    try:
        yield context
    finally:
        delattr(frappe.local, _SALE_TAX_CONTEXT)


def _explicit_no_template_invoice(invoice: Any) -> bool:
    context = getattr(frappe.local, _SALE_TAX_CONTEXT, None)
    if not context or context.request.taxes_template:
        return False
    request = context.request
    items = invoice.get("items") or []
    if (
        invoice.doctype != "Sales Invoice"
        or invoice.company != request.company
        or len(items) != 1
        or items[0].asset != request.asset
        or not items[0].is_fixed_asset
        or flt(items[0].qty) != flt(request.sell_qty)
    ):
        return False
    return context.invoice is None or context.invoice is invoice


class AssetDisposalSalesInvoiceMixin:
    """Keep an explicit blank disposal template while native item taxes still apply."""

    def set_taxes(self: Any) -> None:
        if _explicit_no_template_invoice(self):
            return
        super().set_taxes()

    def set_missing_lead_customer_details(self: Any, for_validate: bool = False) -> None:
        if not _explicit_no_template_invoice(self):
            super().set_missing_lead_customer_details(for_validate=for_validate)
            return
        taxes = list(self.get("taxes") or [])
        template = self.get("taxes_and_charges")
        super().set_missing_lead_customer_details(for_validate=for_validate)
        if not template:
            self.taxes_and_charges = None
            self.set("taxes", taxes)


def _canonical(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalized(value: Any) -> Any:
    return json.loads(_canonical(value))


def _projection(value: Any) -> Any:
    """Retain every native document field except database identity metadata."""
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping):
        return {str(key): _projection(item) for key, item in value.items() if key not in _METADATA}
    if isinstance(value, list):
        return [_projection(item) for item in value]
    return value


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _request_payload(doc: Any) -> dict[str, Any]:
    return {key: doc.get(key) for key in sorted(_MUTABLE_REQUEST | {"company", "asset_quantity"})}


def _asset_stable(asset: Any) -> dict[str, Any]:
    """Bind native configuration while separating allowed carrying-value changes."""
    body = _projection(asset)
    for field in ("value_after_depreciation", "status", "depr_entry_posting_status"):
        body.pop(field, None)
    for native_row, row in zip(
        asset.get("finance_books") or [], body.get("finance_books") or [], strict=True
    ):
        row["name"] = native_row.name
        row.pop("value_after_depreciation", None)
        row.pop("total_number_of_booked_depreciations", None)
    return body


def _asset_values(asset: Any) -> dict[str, Any]:
    return {
        "value_after_depreciation": asset.get("value_after_depreciation"),
        "finance_books": [
            {"finance_book": row.finance_book, "value_after_depreciation": row.value_after_depreciation}
            for row in (asset.get("finance_books") or [])
        ],
    }


def _native_stage1_rates(asset: Any) -> list[dict[str, Any]]:
    """Predict native WDV/DD rate writes using ERPNext's own rate method."""
    result = []
    for row in asset.get("finance_books") or []:
        before = row.rate_of_depreciation
        after = before
        if (
            asset.calculate_depreciation
            and row.depreciation_method in {"Written Down Value", "Double Declining Balance"}
            and flt(row.value_after_depreciation) > flt(row.expected_value_after_useful_life)
        ):
            after = flt(asset.get_depreciation_rate(row), row.precision("rate_of_depreciation"))
        result.append({"name": row.name, "finance_book": row.finance_book, "before": before, "after": after})
    return result


def _actual_stage1_rates(asset: Any, expected: list[dict[str, Any]]) -> None:
    rows = {row.name: row for row in asset.get("finance_books") or []}
    if set(rows) != {item["name"] for item in expected}:
        frappe.throw(_("Asset Finance Book identity changed during depreciation staging."))
    for item in expected:
        row = rows[item["name"]]
        if row.finance_book != item["finance_book"] or flt(row.rate_of_depreciation) != flt(item["after"]):
            frappe.throw(_("Native Asset depreciation rate differed from the approved stage operation."))


def _lock_asset(name: str, *, wait: bool = True) -> Any:
    permission_error = _("You do not have permission to access this Asset.")
    if not name:
        frappe.throw(permission_error, frappe.PermissionError)

    # Check permission by name before locking or loading any Asset data. Keep
    # the failure generic so a guessed name cannot disclose existence/company.
    if not frappe.has_permission("Asset", "read", name):
        frappe.throw(permission_error, frappe.PermissionError)

    company = frappe.db.get_value("Asset", name, "company", for_update=True, wait=wait)
    if not company or not _has_explicit_asset_company_scope(company):
        frappe.throw(permission_error, frappe.PermissionError)

    # Reload all approved fields and child rows with a current locking read. The
    # company probe above establishes the lock but does not refresh an RR snapshot.
    asset = frappe.get_doc("Asset", name, for_update=True)
    if not frappe.has_permission("Asset", "read", asset):
        frappe.throw(permission_error, frappe.PermissionError)
    return asset


def _has_explicit_asset_company_scope(company: str) -> bool:
    """Require an explicit Company User Permission applicable to Asset."""
    rows = frappe.get_all(
        "User Permission",
        filters={
            "user": frappe.session.user,
            "allow": "Company",
            "for_value": company,
        },
        fields=["applicable_for", "apply_to_all_doctypes"],
    )
    return any(not row.applicable_for or row.applicable_for == "Asset" for row in rows)


def _validate_asset(doc: Any, asset: Any) -> None:
    if asset.docstatus != 1 or asset.status in {"Cancelled", "Sold", "Scrapped", "Capitalized"}:
        frappe.throw(_("Asset is not eligible for disposal."))
    if doc.get("company") and doc.company != asset.company:
        frappe.throw(_("Asset company changed during approval."))
    if doc.get("asset_quantity") and flt(doc.asset_quantity) != flt(asset.asset_quantity):
        frappe.throw(_("Asset quantity changed during approval."))
    if doc.purpose == "Sale":
        if flt(doc.sell_qty) != flt(asset.asset_quantity) or doc.item_code != asset.item_code:
            frappe.throw(_("Sale must contain the entire Asset and its native Item."))
        if not doc.customer or not doc.posting_date or flt(doc.rate) < 0:
            frappe.throw(_("Asset sale customer, date, and nonnegative rate are required."))
        if getdate(doc.posting_date) != getdate(doc.disposal_date):
            frappe.throw(_("Asset sale posting and disposal dates must match."))
    elif doc.purpose not in {"Scrap", "Write-off"}:
        frappe.throw(_("Asset disposal purpose is invalid."))
    if not doc.reason or not doc.disposal_date:
        frappe.throw(_("Asset disposal reason and date are required."))


def _active_schedule_snapshot(asset: Any) -> list[dict[str, Any]]:
    from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
        get_asset_depr_schedule_doc,
    )

    schedules: list[dict[str, Any]] = []
    for row in asset.get("finance_books") or []:
        schedule = get_asset_depr_schedule_doc(asset.name, "Active", row.finance_book)
        schedules.append(
            {
                "finance_book": row.finance_book,
                "name": schedule.name if schedule else None,
                "docstatus": schedule.docstatus if schedule else None,
                "rows": [
                    {
                        key: item.get(key)
                        for key in (
                            "name",
                            "idx",
                            "schedule_date",
                            "depreciation_amount",
                            "accumulated_depreciation_amount",
                            "journal_entry",
                            "make_depreciation_entry",
                            "shift",
                        )
                    }
                    for item in (schedule.get("depreciation_schedule") or [])
                ]
                if schedule
                else [],
            }
        )
    return schedules


def _expected_final_schedule_rows(asset: Any, disposal_date: str) -> list[list[dict[str, Any]]]:
    """Calculate native final rows without changing the active schedules."""
    from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
        get_temp_depr_schedule_doc,
    )

    expected: list[list[dict[str, Any]]] = []
    current = _active_schedule_snapshot(asset)
    for book in asset.get("finance_books") or []:
        matching = [row for row in current if (row["finance_book"] or "") == (book.finance_book or "")]
        if len(matching) != 1:
            frappe.throw(_("Asset Finance Book schedule is ambiguous before disposal."))
        if (
            not asset.calculate_depreciation
            or not matching[0]["name"]
            or flt(book.value_after_depreciation) <= flt(book.expected_value_after_useful_life)
        ):
            rows = matching[0]["rows"]
        else:
            temporary = get_temp_depr_schedule_doc(asset, book, disposal_date)
            rows = [
                {
                    key: item.get(key)
                    for key in (
                        "idx",
                        "schedule_date",
                        "depreciation_amount",
                        "accumulated_depreciation_amount",
                        "journal_entry",
                        "make_depreciation_entry",
                        "shift",
                    )
                }
                for item in temporary.get("depreciation_schedule") or []
            ]
        expected.append([{key: value for key, value in row.items() if key != "name"} for row in rows])
    return _normalized(expected)


def _sale_candidate(doc: Any) -> Any:
    from erpnext.assets.doctype.asset.asset import make_sales_invoice

    with _sale_tax_context(doc) as tax_context:
        invoice = make_sales_invoice(doc.asset, doc.item_code, doc.company, doc.sell_qty)
        tax_context.invoice = invoice
        invoice.customer = doc.customer
        invoice.posting_date = doc.posting_date
        invoice.currency = doc.currency
        invoice.taxes_and_charges = doc.taxes_template or None
        invoice.set("taxes", [])
        invoice.set_missing_values()
        invoice.set_taxes_and_charges()
        item = invoice.items[0]
        item.rate = doc.rate
        invoice.calculate_taxes_and_totals()
        previous_action = invoice.get("_action")
        invoice._action = "save"
        try:
            invoice.validate()
        finally:
            if previous_action is None:
                delattr(invoice, "_action")
            else:
                invoice._action = previous_action
        if len(invoice.items) != 1 or item.asset != doc.asset or flt(item.qty) != flt(doc.sell_qty):
            frappe.throw(_("Native Asset sale candidate changed its Asset or quantity."))
        if flt(item.rate, item.precision("rate")) != flt(doc.rate, item.precision("rate")):
            frappe.throw(_("Native Asset sale rate changed during validation."))
        return invoice


def _forecast_disposal_gl(doc: Any, asset: Any, invoice: Any | None, *, forecast: bool = True) -> list[Any]:
    from erpnext.assets.doctype.asset.depreciation import (
        get_gl_entries_on_asset_disposal,
        get_value_after_depreciation_on_disposal_date,
    )

    forecast_asset = copy.deepcopy(asset)
    if forecast:
        for row in forecast_asset.get("finance_books") or []:
            row.value_after_depreciation = get_value_after_depreciation_on_disposal_date(
                asset.name, str(doc.disposal_date), row.finance_book
            )
        if forecast_asset.get("finance_books"):
            forecast_asset.value_after_depreciation = forecast_asset.finance_books[0].value_after_depreciation
    item = invoice.items[0] if invoice else None
    if item:
        entries = get_gl_entries_on_asset_disposal(
            forecast_asset, item.base_net_amount, item.finance_book, date=getdate(doc.disposal_date)
        )
    else:
        # Match native create_journal_entry_for_scrap's positional call exactly.
        entries = get_gl_entries_on_asset_disposal(forecast_asset, getdate(doc.disposal_date))
    return [_projection(row) for row in entries]


def _scrap_journal_entry_preflight(doc: Any, entries: list[Any]) -> None:
    """Run native draft validation without creating the eventual Scrap voucher."""
    je = cast(JournalEntry, frappe.new_doc("Journal Entry"))
    je.voucher_type = "Asset Disposal"
    je.naming_series = frappe.get_cached_value("Company", doc.company, "series_for_depreciation_entry")
    je.posting_date = doc.disposal_date
    je.company = doc.company
    je.remark = f"Scrap Entry for asset {doc.asset}"
    for entry in entries:
        je.append("accounts", {**entry, "reference_type": "Asset", "reference_name": doc.asset})
    previous_action = je.get("_action")
    je._action = "save"
    try:
        je.validate()
    finally:
        if previous_action is None:
            delattr(je, "_action")
        else:
            je._action = previous_action


def _intent(doc: Any, asset: Any) -> dict[str, Any]:
    invoice = _sale_candidate(doc) if doc.purpose == "Sale" else None
    disposal_gl = _forecast_disposal_gl(doc, asset, invoice)
    if doc.purpose in {"Scrap", "Write-off"}:
        _scrap_journal_entry_preflight(doc, disposal_gl)
    return {
        "schema": "asset-disposal-v1",
        "request": _request_payload(doc),
        "asset_stable": _asset_stable(asset),
        "sale_candidate": _projection(invoice) if invoice else None,
        "disposal_gl": disposal_gl,
    }


def _baseline(asset: Any) -> dict[str, Any]:
    return {
        "stable": _asset_stable(asset),
        "values": _asset_values(asset),
        "schedules": _active_schedule_snapshot(asset),
        "status": asset.status,
        "disposal_date": asset.disposal_date,
        "journal_entry_for_scrap": asset.journal_entry_for_scrap,
    }


def _changed_fields(previous: Any, doc: Any) -> set[str]:
    return {
        field.fieldname
        for field in doc.meta.fields
        if field.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
        and _canonical(_projection(previous.get(field.fieldname)))
        != _canonical(_projection(doc.get(field.fieldname)))
    }


def validate_request(doc: Any) -> None:
    if doc.is_new():
        if any(
            doc.get(field) for field in _SERVER_REQUEST - {"company", "asset_quantity", "disposal_status"}
        ):
            frappe.throw(_("Asset Disposal Request server fields cannot be supplied by the client."))
        if doc.get("disposal_status") not in {None, "", "Not Executed"}:
            frappe.throw(_("Asset Disposal Request must start as Not Executed."))
        if doc.workflow_state not in {None, "", STATE_DRAFT}:
            frappe.throw(_("Asset Disposal Request must start in Draft."))
        if doc.docstatus:
            frappe.throw(_("Asset Disposal Request cannot be inserted as submitted."))
        asset = _lock_asset(doc.asset)
        _validate_asset(doc, asset)
        doc.company = asset.company
        doc.asset_quantity = asset.asset_quantity
        return
    previous = doc.get_doc_before_save()
    if previous is None:
        frappe.throw(_("Asset Disposal Request history is unavailable."))
    if int(previous.docstatus or 0) == 1 and int(doc.docstatus or 0) == 1:
        # Frappe invokes before_update_after_submit after validate. The former
        # consumes the one-use grant for a submitted document exactly once.
        return
    changed = _changed_fields(previous, doc)
    if not changed:
        return
    if previous.workflow_state == STATE_DRAFT and doc.workflow_state == STATE_DRAFT:
        if changed <= _MUTABLE_REQUEST | {"company", "asset_quantity"}:
            asset = _lock_asset(doc.asset)
            doc.company = asset.company
            doc.asset_quantity = asset.asset_quantity
            _validate_asset(doc, asset)
            return
    if previous.workflow_state == STATE_RETURNED and doc.workflow_state == STATE_RETURNED:
        if changed <= _MUTABLE_REQUEST - {"asset"}:
            _validate_asset(doc, _lock_asset(doc.asset))
            return
    _consume_request_grant(doc, doc.workflow_state, changed)


def validate_request_submit(doc: Any) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.workflow_state != STATE_APPROVED or doc.workflow_state != STATE_SUBMITTED:
        frappe.throw(_("Asset disposal requires the approved Workflow Submit action."))
    if not doc.approval_digest or doc.approval_digest != _digest(json.loads(doc.approved_intent_json)):
        frappe.throw(_("Asset disposal approval seal is invalid."))
    asset = _lock_asset(doc.asset)
    _validate_asset(doc, asset)
    if _normalized(_intent(doc, asset)) != json.loads(doc.approved_intent_json):
        frappe.throw(_("Asset disposal approved financial payload is stale."))
    approval_controls.require_distinct_actors(doc.maker_user, doc.approver_user, (doc.reviewer_user,))


def validate_submitted_request_update(doc: Any) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.docstatus != 1 or doc.docstatus != 1:
        frappe.throw(_("Submitted Asset Disposal Request history is invalid."))
    changed = _changed_fields(previous, doc)
    if changed:
        _consume_request_grant(doc, doc.workflow_state, changed)


def validate_request_delete(doc: Any) -> None:
    if doc.docstatus or doc.workflow_state not in {None, "", STATE_DRAFT}:
        frappe.throw(_("Reviewed Asset Disposal Request history cannot be deleted."))


def _actor(doc: Any, role: str, maker: str = "", previous: tuple[str, ...] = ()) -> str:
    if role == MAKER_ROLE and not maker:
        return approval_controls.require_interactive_user(doc, (role,))
    return approval_controls.require_interactive_actor(doc, (role,), maker, previous).user


def capture_maker(doc: Any) -> None:
    user = _actor(doc, MAKER_ROLE)
    asset = _lock_asset(doc.asset)
    _validate_asset(doc, asset)
    _assert_unreserved(doc.asset, doc.name)
    doc.company = asset.company
    doc.asset_quantity = asset.asset_quantity
    doc.maker_user = user
    doc.maker_at = now_datetime()
    for field in (
        "reviewer_user",
        "reviewer_at",
        "approver_user",
        "approver_at",
        "approval_digest",
        "approved_intent_json",
        "asset_baseline_json",
        "sale_candidate_projection",
        "disposal_gl_projection",
    ):
        doc.set(field, None)
    authorize_request_update(
        doc,
        STATE_REVIEW,
        {
            "company",
            "asset_quantity",
            "maker_user",
            "maker_at",
            "reviewer_user",
            "reviewer_at",
            "approver_user",
            "approver_at",
            "approval_digest",
            "approved_intent_json",
            "asset_baseline_json",
            "sale_candidate_projection",
            "disposal_gl_projection",
        },
    )


def capture_review(doc: Any) -> None:
    user = _actor(doc, REVIEWER_ROLE, doc.maker_user)
    asset = _lock_asset(doc.asset)
    _validate_asset(doc, asset)
    intent = _intent(doc, asset)
    baseline = _baseline(asset)
    doc.reviewer_user = user
    doc.reviewer_at = now_datetime()
    doc.approval_digest_schema = "asset-disposal-v1"
    doc.approval_digest = _digest(intent)
    doc.approved_intent_json = _canonical(intent)
    doc.asset_baseline_json = _canonical(baseline)
    doc.sale_candidate_projection = _canonical(intent["sale_candidate"])
    doc.disposal_gl_projection = _canonical(intent["disposal_gl"])
    authorize_request_update(
        doc,
        STATE_APPROVAL,
        {
            "reviewer_user",
            "reviewer_at",
            "approval_digest_schema",
            "approval_digest",
            "approved_intent_json",
            "asset_baseline_json",
            "sale_candidate_projection",
            "disposal_gl_projection",
        },
    )


def capture_approval(doc: Any) -> None:
    user = _actor(doc, APPROVER_ROLE, doc.maker_user, (doc.reviewer_user,))
    asset = _lock_asset(doc.asset)
    if _normalized(_intent(doc, asset)) != json.loads(doc.approved_intent_json):
        frappe.throw(_("Asset disposal accounting preview changed after review."))
    doc.approver_user = user
    doc.approver_at = now_datetime()
    authorize_request_update(doc, STATE_APPROVED, {"approver_user", "approver_at"})


def capture_submit_authorization(doc: Any) -> None:
    _actor(doc, REVIEWER_ROLE, doc.maker_user, (doc.approver_user,))
    authorize_request_update(doc, STATE_SUBMITTED, set())


def _assert_unreserved(asset: str, own_request: str | None = None) -> None:
    # capture_maker calls this only after the Asset mutex. A locking read is
    # required here because an RR snapshot can predate another request's commit.
    reservations = frappe.db.get_values(
        DOCTYPE,
        filters={
            "asset": asset,
            "workflow_state": (
                "in",
                [
                    STATE_REVIEW,
                    STATE_APPROVAL,
                    STATE_APPROVED,
                    STATE_SUBMITTED,
                    STATE_RETURNED,
                    STATE_RESET_REVIEW,
                    STATE_RESET_APPROVAL,
                    STATE_RESET_APPROVED,
                ],
            ),
        },
        fieldname=["name", "disposal_status"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if any(
        row.name != own_request and row.disposal_status not in {"Closed", "Abandoned/Released"}
        for row in reservations
    ):
        frappe.throw(_("Asset is already reserved by another disposal request."))


def _persisted_state(doc: Any) -> str:
    value = frappe.db.get_value(DOCTYPE, doc.name, "workflow_state", for_update=True)
    if not value:
        frappe.throw(_("Asset disposal Workflow source state is missing."))
    return str(value)


def _reason_for(doc: Any, action: str) -> str:
    proof = getattr(frappe.local, _REASON_GRANT, None)
    if (
        not isinstance(proof, dict)
        or proof.get("name") != doc.name
        or proof.get("action") != action
        or proof.get("user") != frappe.session.user
        or proof.get("consumed")
    ):
        frappe.throw(_("Asset disposal decision reason requires its exact Desk action."))
    assert isinstance(proof, dict)
    proof["consumed"] = True
    return str(proof["reason"])


@frappe.whitelist()
def apply_reasoned_action(name: str, action: str, reason: str) -> dict[str, Any]:
    """Apply one native Workflow transition with a transaction-bound reason."""
    if action not in {"Return", "Reject", "Request Abandonment Reset", "Return Abandonment Reset"}:
        frappe.throw(_("Asset disposal action does not accept a reason."))
    reason = str(reason or "").strip()
    if not reason or len(reason) > 2000:
        frappe.throw(_("Asset disposal decision reason must contain 1 to 2000 characters."))
    if not frappe.has_permission(DOCTYPE, "write", name) or getattr(frappe.local, _REASON_GRANT, None):
        frappe.throw(_("Asset disposal reason action is not authorized."))
    from frappe.model.workflow import apply_workflow

    proof = {"name": name, "action": action, "reason": reason, "user": frappe.session.user, "consumed": False}
    setattr(frappe.local, _REASON_GRANT, proof)
    try:
        doc = apply_workflow(frappe.get_doc(DOCTYPE, name), action)
        if not proof["consumed"]:
            frappe.throw(_("Asset disposal reason was not consumed by its Workflow transition."))
        return {"data": {"name": doc.name, "state": doc.workflow_state}, "message": ""}
    finally:
        delattr(frappe.local, _REASON_GRANT)


def capture_return(doc: Any) -> None:
    state = _persisted_state(doc)
    if state == STATE_REVIEW:
        _actor(doc, REVIEWER_ROLE, doc.maker_user)
    elif state == STATE_APPROVAL:
        _actor(doc, APPROVER_ROLE, doc.maker_user, (doc.reviewer_user,))
    else:
        frappe.throw(_("Asset disposal cannot be returned from this state."))
    reason = _reason_for(doc, "Return")
    if not reason:
        frappe.throw(_("A return reason is required."))
    doc.return_reason = reason
    for field in (
        "reviewer_user",
        "reviewer_at",
        "approver_user",
        "approver_at",
        "approval_digest",
        "approved_intent_json",
        "asset_baseline_json",
        "sale_candidate_projection",
        "disposal_gl_projection",
    ):
        doc.set(field, None)
    authorize_request_update(
        doc,
        STATE_RETURNED,
        {
            "return_reason",
            "reviewer_user",
            "reviewer_at",
            "approver_user",
            "approver_at",
            "approval_digest",
            "approved_intent_json",
            "asset_baseline_json",
            "sale_candidate_projection",
            "disposal_gl_projection",
        },
    )


def capture_reject(doc: Any) -> None:
    _actor(doc, APPROVER_ROLE, doc.maker_user, (doc.reviewer_user,))
    reason = _reason_for(doc, "Reject")
    if not reason:
        frappe.throw(_("A rejection reason is required."))
    doc.rejection_reason = reason
    authorize_request_update(doc, STATE_REJECTED, {"rejection_reason"})


def capture_resubmit(doc: Any) -> None:
    capture_maker(doc)


def capture_abandon(doc: Any) -> None:
    if _persisted_state(doc) not in {STATE_DRAFT, STATE_RETURNED} or doc.docstatus:
        frappe.throw(_("Only a Draft or Returned request can be abandoned before execution."))
    _actor(doc, MAKER_ROLE)
    _lock_asset(doc.asset)
    authorize_request_update(doc, STATE_ABANDONED, set())


def _child_statuses(doc: Any) -> list[tuple[Any, int, str]]:
    result = []
    for child in doc.get("generated_journal_entries") or []:
        value = frappe.db.get_value(
            "Journal Entry",
            child.journal_entry,
            ["docstatus", "workflow_state"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not value:
            frappe.throw(_("A linked disposal Journal Entry is missing."))
        result.append((child, int(value.docstatus or 0), str(value.workflow_state or "")))
    return result


def _require_reset_preflight(doc: Any) -> None:
    if doc.docstatus != 1 or doc.disposal_status not in {"Depreciation Pending", "Ready to Dispose"}:
        frappe.throw(_("Asset disposal reset is available only after depreciation staging."))
    if doc.sales_invoice or doc.disposal_journal_entry:
        frappe.throw(_("Asset disposal cannot be reset after final disposal has begun."))
    for child, status, state in _child_statuses(doc):
        if child.stage != "pre_disposal_depreciation":
            frappe.throw(_("Unexpected final Journal Entry prevents reset."))
        if status == 1:
            continue
        if status == 0 and state == "Journal Entry Rejected":
            pending = frappe.db.exists(
                "Workflow Action",
                {
                    "reference_doctype": "Journal Entry",
                    "reference_name": child.journal_entry,
                    "status": "Open",
                },
            )
            if pending:
                frappe.throw(_("Rejected Journal Entry still has an open Workflow Action."))
            continue
        frappe.throw(_("All staged Journal Entries must finish before reset approval."))


def capture_reset_maker(doc: Any) -> None:
    _require_reset_preflight(doc)
    user = _actor(doc, MAKER_ROLE)
    reason = _reason_for(doc, "Request Abandonment Reset")
    if not reason:
        frappe.throw(_("An Asset disposal reset reason is required."))
    doc.reset_maker_user = user
    doc.reset_maker_at = now_datetime()
    doc.reset_reason = reason
    doc.reset_digest = _digest(
        {
            "approval_digest": doc.approval_digest,
            "reason": reason,
            "stage1_operation_id": doc.stage1_operation_id,
        }
    )
    authorize_request_update(
        doc, STATE_RESET_REVIEW, {"reset_maker_user", "reset_maker_at", "reset_reason", "reset_digest"}
    )


def capture_reset_review(doc: Any) -> None:
    _require_reset_preflight(doc)
    user = _actor(doc, REVIEWER_ROLE, doc.reset_maker_user)
    doc.reset_reviewer_user = user
    doc.reset_reviewer_at = now_datetime()
    authorize_request_update(doc, STATE_RESET_APPROVAL, {"reset_reviewer_user", "reset_reviewer_at"})


def capture_reset_approval(doc: Any) -> None:
    _require_reset_preflight(doc)
    user = _actor(doc, APPROVER_ROLE, doc.reset_maker_user, (doc.reset_reviewer_user,))
    if doc.reset_digest != _digest(
        {
            "approval_digest": doc.approval_digest,
            "reason": doc.reset_reason,
            "stage1_operation_id": doc.stage1_operation_id,
        }
    ):
        frappe.throw(_("Asset disposal reset approval is stale."))
    doc.reset_approver_user = user
    doc.reset_approver_at = now_datetime()
    authorize_request_update(doc, STATE_RESET_APPROVED, {"reset_approver_user", "reset_approver_at"})


def capture_reset_return(doc: Any) -> None:
    state = _persisted_state(doc)
    if state == STATE_RESET_REVIEW:
        _actor(doc, REVIEWER_ROLE, doc.reset_maker_user)
    elif state == STATE_RESET_APPROVAL:
        _actor(doc, APPROVER_ROLE, doc.reset_maker_user, (doc.reset_reviewer_user,))
    else:
        frappe.throw(_("Asset disposal reset cannot be returned from this state."))
    reason = _reason_for(doc, "Return Abandonment Reset")
    if not reason:
        frappe.throw(_("A reset return reason is required."))
    doc.reset_return_reason = reason
    for field in (
        "reset_maker_user",
        "reset_maker_at",
        "reset_reviewer_user",
        "reset_reviewer_at",
        "reset_approver_user",
        "reset_approver_at",
        "reset_reason",
        "reset_digest",
    ):
        doc.set(field, None)
    authorize_request_update(
        doc,
        STATE_SUBMITTED,
        {
            "reset_return_reason",
            "reset_maker_user",
            "reset_maker_at",
            "reset_reviewer_user",
            "reset_reviewer_at",
            "reset_approver_user",
            "reset_approver_at",
            "reset_reason",
            "reset_digest",
        },
    )


def capture_reset_authorization(doc: Any) -> None:
    """Bind native terminal Workflow action to completed synchronous reset."""
    proof = getattr(frappe.local, _RESET_EXECUTION, None)
    if (
        not isinstance(proof, dict)
        or proof.get("name") != doc.name
        or proof.get("user") != frappe.session.user
        or proof.get("consumed")
        or doc.workflow_state != STATE_EXECUTION_ABANDONED
        or doc.disposal_status != "Abandoned/Released"
        or not doc.reset_completed_at
    ):
        frappe.throw(_("Asset disposal reset Workflow action has no native reset proof."))
    assert isinstance(proof, dict)
    proof["consumed"] = True
    authorize_request_update(doc, STATE_EXECUTION_ABANDONED, set())


def _asset_references(je: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(row.reference_name)
                for row in (je.get("accounts") or [])
                if row.reference_type == "Asset" and row.reference_name
            }
        )
    )


def _generated_operation_id(grant: _NativeGrant, je: Any) -> str:
    coordinates = (
        grant.request,
        grant.operation_id,
        grant.phase,
        str(je.voucher_type or ""),
        str(je.posting_date or ""),
        str(je.finance_book or ""),
        *(_asset_references(je)),
        _canonical(
            [
                {
                    "account": row.account,
                    "reference_type": row.reference_type,
                    "reference_name": row.reference_name,
                    "debit_in_account_currency": row.debit_in_account_currency,
                    "credit_in_account_currency": row.credit_in_account_currency,
                }
                for row in (je.get("accounts") or [])
            ]
        ),
    )
    return hashlib.sha256("\x1f".join(coordinates).encode("utf-8")).hexdigest()


def before_insert_generated_disposal_journal_entry(je: Any, method: str | None = None) -> None:
    """Stamp only a native generator's exact synchronous draft."""
    del method
    references = _asset_references(je)
    if not references:
        return
    grant = _native_grant(references[0])
    if not grant:
        if je.voucher_type == "Asset Disposal" or any(_active_request_for_asset(name) for name in references):
            frappe.throw(_("Asset disposal Journal Entry requires its approved source operation."))
        return
    if len(references) != 1 or references[0] != grant.asset:
        frappe.throw(_("Generated disposal Journal Entry Asset reference is invalid."))
    if grant.phase not in {"stage1", "final"}:
        frappe.throw(_("Asset disposal reset cannot generate a Journal Entry."))
    if grant.phase == "stage1" and je.voucher_type != "Depreciation Entry":
        frappe.throw(_("Depreciation staging generated an unexpected Journal Entry."))
    if grant.phase == "final" and je.voucher_type != "Asset Disposal":
        frappe.throw(_("Final disposal generated an unexpected Journal Entry."))
    if je.company != grant.document.company or int(je.docstatus or 0) != 0:
        frappe.throw(_("Generated disposal Journal Entry company or status is invalid."))
    from connect_diagnostics_core.api.erpnext import journal_entry_generators

    context = {
        "source_doctype": DOCTYPE,
        "source_name": grant.request,
        "source_action": "asset_disposal_" + grant.phase,
        "operation_id": _generated_operation_id(grant, je),
    }
    existing = journal_entry_generators.prepare_trusted_generated_draft(je, context)
    if existing:
        frappe.throw(_("Duplicate native Asset disposal Journal Entry operation."))


def after_insert_generated_disposal_journal_entry(je: Any, method: str | None = None) -> None:
    """Seal native provenance and link its exact draft in this transaction."""
    del method
    references = _asset_references(je)
    if len(references) != 1:
        return
    grant = _native_grant(references[0])
    if not grant:
        return
    if je.approval_source_doctype != DOCTYPE or je.approval_source_name != grant.request:
        frappe.throw(_("Generated Asset disposal Journal Entry lost its source identity."))
    from connect_diagnostics_core.api.erpnext import journal_entry_generators, journal_entry_workflow

    journal_entry_generators.seal_trusted_generated_draft(je)
    draft_payload_digest = journal_entry_workflow.get_approval_digest(je)
    request = grant.document
    if any(
        row.journal_entry == je.name or row.operation_id == je.approval_operation_id
        for row in request.get("generated_journal_entries") or []
    ):
        frappe.throw(_("Duplicate Asset disposal Journal Entry link."))
    request.append(
        "generated_journal_entries",
        {
            "journal_entry": je.name,
            "operation_id": je.approval_operation_id,
            "kind": "depreciation" if je.voucher_type == "Depreciation Entry" else "asset_disposal",
            "stage": "pre_disposal_depreciation" if grant.phase == "stage1" else "final_disposal",
            "finance_book": je.finance_book,
            "posting_date": je.posting_date,
            "source_proof": je.approval_source_proof,
            "draft_payload_digest": draft_payload_digest,
        },
    )
    authorize_request_update(request, request.workflow_state, {"generated_journal_entries"})
    request.save(ignore_permissions=True)


def _active_request_for_asset(asset: str) -> str | None:
    # Depreciation and reservation paths serialize on the Asset row. Once that
    # mutex has been acquired, use a current read so an older REPEATABLE READ
    # snapshot cannot miss a reservation committed while it waited for the
    # Asset lock.
    names = frappe.db.get_values(
        DOCTYPE,
        filters={
            "asset": asset,
            "workflow_state": (
                "in",
                [
                    STATE_REVIEW,
                    STATE_APPROVAL,
                    STATE_APPROVED,
                    STATE_SUBMITTED,
                    STATE_RETURNED,
                    STATE_RESET_REVIEW,
                    STATE_RESET_APPROVAL,
                    STATE_RESET_APPROVED,
                ],
            ),
        },
        fieldname=["name", "disposal_status"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    names = [row.name for row in names if row.disposal_status not in {"Closed", "Abandoned/Released"}]
    if len(names) > 1:
        frappe.throw(_("Asset has conflicting disposal reservations."))
    return str(names[0]) if names else None


def _protected_request_for_asset(asset: str) -> str | None:
    """Read current disposal protection without using a repeatable-read snapshot."""
    rows = frappe.db.get_values(
        DOCTYPE,
        {
            "asset": asset,
            "workflow_state": (
                "in",
                [
                    STATE_REVIEW,
                    STATE_APPROVAL,
                    STATE_APPROVED,
                    STATE_SUBMITTED,
                    STATE_RETURNED,
                    STATE_RESET_REVIEW,
                    STATE_RESET_APPROVAL,
                    STATE_RESET_APPROVED,
                ],
            ),
        },
        ["name", "disposal_status"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    protected = [row.name for row in rows if row.disposal_status != "Abandoned/Released"]
    if len(protected) > 1:
        frappe.throw(_("Asset has conflicting disposal protections."))
    return str(protected[0]) if protected else None


def _lock_request(name: str) -> Any:
    if not name or not frappe.db.get_value(DOCTYPE, name, "name", for_update=True):
        frappe.throw(_("Asset Disposal Request does not exist."))
    # FOR UPDATE is a current read under MariaDB repeatable-read isolation. A caller that
    # waited behind another Execute must observe its committed operation result here.
    return frappe.get_doc(DOCTYPE, name, for_update=True)


def _require_execute_actor(doc: Any) -> None:
    approval_controls.require_interactive_user(doc, (REVIEWER_ROLE,))
    if doc.docstatus != 1 or doc.workflow_state != STATE_SUBMITTED:
        frappe.throw(_("Asset disposal has no current execution authorization."))
    if doc.approval_digest != _digest(json.loads(doc.approved_intent_json)):
        frappe.throw(_("Asset disposal approval seal is invalid."))


def _verify_intent(doc: Any, asset: Any) -> None:
    _validate_asset(doc, asset)
    approved = json.loads(doc.approved_intent_json)
    if _normalized(_request_payload(doc)) != approved["request"]:
        frappe.throw(_("Asset disposal request changed after approval."))
    approved_stable = copy.deepcopy(approved["asset_stable"])
    if doc.stage1_schedule_snapshot_json:
        snapshot = json.loads(doc.stage1_schedule_snapshot_json)
        if (
            hashlib.sha256(doc.stage1_schedule_snapshot_json.encode()).hexdigest()
            != doc.stage1_schedule_snapshot_digest
        ):
            frappe.throw(_("Asset depreciation stage snapshot is invalid."))
        expected_rows = {row["name"]: row for row in approved_stable.get("finance_books") or []}
        for rate in snapshot["rate_deltas"]:
            row = expected_rows.get(rate["name"])
            if (
                not row
                or row.get("finance_book") != rate["finance_book"]
                or flt(row.get("rate_of_depreciation")) != flt(rate["before"])
            ):
                frappe.throw(_("Asset depreciation rate delta has no approved baseline."))
            assert row is not None
            row["rate_of_depreciation"] = rate["after"]
    if _normalized(_asset_stable(asset)) != approved_stable:
        frappe.throw(_("Asset disposal configuration changed after approval."))
    invoice = _sale_candidate(doc) if doc.purpose == "Sale" else None
    if (invoice and _normalized(_projection(invoice))) != approved["sale_candidate"]:
        frappe.throw(_("Native Asset sale candidate changed after approval."))


def _verify_before_stage(doc: Any, asset: Any) -> None:
    _verify_intent(doc, asset)
    baseline = json.loads(doc.asset_baseline_json)
    if _normalized(_baseline(asset)) != baseline:
        frappe.throw(_("Asset carrying value or schedule changed after approval."))
    if doc.purpose in {"Scrap", "Write-off"}:
        from erpnext.assets.doctype.asset.depreciation import validate_asset_for_scrap

        validate_asset_for_scrap(asset, getdate(doc.disposal_date))
        _scrap_journal_entry_preflight(doc, _forecast_disposal_gl(doc, asset, None))


def _stage1_operation_id(request: Any) -> str:
    return hashlib.sha256((request.name + "\x1fstage1\x1f" + request.approval_digest).encode()).hexdigest()


def _final_operation_id(request: Any) -> str:
    return hashlib.sha256((request.name + "\x1ffinal\x1f" + request.approval_digest).encode()).hexdigest()


def _recorded_operation_result(value: str, operation_id: str, result_key: str) -> dict[str, Any]:
    """Read an exact persisted response envelope from a server-owned snapshot."""
    try:
        snapshot = json.loads(value)
    except (TypeError, ValueError):
        frappe.throw(_("Asset disposal operation result is invalid."))
    result = snapshot.get(result_key) if isinstance(snapshot, dict) else None
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("operation_id") != operation_id
        or not isinstance(result, dict)
        or set(result) != {"data", "message"}
        or not isinstance(result.get("data"), dict)
        or not isinstance(result.get("message"), str)
        or result.get("message") != ""
    ):
        frappe.throw(_("Asset disposal operation identity does not match its recorded result."))
    assert isinstance(result, dict)
    return result


def _verify_stage1_retry(request: Any, asset: Any, operation_id: str) -> dict[str, Any]:
    if (
        request.docstatus != 1
        or request.workflow_state != STATE_SUBMITTED
        or request.disposal_status
        not in {"Depreciation Pending", "Ready to Dispose", "Disposal Accounting Pending", "Closed"}
        or request.stage1_operation_id != operation_id
        or not request.stage1_schedule_snapshot_json
        or hashlib.sha256(request.stage1_schedule_snapshot_json.encode()).hexdigest()
        != request.stage1_schedule_snapshot_digest
    ):
        frappe.throw(_("Asset depreciation stage retry does not match its recorded operation."))
    result = _recorded_operation_result(request.stage1_schedule_snapshot_json, operation_id, "result")
    expected_status = (
        "Depreciation Pending"
        if any(
            row.stage == "pre_disposal_depreciation" for row in request.get("generated_journal_entries") or []
        )
        else "Ready to Dispose"
    )
    if result["data"] != {"request": request.name, "status": expected_status}:
        frappe.throw(_("Asset depreciation stage result differs from its native operation."))
    if request.disposal_status in {"Disposal Accounting Pending", "Closed"}:
        _verify_final_retry(request, _final_operation_id(request))
    else:
        _verify_stage1_schedule_links(request, _active_schedule_snapshot(asset))
    return result


@frappe.whitelist()
def stage_depreciation(name: str) -> dict[str, Any]:
    """Run native disposal-date depreciation before the final asset effect."""
    if not frappe.has_permission(DOCTYPE, "write", name):
        frappe.throw(_("Asset Disposal Request write permission is required."))
    request = _lock_request(name)
    _require_execute_actor(request)
    asset = _lock_asset(request.asset)
    operation_id = _stage1_operation_id(request)
    if request.stage1_operation_id:
        return _verify_stage1_retry(request, asset, operation_id)
    if request.disposal_status != "Not Executed" or request.stage1_operation_id:
        frappe.throw(_("Asset depreciation has already been staged."))
    _verify_before_stage(request, asset)
    from erpnext.assets.doctype.asset.depreciation import depreciate_asset

    expected_rates = _native_stage1_rates(asset)
    request.execution_id = hashlib.sha256(
        (request.name + "\x1f" + request.approval_digest).encode()
    ).hexdigest()
    request.execution_phase = "stage1"
    request.execute_started_at = now_datetime()
    request.stage1_operation_id = operation_id
    authorize_request_update(
        request,
        STATE_SUBMITTED,
        {"execution_id", "execution_phase", "execute_started_at", "stage1_operation_id"},
    )
    request.save(ignore_permissions=True)
    with native_disposal_capability(request, "stage1", operation_id):
        depreciate_asset(asset, getdate(request.disposal_date), f"Asset Disposal Request {request.name}")
    asset.reload()
    _actual_stage1_rates(asset, expected_rates)
    result_status = "Depreciation Pending" if request.get("generated_journal_entries") else "Ready to Dispose"
    result = {"data": {"request": request.name, "status": result_status}, "message": ""}
    snapshot = {
        "operation_id": operation_id,
        "result": result,
        "schedules": _active_schedule_snapshot(asset),
        "rate_deltas": expected_rates,
    }
    request.stage1_schedule_snapshot_json = _canonical(snapshot)
    request.stage1_schedule_snapshot_digest = hashlib.sha256(
        request.stage1_schedule_snapshot_json.encode()
    ).hexdigest()
    request.disposal_status = (
        "Depreciation Pending" if request.get("generated_journal_entries") else "Ready to Dispose"
    )
    request.execution_phase = (
        "awaiting_depreciation" if request.get("generated_journal_entries") else "ready_to_dispose"
    )
    authorize_request_update(
        request,
        STATE_SUBMITTED,
        {
            "stage1_schedule_snapshot_json",
            "stage1_schedule_snapshot_digest",
            "disposal_status",
            "execution_phase",
        },
    )
    request.save(ignore_permissions=True)
    return result


def _verify_child(je: Any, request: Any, row: Any) -> None:
    from connect_diagnostics_core.api.erpnext import journal_entry_generators, journal_entry_workflow

    source = journal_entry_generators._validate_source_provenance(je)
    if (
        source[0] != DOCTYPE
        or source[1] != request.name
        or source[2]
        != "asset_disposal_" + ("stage1" if row.stage == "pre_disposal_depreciation" else "final")
        or source[3] != row.operation_id
        or je.name != row.journal_entry
        or je.approval_source_proof != row.source_proof
        or journal_entry_workflow.get_approval_digest(je) != row.draft_payload_digest
        or je.company != request.company
        or tuple(_asset_references(je)) != (request.asset,)
        or je.voucher_type != ("Depreciation Entry" if row.kind == "depreciation" else "Asset Disposal")
        or str(je.posting_date) != str(row.posting_date)
        or (je.finance_book or "") != (row.finance_book or "")
    ):
        frappe.throw(_("Linked Asset disposal Journal Entry provenance changed."))


def _posted_depreciation_by_book(request: Any) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for row in request.get("generated_journal_entries") or []:
        if row.stage != "pre_disposal_depreciation" or row.kind != "depreciation":
            continue
        je = frappe.get_doc("Journal Entry", row.journal_entry)
        _verify_child(je, request, row)
        if je.docstatus != 1:
            frappe.throw(_("All staged Depreciation Entries must be submitted before disposal."))
        expense = [
            account
            for account in je.get("accounts") or []
            if account.reference_type == "Asset"
            and account.reference_name == request.asset
            and frappe.get_cached_value("Account", account.account, "root_type") == "Expense"
            and flt(account.debit) > 0
        ]
        if len(expense) != 1:
            frappe.throw(_("Staged depreciation has an invalid Asset expense debit."))
        book = str(je.finance_book or "")
        amounts[book] = amounts.get(book, 0.0) + flt(expense[0].debit)
    return amounts


def _verify_stage1_schedule_links(request: Any, current: list[dict[str, Any]]) -> None:
    if not request.stage1_schedule_snapshot_json or not request.stage1_schedule_snapshot_digest:
        frappe.throw(_("Asset depreciation schedule snapshot is missing."))
    if (
        hashlib.sha256(request.stage1_schedule_snapshot_json.encode()).hexdigest()
        != request.stage1_schedule_snapshot_digest
    ):
        frappe.throw(_("Asset depreciation schedule snapshot digest is invalid."))
    expected = json.loads(request.stage1_schedule_snapshot_json)["schedules"]
    if len(current) != len(expected):
        frappe.throw(_("Asset depreciation schedule count changed after staging."))
    linked = {
        row.journal_entry
        for row, status, _state in _child_statuses(request)
        if row.stage == "pre_disposal_depreciation" and status == 1
    }
    for old_schedule, new_schedule in zip(expected, _normalized(current), strict=True):
        for key in ("finance_book", "name", "docstatus"):
            if old_schedule[key] != new_schedule[key]:
                frappe.throw(_("Active Asset depreciation schedule changed after staging."))
        old_rows = old_schedule["rows"]
        new_rows = new_schedule["rows"]
        if len(old_rows) != len(new_rows):
            frappe.throw(_("Asset depreciation schedule topology changed after staging."))
        for old_row, new_row in zip(old_rows, new_rows, strict=True):
            old_link = old_row.pop("journal_entry", None)
            new_link = new_row.pop("journal_entry", None)
            if old_row != new_row or (new_link != old_link and (old_link or new_link not in linked)):
                frappe.throw(_("Asset depreciation schedule row changed outside its linked Journal Entry."))


def _verify_posted_depreciation_schedule_bijection(request: Any, asset: Any) -> None:
    """A posted child must match one exact native schedule row before JE commit."""
    schedules = _active_schedule_snapshot(asset)
    by_book = {str(item["finance_book"] or ""): item for item in schedules}
    if len(by_book) != len(schedules):
        frappe.throw(_("Asset has ambiguous Finance Book depreciation schedules."))
    all_links = [
        row["journal_entry"] for schedule in schedules for row in schedule["rows"] if row["journal_entry"]
    ]
    posted_links: set[str] = set()
    for child in request.get("generated_journal_entries") or []:
        if child.stage != "pre_disposal_depreciation":
            continue
        je = frappe.get_doc("Journal Entry", child.journal_entry)
        _verify_child(je, request, child)
        if je.docstatus != 1:
            if child.journal_entry in all_links:
                frappe.throw(_("Unsubmitted Asset depreciation Journal Entry has a native schedule link."))
            continue
        if all_links.count(je.name) != 1:
            frappe.throw(_("Posted depreciation Journal Entry must link exactly once across Finance Books."))
        book = str(je.finance_book or "")
        schedule = by_book.get(book)
        if not schedule:
            frappe.throw(_("Posted depreciation has no matching active Finance Book schedule."))
        assert schedule is not None
        matches = [row for row in schedule["rows"] if row["journal_entry"] == je.name]
        if len(matches) != 1 or je.name in posted_links:
            frappe.throw(_("Posted Depreciation Entry must link to one exact schedule row."))
        expense = [
            row
            for row in je.get("accounts") or []
            if row.reference_type == "Asset"
            and row.reference_name == request.asset
            and frappe.get_cached_value("Account", row.account, "root_type") == "Expense"
            and flt(row.debit) > 0
        ]
        if (
            len(expense) != 1
            or str(matches[0]["schedule_date"]) != str(je.posting_date)
            or flt(matches[0]["depreciation_amount"], asset.precision("net_purchase_amount"))
            != flt(expense[0].debit, asset.precision("net_purchase_amount"))
        ):
            frappe.throw(_("Posted depreciation date or amount differs from its native schedule row."))
        posted_links.add(je.name)


def _verify_ready_for_final(request: Any, asset: Any) -> None:
    _verify_intent(request, asset)
    _verify_stage1_schedule_links(request, _active_schedule_snapshot(asset))
    _verify_posted_depreciation_schedule_bijection(request, asset)
    amounts = _posted_depreciation_by_book(request)
    baseline = json.loads(request.asset_baseline_json)
    initial = baseline["values"]
    current_values = _normalized(_asset_values(asset))
    initial_books = {
        str(row["finance_book"] or ""): flt(row["value_after_depreciation"])
        for row in initial["finance_books"]
    }
    current_books = {
        str(row["finance_book"] or ""): flt(row["value_after_depreciation"])
        for row in current_values["finance_books"]
    }
    if initial_books.keys() != current_books.keys():
        frappe.throw(_("Asset Finance Books changed after approval."))
    precision = asset.precision("net_purchase_amount")
    for book, initial_amount in initial_books.items():
        if flt(initial_amount - amounts.get(book, 0), precision) != flt(current_books[book], precision):
            frappe.throw(_("Asset carrying value does not match approved Depreciation Entries."))
    if flt(initial["value_after_depreciation"] - sum(amounts.values()), precision) != flt(
        current_values["value_after_depreciation"], precision
    ):
        frappe.throw(_("Asset total carrying value does not match linked Depreciation Entries."))
    approved = json.loads(request.approved_intent_json)
    invoice = _sale_candidate(request) if request.purpose == "Sale" else None
    actual_gl = _normalized(_forecast_disposal_gl(request, asset, invoice, forecast=False))
    if actual_gl != approved["disposal_gl"]:
        frappe.throw(_("Native disposal GL projection changed after approval."))


def _verify_final_retry(request: Any, operation_id: str) -> dict[str, Any]:
    if (
        request.docstatus != 1
        or request.workflow_state != STATE_SUBMITTED
        or request.disposal_status not in {"Disposal Accounting Pending", "Closed"}
        or not request.execute_completed_at
        or not request.final_schedule_snapshot_json
        or hashlib.sha256(request.final_schedule_snapshot_json.encode()).hexdigest()
        != request.final_schedule_snapshot_digest
    ):
        frappe.throw(_("Asset disposal final retry does not match a completed native operation."))
    result = _recorded_operation_result(request.final_schedule_snapshot_json, operation_id, "result")
    snapshot = json.loads(request.final_schedule_snapshot_json)
    expected_status = "Closed" if request.purpose == "Sale" else "Disposal Accounting Pending"
    if result["data"] != {"request": request.name, "status": expected_status}:
        frappe.throw(_("Asset disposal final result differs from its native operation."))
    if request.purpose == "Sale":
        if not request.sales_invoice or request.disposal_journal_entry:
            frappe.throw(_("Recorded Asset sale operation has no exact Sales Invoice result."))
        invoice = frappe.get_doc("Sales Invoice", request.sales_invoice)
        if (
            invoice.docstatus != 1
            or len(invoice.get("items") or []) != 1
            or invoice.items[0].asset != request.asset
            or not invoice.items[0].is_fixed_asset
            or _normalized(_projection(invoice)) != json.loads(request.sale_candidate_projection)
        ):
            frappe.throw(_("Recorded Asset sale operation differs from its native Sales Invoice."))
    else:
        if not request.disposal_journal_entry or request.sales_invoice:
            frappe.throw(_("Recorded Asset Scrap operation has no exact native Journal Entry result."))
        rows = [
            row
            for row in request.get("generated_journal_entries") or []
            if row.stage == "final_disposal"
            and row.kind == "asset_disposal"
            and row.operation_id == operation_id
            and row.journal_entry == request.disposal_journal_entry
        ]
        if len(rows) != 1:
            frappe.throw(_("Recorded Asset Scrap operation has invalid Journal Entry provenance."))
        je = frappe.get_doc("Journal Entry", request.disposal_journal_entry)
        _verify_child(je, request, rows[0])
        if je.docstatus not in {0, 1}:
            frappe.throw(_("Recorded Asset Scrap Journal Entry is no longer active."))
    if not isinstance(snapshot.get("schedules"), list):
        frappe.throw(_("Asset disposal final schedule result is invalid."))
    return result


@frappe.whitelist()
def finalize_disposal(name: str) -> dict[str, Any]:
    """Post native SI or create native Scrap JE after exact depreciation proof."""
    if not frappe.has_permission(DOCTYPE, "write", name):
        frappe.throw(_("Asset Disposal Request write permission is required."))
    request = _lock_request(name)
    _require_execute_actor(request)
    operation_id = _final_operation_id(request)
    if (
        request.final_schedule_snapshot_json
        or request.sales_invoice
        or request.disposal_journal_entry
        or request.execute_completed_at
    ):
        _lock_asset(request.asset)
        return _verify_final_retry(request, operation_id)
    if (
        request.disposal_status != "Ready to Dispose"
        or request.sales_invoice
        or request.disposal_journal_entry
    ):
        frappe.throw(_("Asset disposal is not ready for final execution."))
    asset = _lock_asset(request.asset)
    _verify_ready_for_final(request, asset)
    before_schedules = _active_schedule_snapshot(asset)
    expected_final_rows = _expected_final_schedule_rows(asset, request.disposal_date)
    request.execution_phase = "final"
    authorize_request_update(request, STATE_SUBMITTED, {"execution_phase"})
    request.save(ignore_permissions=True)
    with native_disposal_capability(request, "final", operation_id):
        if request.purpose == "Sale":
            invoice = _sale_candidate(request)
            if _normalized(_projection(invoice)) != json.loads(request.sale_candidate_projection):
                frappe.throw(_("Native Sales Invoice payload changed after approval."))
            with _sale_tax_context(request, invoice):
                invoice.insert()
                if _normalized(_projection(invoice)) != json.loads(request.sale_candidate_projection):
                    frappe.throw(_("Native Sales Invoice changed during insert validation."))
                invoice.submit()
            request.sales_invoice = invoice.name
        else:
            from erpnext.assets.doctype.asset.depreciation import scrap_asset

            scrap_asset(request.asset, request.disposal_date)
            final_rows = [
                row for row in request.get("generated_journal_entries") or [] if row.stage == "final_disposal"
            ]
            if len(final_rows) != 1 or final_rows[0].kind != "asset_disposal":
                frappe.throw(_("Native Scrap did not create exactly one linked disposal Journal Entry."))
            request.disposal_journal_entry = final_rows[0].journal_entry
    asset.reload()
    after_schedules = _active_schedule_snapshot(asset)
    if [row["finance_book"] for row in before_schedules] != [
        row["finance_book"] for row in after_schedules
    ] or _normalized(
        [
            [{key: value for key, value in row.items() if key != "name"} for row in schedule["rows"]]
            for schedule in after_schedules
        ]
    ) != expected_final_rows:
        frappe.throw(_("Native disposal changed Asset depreciation schedule rows unexpectedly."))
    staged_links = {
        row.journal_entry
        for row in request.get("generated_journal_entries") or []
        if row.stage == "pre_disposal_depreciation"
    }
    before_links = {
        row["journal_entry"]
        for item in before_schedules
        for row in item["rows"]
        if row["journal_entry"] in staged_links
    }
    after_links = {
        row["journal_entry"]
        for item in after_schedules
        for row in item["rows"]
        if row["journal_entry"] in staged_links
    }
    if before_links != after_links or before_links != staged_links:
        frappe.throw(_("Native disposal lost staged Depreciation Entry schedule links."))
    result_status = "Disposal Accounting Pending" if request.disposal_journal_entry else "Closed"
    result = {"data": {"request": request.name, "status": result_status}, "message": ""}
    request.final_schedule_snapshot_json = _canonical(
        {"operation_id": operation_id, "result": result, "schedules": after_schedules}
    )
    request.final_schedule_snapshot_digest = hashlib.sha256(
        request.final_schedule_snapshot_json.encode()
    ).hexdigest()
    request.execute_completed_at = now_datetime()
    request.execution_phase = "awaiting_disposal_accounting" if request.disposal_journal_entry else "closed"
    request.disposal_status = "Disposal Accounting Pending" if request.disposal_journal_entry else "Closed"
    authorize_request_update(
        request,
        STATE_SUBMITTED,
        {
            "sales_invoice",
            "disposal_journal_entry",
            "final_schedule_snapshot_json",
            "final_schedule_snapshot_digest",
            "execute_completed_at",
            "execution_phase",
            "disposal_status",
        },
    )
    request.save(ignore_permissions=True)
    return result


def guard_disposal_sales_invoice_submit(invoice: Any, method: str | None = None) -> None:
    """Require a linked Execute for every whole fixed-Asset sale."""
    del method
    asset_rows = [row for row in invoice.get("items") or [] if row.asset]
    assets = tuple(sorted({str(row.asset) for row in asset_rows}))
    if not assets:
        return
    if any(not row.is_fixed_asset for row in asset_rows):
        frappe.throw(_("Asset-linked Sales Invoice rows must have the fixed Asset flag."))
    if len(assets) != 1 or len(invoice.get("items") or []) != 1:
        frappe.throw(_("Fixed Asset disposal Sales Invoice must contain one whole Asset."))
    asset_name = assets[0]
    _lock_asset(asset_name)
    grant = _native_grant(asset_name, "final")
    if grant:
        request = grant.document
        if grant.sale_consumed:
            frappe.throw(_("Asset sale Execute cannot submit another Sales Invoice."))
        if request.purpose != "Sale" or request.company != invoice.company:
            frappe.throw(_("Asset sale is not authorized by this disposal request."))
        if _normalized(_projection(invoice)) != json.loads(request.sale_candidate_projection):
            frappe.throw(_("Submitted Sales Invoice differs from approved Asset sale."))
        grant.sale_consumed = True
        return
    if invoice.get("demo_fulfillment_allocation") and not _active_request_for_asset(asset_name):
        from connect_diagnostics_core.api.erpnext.sales_invoice import validate_demo_sales_invoice

        validate_demo_sales_invoice(invoice)
        return
    frappe.throw(_("Fixed Asset sale requires an approved Asset Disposal Request."))


def guard_disposal_sales_invoice_cancel(invoice: Any, method: str | None = None) -> None:
    del method
    requests = frappe.db.get_all(
        DOCTYPE, filters={"sales_invoice": invoice.name}, fields=["name", "disposal_status"]
    )
    if requests:
        frappe.throw(_("A linked Asset Disposal Request prevents Sales Invoice cancellation."))


def guard_disposal_journal_entry_submit(je: Any, method: str | None = None) -> None:
    del method
    references = _asset_references(je)
    if not references:
        return
    if je.voucher_type == "Asset Disposal" and len(references) != 1:
        frappe.throw(_("Asset Disposal Journal Entry must reference one Asset."))
    if je.voucher_type not in {"Asset Disposal", "Depreciation Entry"}:
        return
    request_name = str(je.get("approval_source_name") or "")
    request = (
        _lock_request(request_name) if request_name and je.get("approval_source_doctype") == DOCTYPE else None
    )
    for asset_name in references:
        _lock_asset(asset_name)
        if (
            je.voucher_type == "Depreciation Entry"
            and not _active_request_for_asset(asset_name)
            and not request_name
        ):
            continue
        if not request:
            frappe.throw(_("Asset disposal Journal Entry is missing approved provenance."))
        assert request is not None
        if request.asset != asset_name:
            frappe.throw(_("Asset disposal Journal Entry refers to another Asset."))
        rows = [row for row in request.get("generated_journal_entries") or [] if row.journal_entry == je.name]
        if len(rows) != 1:
            frappe.throw(_("Asset disposal Journal Entry has no exact child link."))
        _verify_child(je, request, rows[0])
        if request.workflow_state != STATE_SUBMITTED or request.docstatus != 1:
            frappe.throw(_("Asset disposal is no longer open for Journal Entry posting."))
        if je.voucher_type == "Depreciation Entry":
            if (
                rows[0].stage != "pre_disposal_depreciation"
                or request.disposal_status != "Depreciation Pending"
            ):
                frappe.throw(_("Staged Depreciation Entry is outside its approved phase."))
        elif rows[0].stage != "final_disposal" or request.disposal_status != "Disposal Accounting Pending":
            frappe.throw(_("Asset Disposal Journal Entry is outside its approved final phase."))


def complete_disposal_journal_entry_submit(je: Any, method: str | None = None) -> None:
    """Advance source progress only after native JE submit and Asset updates."""
    del method
    if je.docstatus != 1 or je.get("approval_source_doctype") != DOCTYPE:
        return
    request = _lock_request(str(je.get("approval_source_name") or ""))
    rows = [row for row in request.get("generated_journal_entries") or [] if row.journal_entry == je.name]
    if len(rows) != 1:
        frappe.throw(_("Posted Asset disposal Journal Entry lost its source link."))
    _verify_child(je, request, rows[0])
    if rows[0].stage == "pre_disposal_depreciation":
        _verify_posted_depreciation_schedule_bijection(request, _lock_asset(request.asset))
        if all(
            status == 1
            for child, status, _state in _child_statuses(request)
            if child.stage == "pre_disposal_depreciation"
        ):
            request.disposal_status = "Ready to Dispose"
            request.execution_phase = "ready_to_dispose"
    elif rows[0].stage == "final_disposal":
        if request.disposal_journal_entry != je.name:
            frappe.throw(_("Posted disposal Journal Entry is not the expected final effect."))
        if any(status != 1 for _child, status, _state in _child_statuses(request)):
            frappe.throw(_("Asset disposal cannot close with unposted linked Journal Entries."))
        request.disposal_status = "Closed"
        request.execution_phase = "closed"
    else:
        frappe.throw(_("Unknown Asset disposal Journal Entry stage."))
    authorize_request_update(request, request.workflow_state, {"disposal_status", "execution_phase"})
    request.save(ignore_permissions=True)


def guard_disposal_journal_entry_cancel(je: Any, method: str | None = None) -> None:
    del method
    if je.get("approval_source_doctype") != DOCTYPE:
        return
    request = _lock_request(str(je.get("approval_source_name") or ""))
    if not any(row.journal_entry == je.name for row in request.get("generated_journal_entries") or []):
        frappe.throw(_("Journal Entry has no exact Asset disposal child link."))
    frappe.throw(_("Linked Asset disposal accounting history cannot be cancelled."))


def _posted_disposal_journal_entry_allows_status(asset: Any, request_name: str | None) -> bool:
    je_name = str(asset.get("journal_entry_for_scrap") or "")
    if not request_name or not je_name:
        return False
    request = _lock_request(request_name)
    if (
        request.asset != asset.name
        or request.workflow_state != STATE_SUBMITTED
        or request.disposal_status not in {"Disposal Accounting Pending", "Closed"}
        or request.disposal_journal_entry != je_name
    ):
        return False
    rows = [
        row
        for row in request.get("generated_journal_entries") or []
        if row.journal_entry == je_name and row.stage == "final_disposal" and row.kind == "asset_disposal"
    ]
    if len(rows) != 1:
        return False
    je = frappe.get_doc("Journal Entry", je_name)
    _verify_child(je, request, rows[0])
    return int(je.docstatus or 0) == 1


def guard_asset_disposal_mutation(
    asset: Any, changed: set[str], values: Mapping[str, Any] | None = None
) -> None:
    protected_fields = {"disposal_date", "journal_entry_for_scrap"}
    if not changed.intersection(protected_fields | {"status"}):
        return
    if asset.docstatus != 1:
        return
    prior_status = frappe.db.get_value("Asset", asset.name, "status", for_update=True, wait=False)
    target_status = (values or {}).get("status", asset.get("status"))
    protected_request = (
        _protected_request_for_asset(asset.name)
        if prior_status in {"Sold", "Scrapped"} or target_status in {"Sold", "Scrapped"}
        else None
    )
    terminal = prior_status in {"Sold", "Scrapped"}
    if terminal and protected_request:
        if not _native_grant(asset.name, "reset"):
            frappe.throw(_("A completed Asset Disposal Request protects this Asset."))
        return
    if "status" in changed and target_status in {"Sold", "Scrapped"}:
        if not _native_grant(asset.name, "final") and not (
            target_status == "Scrapped"
            and _posted_disposal_journal_entry_allows_status(asset, protected_request)
        ):
            frappe.throw(_("Native Asset terminal status requires approved disposal accounting."))
    if (
        changed.intersection(protected_fields)
        and prior_status not in {"Cancelled", "Sold", "Scrapped", "Capitalized"}
        and not _native_grant(asset.name, "final")
    ):
        frappe.throw(_("Native Asset disposal fields require an approved request Execute."))


def guard_asset_disposal_save(asset: Any, method: str | None = None) -> None:
    del method
    previous = asset.get_doc_before_save()
    if not previous:
        return
    changed = {
        field
        for field in ("disposal_date", "journal_entry_for_scrap", "status")
        if previous.get(field) != asset.get(field)
    }
    guard_asset_disposal_mutation(asset, changed, {"status": asset.get("status")})


class AssetDisposalNativeMixin:
    """Protect ERPNext Asset.db_set mutations used by direct Python Scrap."""

    def db_set(
        self: Any, fieldname: str | dict[str, Any], value: Any = None, *args: Any, **kwargs: Any
    ) -> Any:
        changed = set(fieldname) if isinstance(fieldname, dict) else {fieldname}
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        guard_asset_disposal_mutation(self, changed, values)
        return super().db_set(fieldname, value, *args, **kwargs)


class AssetDisposalFinanceBookMixin:
    """Stop Restore's WDV/DDB rate write before it changes a protected Asset."""

    def db_set(
        self: Any, fieldname: str | dict[str, Any], value: Any = None, *args: Any, **kwargs: Any
    ) -> Any:
        changed = set(fieldname) if isinstance(fieldname, dict) else {fieldname}
        if (
            "rate_of_depreciation" in changed
            and self.parenttype == "Asset"
            and self.parentfield == "finance_books"
        ):
            asset_name = self.parent
            if not frappe.db.get_value("Asset", asset_name, "name", for_update=True, wait=False):
                frappe.throw(_("Asset Finance Book needs an existing Asset."))
            request_name = _protected_request_for_asset(asset_name)
            if request_name:
                grant = _native_grant(asset_name)
                if (
                    not grant
                    or grant.request != request_name
                    or grant.phase not in {"stage1", "final", "reset"}
                ):
                    frappe.throw(
                        _("Protected Asset depreciation rate requires its approved disposal operation.")
                    )
        return super().db_set(fieldname, value, *args, **kwargs)


def guard_asset_depreciation_schedule_change(schedule: Any, method: str) -> None:
    """Deny native Restore's first write for a reserved or completed Asset."""
    del method
    asset_name = schedule.get("asset")
    if not asset_name:
        return
    if not frappe.db.get_value("Asset", asset_name, "name", for_update=True, wait=False):
        frappe.throw(_("Asset Depreciation Schedule needs an existing Asset."))
    request_name = _protected_request_for_asset(asset_name)
    if request_name:
        grant = _native_grant(asset_name)
        if not grant or grant.request != request_name or grant.phase not in {"stage1", "final", "reset"}:
            frappe.throw(
                _("A protected Asset Depreciation Schedule requires its approved disposal operation.")
            )


@frappe.whitelist()
def scrap_asset(asset_name: str, scrap_date: str | None = None) -> Any:
    from erpnext.assets.doctype.asset.depreciation import scrap_asset as native_scrap

    frappe.has_permission("Asset", "write", asset_name, throw=True)
    asset = _lock_asset(asset_name)
    if not _native_grant(asset.name, "final"):
        frappe.throw(_("Scrap requires an approved Asset Disposal Request Execute."))
    return native_scrap(asset_name, scrap_date)


@frappe.whitelist()
def restore_asset(asset_name: str) -> Any:
    from erpnext.assets.doctype.asset.depreciation import restore_asset as native_restore

    frappe.has_permission("Asset", "write", asset_name, throw=True)
    asset = _lock_asset(asset_name, wait=False)
    if _protected_request_for_asset(asset.name):
        frappe.throw(_("A retained Asset Disposal Request protects this Asset from Restore."))
    return native_restore(asset_name)


@frappe.whitelist()
def reset_and_abandon(name: str) -> dict[str, Any]:
    """Execute the separately approved native schedule reset without erasing JEs."""
    if not frappe.has_permission(DOCTYPE, "write", name):
        frappe.throw(_("Asset Disposal Request write permission is required."))
    request = _lock_request(name)
    _require_reset_preflight(request)
    if request.workflow_state != STATE_RESET_APPROVED:
        frappe.throw(_("Asset disposal schedule reset has not been independently approved."))
    _actor(request, REVIEWER_ROLE, request.reset_maker_user, (request.reset_approver_user,))
    if request.reset_digest != _digest(
        {
            "approval_digest": request.approval_digest,
            "reason": request.reset_reason,
            "stage1_operation_id": request.stage1_operation_id,
        }
    ):
        frappe.throw(_("Asset disposal reset approval is stale."))
    asset = _lock_asset(request.asset)
    _verify_intent(request, asset)
    _verify_stage1_schedule_links(request, _active_schedule_snapshot(asset))
    _verify_posted_depreciation_schedule_bijection(request, asset)
    posted = {row.journal_entry for row, status, _state in _child_statuses(request) if status == 1}
    from erpnext.assets.doctype.asset.depreciation import reset_depreciation_schedule

    with native_disposal_capability(request, "reset", request.reset_digest):
        reset_depreciation_schedule(asset, request.reset_reason)
    asset.reload()
    current = _active_schedule_snapshot(asset)
    retained = {
        row["journal_entry"] for item in current for row in item["rows"] if row["journal_entry"] in posted
    }
    if retained != posted:
        frappe.throw(_("Native schedule reset did not retain posted depreciation history."))
    request.disposal_status = "Abandoned/Released"
    request.execution_phase = "reset_abandoned"
    request.reset_completed_at = now_datetime()
    authorize_request_update(
        request, STATE_RESET_APPROVED, {"disposal_status", "execution_phase", "reset_completed_at"}
    )
    request.save(ignore_permissions=True)
    from frappe.model.workflow import apply_workflow

    proof = {"name": request.name, "user": frappe.session.user, "consumed": False}
    if getattr(frappe.local, _RESET_EXECUTION, None):
        frappe.throw(_("Asset disposal reset operation is already active."))
    setattr(frappe.local, _RESET_EXECUTION, proof)
    try:
        request = apply_workflow(request, "Reset/Abandon")
        if not proof["consumed"] or request.workflow_state != STATE_EXECUTION_ABANDONED:
            frappe.throw(_("Native Asset disposal reset transition did not complete."))
    finally:
        delattr(frappe.local, _RESET_EXECUTION)
    return {"data": {"request": request.name, "status": request.disposal_status}, "message": ""}
