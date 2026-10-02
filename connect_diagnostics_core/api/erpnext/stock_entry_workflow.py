# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guards for the native Stock Entry Material Transfer workflow."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_conflict
from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
from connect_diagnostics_core.api.frappe.approval_controls import (
    authorize_approval_field_write,
    authorize_workflow_field_write,
    consume_approval_field_grant,
    critical_digest,
    require_distinct_actors,
    require_locked_submitted_update,
    require_native_terminal_state,
    require_permission,
    resolve_user,
)
from connect_diagnostics_core.api.frappe.approval_routes import get_route
from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    require_location_warehouse,
    require_operational_warehouse,
)

DIRECT_TRANSFER_PURPOSE = "Material Transfer"
ROUTE = "stock_entry_material_transfer"
_CANCEL_ACTION = "Cancel Stock Transfer"
APPROVED_STATES = frozenset(
    {
        "Stock Transfer Submitted",
    }
)
EMERGENCY_STATES = frozenset(
    {
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
        "Emergency Stock Movement Submitted",
        "Emergency Stock Movement Rejected",
        "Emergency Stock Movement Cancelled",
    }
)
EXCEPTION_FLAG = "freeze_exception"
EXCEPTION_REASON = "freeze_exception_reason"
EXCEPTION_SCOPE = "freeze_exception_reconciliation_scope"
_REVIEW_LOCKED_STATES = frozenset(
    {
        "Stock Transfer Pending Review",
        "Stock Transfer Reviewed",
        "Stock Transfer Approved",
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
    }
)
_CRITICAL_FIELDS = (
    "purpose",
    "stock_entry_type",
    "company",
    "posting_date",
    "posting_time",
    "set_posting_time",
    "from_warehouse",
    "to_warehouse",
    "add_to_transit",
    "outgoing_stock_entry",
    "inspection_required",
    "apply_putaway_rule",
    "items",
)
_CRITICAL_ITEM_FIELDS = (
    "item_code",
    "s_warehouse",
    "t_warehouse",
    "storage_location",
    "to_storage_location",
    "qty",
    "transfer_qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "serial_and_batch_bundle",
    "serial_no",
    "batch_no",
    "basic_rate",
    "basic_amount",
    "valuation_rate",
    "allow_zero_valuation_rate",
    "use_serial_batch_fields",
    "expense_account",
    "cost_center",
    "project",
    "material_request",
    "material_request_item",
    "against_stock_entry",
    "putaway_rule",
    "reference_purchase_receipt",
    "job_card_item",
    "bom_no",
    "sample_quantity",
)
_APPROVAL_FIELDS = frozenset(
    {
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)
_SUBMIT_IDENTITY_CAPTURE = "_stock_transfer_submit_identity_capture"


def is_direct_transfer(doc: Document) -> bool:
    """Return whether a Stock Entry is a direct Material Transfer."""
    return bool(
        doc.get("purpose") == DIRECT_TRANSFER_PURPOSE
        and not doc.get("add_to_transit")
        and not doc.get("outgoing_stock_entry")
    )


def _reject_excluded_material_transfer(doc: Document) -> None:
    if doc.get("purpose") == DIRECT_TRANSFER_PURPOSE and not is_direct_transfer(doc):
        frappe.throw(_("Transit Material Transfers require a separate approved Workflow route."))


def has_freeze_exception(doc: Document) -> bool:
    """Return whether the document requests the narrowly scoped exception route."""
    return bool(doc.get(EXCEPTION_FLAG))


def _validate_count_entry(doc: Document, phase: str) -> bool:
    """Leave ordinary routing only after the independent Count verifier succeeds."""
    from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import (
        guard_count_stock_entry,
        is_count_stock_entry,
    )

    if not is_count_stock_entry(doc):
        return False
    previous = doc.get_doc_before_save()
    for current in (doc, previous):
        if current is not None and (
            any(current.get(field) for field in (EXCEPTION_FLAG, EXCEPTION_REASON, EXCEPTION_SCOPE))
            or current.get("workflow_state") in EMERGENCY_STATES
        ):
            frappe.throw(_("Count corrections cannot use Emergency Stock Movement authority."))
    guard_count_stock_entry(doc, phase)
    return True


def _has_native_exception_approval(doc: Document) -> bool:
    """Use a completed native action as supporting approval evidence only.

    A rejected action is also Completed in Frappe, so this predicate is never
    sufficient to authorize posting by itself.  The native Post transition task
    supplies the request-scoped execution provenance checked below.
    """
    return bool(
        frappe.db.exists(
            {
                "doctype": "Workflow Action",
                "reference_doctype": "Stock Entry",
                "reference_name": doc.name,
                "workflow_state": "Emergency Stock Movement Pending Review",
                "status": "Completed",
            }
        )
    )


def _has_native_execution_provenance(doc: Document) -> bool:
    marker = getattr(frappe.flags, "freeze_exception_execution", None)
    return marker == {"doctype": doc.doctype, "name": doc.name}


def clear_freeze_exception_execution() -> None:
    """Clear the one-transition execution marker after validation or failure."""
    frappe.flags.freeze_exception_execution = None


def _has_current_freeze_scope(doc: Document) -> bool:
    try:
        approved_scope = {
            tuple(sorted(entry.items())) for entry in json.loads(doc.get(EXCEPTION_SCOPE) or "[]")
        }
    except (TypeError, ValueError):
        return False

    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import get_active_freeze_scope

    current_scope = {tuple(sorted(entry.items())) for entry in get_active_freeze_scope(doc)}
    return current_scope.issubset(approved_scope)


def is_authorized_freeze_exception(doc: Document) -> bool:
    """Return whether native posting may use the scoped reconciliation exception."""
    return bool(
        is_direct_transfer(doc)
        and has_freeze_exception(doc)
        and doc.get("workflow_state") == "Emergency Stock Movement Submitted"
        and str(doc.get(EXCEPTION_REASON) or "").strip()
        and _has_native_exception_approval(doc)
        and _has_current_freeze_scope(doc)
        and _has_native_execution_provenance(doc)
    )


def authorize_freeze_exception_execution(doc: Document) -> None:
    """Mark a native Post transition as the only execution entry point."""
    if not (
        is_direct_transfer(doc)
        and has_freeze_exception(doc)
        and doc.get("workflow_state") == "Emergency Stock Movement Submitted"
        and str(doc.get(EXCEPTION_REASON) or "").strip()
        and _has_native_exception_approval(doc)
        and _has_current_freeze_scope(doc)
    ):
        frappe.throw(_("Emergency Stock Movement must have a completed native approval before posting."))
    frappe.flags.freeze_exception_execution = {"doctype": doc.doctype, "name": doc.name}


def capture_freeze_exception_approval_scope(doc: Document) -> None:
    """Persist the Freeze scope present when native Emergency approval completes."""
    if not (is_direct_transfer(doc) and has_freeze_exception(doc)):
        frappe.throw(_("Freeze Exception approval requires a direct Material Transfer."))
    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import get_active_freeze_scope

    doc.set(EXCEPTION_SCOPE, json.dumps(get_active_freeze_scope(doc), sort_keys=True))


def _approval_payload(doc: Document) -> dict[str, Any]:
    payload: dict[str, Any] = {
        fieldname: doc.get(fieldname) for fieldname in _CRITICAL_FIELDS if fieldname != "items"
    }
    if not doc.get("set_posting_time"):
        payload["posting_date"] = None
        payload["posting_time"] = None
    payload["items"] = [
        {fieldname: row.get(fieldname) for fieldname in _CRITICAL_ITEM_FIELDS}
        for row in doc.get("items") or []
    ]
    return payload


def _requested_tracked_identities(row: Document, item: frappe._dict) -> dict[tuple[str, str], Decimal]:
    """Read source identities already selected on the native draft row or Bundle."""
    requested: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    bundle_name = str(row.get("serial_and_batch_bundle") or "")
    if bundle_name:
        try:
            bundle = cast(
                frappe._dict | None,
                frappe.db.get_value(
                    "Serial and Batch Bundle",
                    bundle_name,
                    [
                        "docstatus",
                        "is_cancelled",
                        "item_code",
                        "warehouse",
                        "type_of_transaction",
                        "total_qty",
                    ],
                    as_dict=True,
                    for_update=True,
                    wait=False,
                ),
            )
            if not bundle:
                frappe.throw(_("The supplied Serial and Batch Bundle is missing or inactive."))
            bundle_doc = cast(frappe._dict, bundle)
            entries = cast(
                list[frappe._dict],
                frappe.db.get_values(
                    "Serial and Batch Entry",
                    {"parent": bundle_name, "parenttype": "Serial and Batch Bundle"},
                    ["serial_no", "batch_no", "qty"],
                    as_dict=True,
                    for_update=True,
                    wait=False,
                    order_by="name",
                ),
            )
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()
        if bundle_doc.docstatus == 2 or bundle_doc.is_cancelled or not entries:
            frappe.throw(_("The supplied Serial and Batch Bundle is missing or inactive."))
        if (
            bundle_doc.get("item_code") != row.get("item_code")
            or bundle_doc.get("warehouse") != row.get("s_warehouse")
            or bundle_doc.get("type_of_transaction") != "Outward"
        ):
            frappe.throw(_("The supplied Serial and Batch Bundle does not match the source row."))
        try:
            transfer_qty = Decimal(str(row.get("transfer_qty") or 0))
            bundle_qty = abs(Decimal(str(bundle_doc.get("total_qty") or 0)))
        except (InvalidOperation, ValueError, TypeError):
            frappe.throw(_("The supplied Serial and Batch Bundle has an invalid quantity."))
        if bundle_qty != transfer_qty:
            frappe.throw(_("The supplied Serial and Batch Bundle quantity does not match the source row."))
        for entry in entries:
            try:
                entry_qty = Decimal(str(entry.get("qty") or 0))
                quantity = abs(entry_qty)
            except (InvalidOperation, ValueError, TypeError):
                frappe.throw(_("The supplied Serial and Batch Bundle has an invalid quantity."))
            serial = str(entry.get("serial_no") or "")
            batch = str(entry.get("batch_no") or "")
            if (item.has_serial_no and not serial) or (item.has_batch_no and not batch) or not quantity:
                frappe.throw(_("The supplied Serial and Batch Bundle has incomplete tracked identities."))
            if entry_qty >= 0:
                frappe.throw(_("The supplied Serial and Batch Bundle must contain outward quantities."))
            requested[(serial, batch)] += quantity
    elif item.has_serial_no or item.has_batch_no:
        serials = [value.strip() for value in str(row.get("serial_no") or "").splitlines() if value.strip()]
        batch = str(row.get("batch_no") or "").strip()
        try:
            transfer_qty = Decimal(str(row.get("transfer_qty") or 0))
        except (InvalidOperation, ValueError, TypeError):
            frappe.throw(_("Stock UOM transfer quantity is invalid."))
        if item.has_serial_no and serials:
            for serial in serials:
                requested[(serial, batch)] += Decimal(1)
        elif item.has_batch_no and batch:
            requested[("", batch)] = transfer_qty

    try:
        transfer_qty = Decimal(str(row.get("transfer_qty") or 0))
    except (InvalidOperation, ValueError, TypeError):
        frappe.throw(_("Stock UOM transfer quantity is invalid."))
    if not requested or sum(requested.values(), Decimal(0)) != transfer_qty:
        frappe.throw(_("Tracked Stock Entry rows must specify exact source identities in Stock UOM."))
    if any(
        (item.has_serial_no and not serial) or (item.has_batch_no and not batch)
        for serial, batch in requested
    ):
        frappe.throw(_("Tracked Stock Entry rows must specify complete Batch and Serial identities."))
    return dict(requested)


def _tracked_source_projection(
    doc: Document,
) -> tuple[dict[str, dict[tuple[str, str], Decimal]], list[dict[str, Any]]]:
    """Lock one canonical identity projection for approval digest and submit capture."""
    identities_by_row: dict[str, dict[tuple[str, str], Decimal]] = {}
    source_snapshot: list[dict[str, Any]] = []
    for row in doc.get("items") or []:
        item_code = str(row.get("item_code") or "")
        item = cast(
            frappe._dict | None,
            frappe.get_cached_value("Item", item_code, ["has_serial_no", "has_batch_no"], as_dict=True),
        )
        if not item or not (item.has_serial_no or item.has_batch_no):
            continue
        source_location = str(row.get("storage_location") or "")
        if not source_location:
            frappe.throw(_("Tracked transfers require an exact source Storage Location."))
        requested = _requested_tracked_identities(row, item)
        snapshot = snapshot_location(
            company=str(doc.get("company") or ""),
            item_code=item_code,
            warehouse=str(row.get("s_warehouse") or ""),
            storage_location=source_location,
            cutoff=f"{doc.get('posting_date')} {doc.get('posting_time') or '00:00:00'}",
            locking_read=True,
        )
        available = {(serial, batch): quantity for serial, batch, quantity in snapshot.identities}
        bound: list[tuple[str, str, str, str]] = []
        for (serial, batch), quantity in sorted(requested.items()):
            source_qty = available.get((serial, batch), Decimal(0))
            if source_qty < quantity:
                frappe.throw(
                    _("Selected Batch/Serial stock is not available at the source Storage Location.")
                )
            bound.append((serial, batch, str(quantity), str(source_qty)))
        row_name = str(row.name)
        identities_by_row[row_name] = requested
        source_snapshot.append({"row": row_name, "identities": bound})
    return identities_by_row, source_snapshot


def _approval_digest(doc: Document, tracked_source_snapshot: list[dict[str, Any]]) -> str:
    return critical_digest(
        {"transfer": _approval_payload(doc), "tracked_source_snapshot": tracked_source_snapshot}
    )


def validate_after_submit(doc: Document, method: str | None = None) -> None:
    """Verify native ledger identities after ERPNext posts an approved direct transfer."""
    del method
    if not is_direct_transfer(doc):
        return
    if int(doc.docstatus) != 1 or not doc.name:
        frappe.throw(_("Stock Transfer ledger verification requires a submitted document."))

    capture = cast(dict[str, Any] | None, doc.flags.get(_SUBMIT_IDENTITY_CAPTURE))
    if capture is None:
        frappe.throw(_("Stock Transfer ledger verification has no current approved identity capture."))
    capture_doc = cast(dict[str, Any], capture)
    if capture_doc.get("name") != doc.name or capture_doc.get("approval_critical_digest") != doc.get(
        "approval_critical_digest"
    ):
        frappe.throw(_("Stock Transfer ledger verification has no current approved identity capture."))
    tracked_projection = cast(
        dict[str, dict[tuple[str, str], Decimal]], capture_doc.get("tracked_identities") or {}
    )
    rows = list(doc.get("items") or [])
    row_names = [str(row.name) for row in rows]
    ledger_rows = frappe.get_all(
        "Stock Ledger Entry",
        filters={
            "voucher_type": "Stock Entry",
            "voucher_no": doc.name,
            "voucher_detail_no": ["in", row_names],
            "is_cancelled": 0,
        },
        fields=[
            "name",
            "voucher_detail_no",
            "item_code",
            "warehouse",
            "actual_qty",
            "storage_location",
            "serial_and_batch_bundle",
            "serial_no",
            "batch_no",
        ],
    )
    by_row: dict[str, list[frappe._dict]] = defaultdict(list)
    for ledger_row in ledger_rows:
        by_row[str(ledger_row.get("voucher_detail_no") or "")].append(ledger_row)

    bundle_names = sorted(
        {
            str(ledger_row.get("serial_and_batch_bundle"))
            for ledger_row in ledger_rows
            if ledger_row.get("serial_and_batch_bundle")
        }
    )
    bundles: dict[str, frappe._dict] = {}
    bundle_entries: dict[str, dict[tuple[str, str], Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    if bundle_names:
        for bundle in frappe.get_all(
            "Serial and Batch Bundle",
            filters={"name": ["in", bundle_names]},
            fields=["name", "item_code", "warehouse", "type_of_transaction", "total_qty"],
        ):
            bundles[str(bundle.name)] = bundle
        for entry in frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": ["in", bundle_names], "parenttype": "Serial and Batch Bundle"},
            fields=["parent", "serial_no", "batch_no", "qty"],
        ):
            try:
                bundle_entries[str(entry.parent)][
                    (str(entry.get("serial_no") or ""), str(entry.get("batch_no") or ""))
                ] += abs(Decimal(str(entry.get("qty") or 0)))
            except (InvalidOperation, ValueError, TypeError):
                frappe.throw(_("Posted Serial and Batch Bundle has an invalid quantity."))

    if len(ledger_rows) != 2 * len(rows):
        frappe.throw(_("Posted Stock Transfer must create one source and one target ledger row per item."))

    for row in rows:
        row_name = str(row.name)
        try:
            transfer_qty = Decimal(str(row.get("transfer_qty") or 0))
        except (InvalidOperation, ValueError, TypeError):
            frappe.throw(_("Stock UOM transfer quantity is invalid."))
        source_warehouse = str(row.get("s_warehouse") or "")
        target_warehouse = str(row.get("t_warehouse") or "")
        source_location = str(row.get("storage_location") or "")
        target_location = str(row.get("to_storage_location") or "")
        row_ledger = by_row.get(row_name, [])
        source = [
            entry
            for entry in row_ledger
            if entry.get("warehouse") == source_warehouse
            and Decimal(str(entry.get("actual_qty") or 0)) == -transfer_qty
        ]
        target = [
            entry
            for entry in row_ledger
            if entry.get("warehouse") == target_warehouse
            and Decimal(str(entry.get("actual_qty") or 0)) == transfer_qty
        ]
        if len(row_ledger) != 2 or len(source) != 1 or len(target) != 1:
            frappe.throw(_("Posted Stock Transfer ledger quantities do not match the approved rows."))
        source_sle, target_sle = source[0], target[0]
        if any(entry.get("item_code") != row.get("item_code") for entry in (source_sle, target_sle)):
            frappe.throw(_("Posted Stock Transfer ledger item does not match the approved row."))
        if (
            str(source_sle.get("storage_location") or "") != source_location
            or str(target_sle.get("storage_location") or "") != target_location
        ):
            frappe.throw(_("Posted Stock Transfer ledger Storage Location does not match the approved row."))

        item = cast(
            frappe._dict | None,
            frappe.get_cached_value(
                "Item",
                str(row.get("item_code") or ""),
                ["has_serial_no", "has_batch_no"],
                as_dict=True,
            ),
        )
        if not item or not (item.has_serial_no or item.has_batch_no):
            continue
        expected = tracked_projection.get(row_name)
        if expected is None:
            frappe.throw(_("Approved Stock Transfer is missing its tracked identity projection."))
        expected = cast(dict[tuple[str, str], Decimal], expected)
        for sle, warehouse, transaction_type in (
            (source_sle, source_warehouse, "Outward"),
            (target_sle, target_warehouse, "Inward"),
        ):
            bundle_name = str(sle.get("serial_and_batch_bundle") or "")
            if not bundle_name:
                _validate_legacy_sle_identities(sle, expected, item)
                continue
            bundle = bundles.get(bundle_name)
            if bundle is None:
                frappe.throw(_("Posted Stock Transfer ledger has a mismatched Batch/Serial Bundle."))
            bundle_doc = cast(frappe._dict, bundle)
            if (
                bundle_doc.get("item_code") != row.get("item_code")
                or bundle_doc.get("warehouse") != warehouse
                or bundle_doc.get("type_of_transaction") != transaction_type
            ):
                frappe.throw(_("Posted Stock Transfer ledger has a mismatched Batch/Serial Bundle."))
            actual_identities = dict(bundle_entries.get(bundle_name, {}))
            if actual_identities != expected:
                frappe.throw(_("Posted Stock Transfer Batch/Serial identities differ from the approved row."))
            if abs(Decimal(str(bundle_doc.get("total_qty") or 0))) != transfer_qty:
                frappe.throw(_("Posted Stock Transfer Batch/Serial quantity differs from the approved row."))
    doc.flags.pop(_SUBMIT_IDENTITY_CAPTURE, None)


def _validate_legacy_sle_identities(
    ledger_row: frappe._dict,
    expected: dict[tuple[str, str], Decimal],
    item: frappe._dict,
) -> None:
    """Check the legacy SLE serial/batch fields against the pre-submit projection."""
    expected_serials = sorted(serial for serial, _batch in expected if serial)
    actual_serials = sorted(
        value.strip()
        for value in str(ledger_row.get("serial_no") or "").replace(",", "\n").splitlines()
        if value.strip()
    )
    if item.has_serial_no and actual_serials != expected_serials:
        frappe.throw(_("Posted Stock Transfer Serial No values differ from the approved row."))

    expected_batches: dict[str, Decimal] = defaultdict(Decimal)
    for (_serial, batch), quantity in expected.items():
        if batch:
            expected_batches[batch] += quantity
    actual_batch = str(ledger_row.get("batch_no") or "")
    if item.has_batch_no and (len(expected_batches) != 1 or actual_batch != next(iter(expected_batches), "")):
        frappe.throw(_("Posted Stock Transfer Batch No differs from the approved row."))


def get_approval_digest(doc: Document) -> str:
    """Bind approval to the direct transfer values that control native posting."""
    _tracked_identities, tracked_source_snapshot = _tracked_source_projection(doc)
    return _approval_digest(doc, tracked_source_snapshot)


def _validate_transfer_locations(doc: Document) -> None:
    """Validate exact locations and current read scope on a direct transfer."""
    checked_warehouses: set[str] = set()
    checked_locations: set[tuple[str, str]] = set()
    for row in doc.get("items") or []:
        source_warehouse = str(row.get("s_warehouse") or "")
        target_warehouse = str(row.get("t_warehouse") or "")
        source = str(row.get("storage_location") or "")
        target = str(row.get("to_storage_location") or "")
        if not source_warehouse or source_warehouse != target_warehouse:
            frappe.throw(_("Direct Material Transfers must stay within one Warehouse."))
        if not source or not target:
            frappe.throw(_("Both source and target Storage Locations are required."))
        if source == target:
            frappe.throw(_("Source and target Storage Locations must be different."))
        for warehouse in (source_warehouse, target_warehouse):
            if warehouse not in checked_warehouses:
                require_operational_warehouse(warehouse)
                checked_warehouses.add(warehouse)
        for location, warehouse in ((source, source_warehouse), (target, target_warehouse)):
            if (location, warehouse) not in checked_locations:
                require_location_warehouse(location, warehouse)
                checked_locations.add((location, warehouse))


def _require_direct_transfer(doc: Document) -> None:
    if not is_direct_transfer(doc):
        frappe.throw(_("Stock Transfer approval requires a direct Material Transfer."))
    _validate_transfer_locations(doc)


def _clear_review_and_approval(doc: Document) -> None:
    for fieldname in _APPROVAL_FIELDS - {"approval_maker_user"}:
        doc.set(fieldname, None)


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    """Capture first Send identity and preserve it through original-maker Resubmit."""
    del method
    _require_direct_transfer(doc)
    route = get_route(ROUTE)
    persisted = frappe.db.get_value(
        "Stock Entry",
        doc.name,
        ["workflow_state", "docstatus", "approval_maker_user"],
        as_dict=True,
        for_update=True,
    )
    if (
        not persisted
        or int(persisted.get("docstatus") or 0) != 0
        or int(doc.docstatus) != 0
        or doc.get("workflow_state") != route.pending_review_state
    ):
        frappe.throw(_("Stock Transfer Send requires a persisted draft transition."))
    maker = str(persisted.get("approval_maker_user") or "")
    if persisted.get("workflow_state") == route.draft_state:
        if maker or doc.get("approval_maker_user"):
            frappe.throw(_("First Stock Transfer Send cannot contain an existing maker."))
        action = route.send_action
    elif persisted.get("workflow_state") == route.returned_state:
        if not maker or doc.get("approval_maker_user") != maker:
            frappe.throw(_("Stock Transfer Resubmit must preserve its original maker."))
        if resolve_user(str(frappe.session.user or "")) != maker:
            frappe.throw(_("Only the original Stock Transfer maker may resubmit."))
        action = route.resubmit_action
    else:
        frappe.throw(_("Stock Transfer Send is unavailable from its current state."))
    user = authorize_workflow_field_write(doc, ROUTE, action, route.maker_roles)
    _clear_review_and_approval(doc)
    doc.set("approval_maker_user", maker or user)
    doc.set("approval_critical_digest", get_approval_digest(doc))


def capture_review_snapshot(doc: Document, method: str | None = None) -> None:
    """Bind a signed, distinct Review action to the full current transfer payload."""
    del method
    _require_direct_transfer(doc)
    if str(doc.get("approval_critical_digest") or "") != get_approval_digest(doc):
        frappe.throw(_("The Stock Entry or its source stock changed after Maker submission."))
    route = get_route(ROUTE)
    snapshot = authorize_approval_field_write(
        doc,
        ROUTE,
        route.review_action,
        route.reviewer_roles,
        str(doc.get("approval_maker_user") or ""),
    )
    doc.set("approval_reviewer_user", snapshot.user)
    doc.set("checked_by", snapshot.employee)
    doc.set("checked_at", snapshot.acted_at)
    doc.set("checked_signature", snapshot.signature)


def capture_approval_snapshot(doc: Document, method: str | None = None) -> None:
    """Capture a signed Final Approver distinct from maker and checker."""
    del method
    _require_direct_transfer(doc)
    if str(doc.get("approval_critical_digest") or "") != get_approval_digest(doc):
        frappe.throw(_("The Stock Entry changed after review and must be reviewed again."))
    if not all(
        doc.get(field)
        for field in ("approval_reviewer_user", "checked_by", "checked_at", "checked_signature")
    ):
        frappe.throw(_("Signed Stock Transfer review evidence is required before approval."))
    route = get_route(ROUTE)
    snapshot = authorize_approval_field_write(
        doc,
        ROUTE,
        route.approve_action,
        route.final_approver_roles,
        str(doc.get("approval_maker_user") or ""),
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    doc.set("approval_authorized_user", snapshot.user)
    doc.set("authorized_by", snapshot.employee)
    doc.set("authorized_at", snapshot.acted_at)
    doc.set("authorized_signature", snapshot.signature)


def reset_approval(doc: Document, method: str | None = None) -> None:
    """Clear signed evidence through a protected Return transition."""
    del method
    _require_direct_transfer(doc)
    route = get_route(ROUTE)
    if doc.get("workflow_state") != route.returned_state:
        frappe.throw(_("Stock Transfer Return must enter the Returned state."))
    previous_state = frappe.db.get_value("Stock Entry", doc.name, "workflow_state", for_update=True)
    if previous_state not in {route.pending_review_state, route.reviewed_state, route.approved_state}:
        frappe.throw(_("Stock Transfer cannot be returned from its current state."))
    roles = (
        route.reviewer_roles if previous_state == route.pending_review_state else route.final_approver_roles
    )
    authorize_workflow_field_write(doc, ROUTE, route.return_action, roles)
    _clear_review_and_approval(doc)


def reject_approval(doc: Document, method: str | None = None) -> None:
    """Authorize a final approver's rejection without retaining signed approval evidence."""
    del method
    _require_direct_transfer(doc)
    route = get_route(ROUTE)
    if (
        doc.get("workflow_state") != "Stock Transfer Rejected"
        or frappe.db.get_value("Stock Entry", doc.name, "workflow_state", for_update=True)
        != route.reviewed_state
    ):
        frappe.throw(_("Stock Transfer Rejection requires the Reviewed state."))
    require_distinct_actors(
        str(doc.get("approval_maker_user") or ""),
        resolve_user(str(frappe.session.user or "")),
        (str(doc.get("approval_reviewer_user") or ""),),
    )
    authorize_workflow_field_write(doc, ROUTE, route.reject_action, route.final_approver_roles)
    _clear_review_and_approval(doc)


def _reject_critical_changes_after_review(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.get("workflow_state") not in _REVIEW_LOCKED_STATES:
        return
    previous_payload = _approval_payload(previous)
    current_payload = _approval_payload(doc)
    changed = [
        key
        for key in previous_payload
        if critical_digest({key: previous_payload[key]}) != critical_digest({key: current_payload[key]})
    ]
    if changed:
        frappe.throw(
            _(
                "Critical Stock Entry fields cannot change after review. Return it for correction first: {0}."
            ).format(", ".join(changed))
        )


def validate_workflow(doc: Document, method: str | None = None) -> None:
    """Permit protected state and evidence writes only from a native task grant."""
    del method
    if _validate_count_entry(doc, "validate"):
        return
    _reject_excluded_material_transfer(doc)
    state = str(doc.get("workflow_state") or "")
    if state.startswith("Stock Transfer") and not is_direct_transfer(doc):
        frappe.throw(_("Stock Transfer workflow is limited to direct Material Transfer entries."))
    if has_freeze_exception(doc):
        if not is_direct_transfer(doc) or not str(doc.get(EXCEPTION_REASON) or "").strip():
            frappe.throw(_("Freeze Exception requires a reason and a direct Material Transfer."))
        frappe.throw(_("Emergency Stock Movement requires its approved native Workflow route."))
    if state in EMERGENCY_STATES:
        frappe.throw(_("Emergency Stock Movement requires its approved native Workflow route."))
    if not is_direct_transfer(doc):
        previous = doc.get_doc_before_save()
        if previous and previous.get("workflow_state") in _REVIEW_LOCKED_STATES:
            frappe.throw(_("A reviewed Stock Transfer cannot leave the direct transfer route."))
        return
    route = get_route(ROUTE)
    require_native_terminal_state(doc, route.submitted_state, "Stock Transfer Cancelled")
    if doc.is_new():
        if state not in {"", route.draft_state}:
            frappe.throw(_("New Stock Transfers must start in Draft."))
        if any(doc.get(field) for field in _APPROVAL_FIELDS):
            frappe.throw(_("New Stock Transfers cannot contain approval evidence."))
        return
    previous = doc.get_doc_before_save()
    if not previous:
        frappe.throw(_("Existing Stock Transfer state cannot be verified."))
    _reject_critical_changes_after_review(doc)
    before = str(previous.get("workflow_state") or "")
    action = next(
        (
            action_name
            for action_name, old, new in (
                (route.send_action, route.draft_state, route.pending_review_state),
                (route.resubmit_action, route.returned_state, route.pending_review_state),
                (route.review_action, route.pending_review_state, route.reviewed_state),
                (route.approve_action, route.reviewed_state, route.approved_state),
                (route.return_action, route.pending_review_state, route.returned_state),
                (route.return_action, route.reviewed_state, route.returned_state),
                (route.return_action, route.approved_state, route.returned_state),
                (route.reject_action, route.reviewed_state, "Stock Transfer Rejected"),
                (route.execute_action, route.approved_state, route.submitted_state),
            )
            if before == old and state == new
        ),
        None,
    )
    changed = {field for field in _APPROVAL_FIELDS if doc.get(field) != previous.get(field)}
    if before != state and not action:
        frappe.throw(_("Stock Transfer state changed outside an approved Workflow transition."))
    if not action:
        if changed:
            frappe.throw(_("Stock Transfer approval evidence may only change through Workflow."))
        return
    allowed = {
        route.send_action: {"approval_maker_user", "approval_critical_digest"},
        route.resubmit_action: _APPROVAL_FIELDS - {"approval_maker_user"},
        route.review_action: {
            "approval_reviewer_user",
            "approval_critical_digest",
            "checked_by",
            "checked_at",
            "checked_signature",
        },
        route.approve_action: {
            "approval_authorized_user",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        },
        route.return_action: _APPROVAL_FIELDS - {"approval_maker_user"},
        route.reject_action: _APPROVAL_FIELDS - {"approval_maker_user"},
        route.execute_action: set(),
    }[action]
    if not changed.issubset(allowed):
        frappe.throw(_("Stock Transfer approval evidence changed outside its Workflow action."))
    if state in {route.pending_review_state, route.reviewed_state, route.approved_state}:
        if not doc.get("approval_maker_user") or doc.get("approval_critical_digest") != get_approval_digest(
            doc
        ):
            frappe.throw(_("Stock Transfer maker evidence is missing or stale."))
    if state in {route.reviewed_state, route.approved_state}:
        if not all(
            doc.get(field)
            for field in ("approval_reviewer_user", "checked_by", "checked_at", "checked_signature")
        ):
            frappe.throw(_("Signed Stock Transfer review evidence is required."))
    if state == route.approved_state:
        if not all(
            doc.get(field)
            for field in (
                "approval_authorized_user",
                "authorized_by",
                "authorized_at",
                "authorized_signature",
            )
        ):
            frappe.throw(_("Signed Stock Transfer approval evidence is required."))
        require_distinct_actors(
            str(doc.get("approval_maker_user") or ""),
            str(doc.get("approval_authorized_user") or ""),
            (str(doc.get("approval_reviewer_user") or ""),),
        )
    if action != route.execute_action:
        consume_approval_field_grant(doc, ROUTE, action)


def validate_after_submit_update(doc: Document, method: str | None = None) -> None:
    """Lock a submitted Stock Transfer in its native submitted state and direct route."""
    del method
    if _validate_count_entry(doc, "before_update_after_submit"):
        return
    previous = doc.get_doc_before_save()
    current_state = str(doc.get("workflow_state") or "")
    previous_state = str(previous.get("workflow_state") or "") if previous else ""
    if not (current_state.startswith("Stock Transfer ") or previous_state.startswith("Stock Transfer ")):
        return
    require_locked_submitted_update(doc, get_route(ROUTE).submitted_state)
    if not is_direct_transfer(doc):
        frappe.throw(_("Submitted Stock Transfer cannot leave the direct transfer route."))


def authorize_submit_execution(doc: Document, method: str | None = None) -> None:
    del method
    _reject_excluded_material_transfer(doc)
    _require_direct_transfer(doc)
    route = get_route(ROUTE)
    authorize_workflow_field_write(
        doc, ROUTE, route.execute_action, route.execution_roles, permission="submit"
    )


def authorize_cancel_execution(doc: Document, method: str | None = None) -> None:
    del method
    _reject_excluded_material_transfer(doc)
    _require_direct_transfer(doc)
    authorize_workflow_field_write(
        doc, ROUTE, _CANCEL_ACTION, get_route(ROUTE).execution_roles, permission="cancel"
    )


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    """Prevent direct Material Transfer submission without native approval."""
    del method
    if _validate_count_entry(doc, "before_submit"):
        return
    try:
        _reject_excluded_material_transfer(doc)
        validate_workflow(doc)
        if not is_direct_transfer(doc):
            return
        route = get_route(ROUTE)
        if doc.get("workflow_state") not in APPROVED_STATES:
            frappe.throw(_("Direct stock transfers must be approved through the Stock Entry Workflow."))
        current_user = resolve_user(str(frappe.session.user or ""))
        if not set(frappe.get_roles(current_user)).intersection(route.execution_roles):
            frappe.throw(_("Only an authorized Stock Manager may submit this transfer."))
        require_permission(doc, "submit")
        _validate_transfer_locations(doc)
        tracked_identities, tracked_source_snapshot = _tracked_source_projection(doc)
        current_digest = _approval_digest(doc, tracked_source_snapshot)
        persisted = cast(
            dict[str, Any] | None,
            frappe.db.get_value(
                "Stock Entry",
                doc.name,
                ["workflow_state", *sorted(_APPROVAL_FIELDS)],
                as_dict=True,
                for_update=True,
            ),
        )
        if not persisted or persisted.get("workflow_state") != route.approved_state:
            frappe.throw(_("Stock Transfer must be submitted through its approved Workflow action."))
        assert persisted is not None
        if persisted.get("approval_critical_digest") != current_digest:
            frappe.throw(_("The Stock Entry approval is stale and must be renewed."))
        for field in _APPROVAL_FIELDS:
            if not persisted.get(field) or str(persisted.get(field)) != str(doc.get(field)):
                frappe.throw(_("Signed Stock Transfer approval evidence is incomplete or stale."))
        require_distinct_actors(
            str(persisted.get("approval_maker_user") or ""),
            str(persisted.get("approval_authorized_user") or ""),
            (str(persisted.get("approval_reviewer_user") or ""),),
        )
        consume_approval_field_grant(doc, ROUTE, route.execute_action)
        doc.flags[_SUBMIT_IDENTITY_CAPTURE] = {
            "name": doc.name,
            "approval_critical_digest": persisted.get("approval_critical_digest"),
            "tracked_identities": tracked_identities,
        }
    except Exception:
        clear_freeze_exception_execution()
        raise


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    """Keep direct transfers on the native Workflow cancel transition."""
    del method
    if _validate_count_entry(doc, "before_cancel"):
        return
    _reject_excluded_material_transfer(doc)
    if not is_direct_transfer(doc):
        return
    current_user = resolve_user(str(frappe.session.user or ""))
    if not set(frappe.get_roles(current_user)).intersection(get_route(ROUTE).execution_roles):
        frappe.throw(_("Only an authorized Stock Manager may cancel this transfer."))
    require_permission(doc, "cancel")
    persisted_state = frappe.db.get_value(
        "Stock Entry",
        doc.name,
        "workflow_state",
        for_update=True,
    )
    if not (
        persisted_state == "Stock Transfer Submitted"
        and doc.get("workflow_state") == "Stock Transfer Cancelled"
    ):
        frappe.throw(_("Direct stock transfers must be cancelled through their Workflow action."))
    consume_approval_field_grant(doc, ROUTE, _CANCEL_ACTION)
