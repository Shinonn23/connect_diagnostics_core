# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Authenticated exact-location Stock Count observation and decision APIs."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import get_transitions
from frappe.utils import now

from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import (
    _cancellation_gl_source,
    _insert_count_evidence,
    account_submit_grant,
    count_revision_accepts_observations,
    parent_write_grant,
)
from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_warehouses

_REASON_ACTIONS = frozenset(
    {
        "Return Count for Recount",
        "Return Count from Stock Approval",
        "Return Count from Accounting",
        "Return Approved Count for Recapture",
        "Restart Frozen Count after Invalidation",
        "Restart Count after Invalidation",
        "Restart Approved Count after Invalidation",
        "Restart Returned Count after Invalidation",
        "Restart Recapture after Invalidation",
        "Reject Count from Review",
        "Reject Count from Stock Approval",
        "Reject Restarted Count",
        "Reject Recaptured Count",
        "Abandon Draft Count",
        "Abandon Frozen Count",
        "Abandon Pending Review Count",
        "Abandon Returned Count",
        "Abandon Pending Approval Count",
        "Abandon Pending Accounting Count",
        "Abandon Approved Count",
        "Abandon Restarted Count",
        "Abandon Recaptured Count",
        "Request Count Cancellation Accounting Review",
        "Return Count Cancellation Review",
        "Return Approved Count Cancellation",
    }
)


def _visible_session(name: str, permission: str) -> Document:
    if not isinstance(name, str) or not name or not frappe.db.exists("Stock Count Session", name):
        frappe.throw(_("Select an existing Stock Count Session."))
    doc = cast(Document, frappe.get_doc("Stock Count Session", name))
    if not frappe.has_permission(doc.doctype, ptype=permission, doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission for this Count Session."))
    return doc


def _current_session(name: str, warehouses: set[str]) -> Document:
    lock_warehouses(warehouses)
    if not frappe.db.get_value("Stock Count Session", name, "name", for_update=True, wait=False):
        frappe.throw(_("Count Session changed; reload and retry."))
    # Frappe loads both parent and child tables with current reads for for_update.
    # A plain get_doc after the lock can reuse an older RR snapshot of child rows.
    doc = cast(Document, frappe.get_doc("Stock Count Session", name, for_update=True))
    if not frappe.has_permission(doc.doctype, ptype="write", doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission for this Count Session."))
    return doc


def _quantity(value: object) -> Decimal:
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        frappe.throw(_("Count quantity must be a finite number."))
    if not qty.is_finite() or qty < 0:
        frappe.throw(_("Count quantity must be finite and nonnegative."))
    return qty


def _employee_for_user(user: str) -> str:
    matches = frappe.db.get_values(
        "Employee",
        {"user_id": user, "status": "Active"},
        "name",
        pluck=True,
        order_by="name",
        limit=2,
    )
    if len(matches) > 1:
        frappe.throw(_("The Count actor has multiple active Employee records."))
    return str(matches[0]) if matches else ""


@frappe.whitelist()
def record_observation(
    session: str,
    line_key: str,
    evidence_revision: int,
    pass_type: str,
    counted_qty: float | str,
    note: str = "",
) -> dict[str, object]:
    """Append one actor-signed current-revision physical observation."""
    preliminary = _visible_session(session, "write")
    if "Stock User" not in frappe.get_roles():
        raise frappe.PermissionError(_("Only Stock User may record count observations."))
    candidates = [
        row
        for row in preliminary.get("items") or []
        if row.get("line_key") == line_key
        and int(row.get("evidence_revision") or 0) == int(evidence_revision)
    ]
    if len(candidates) != 1:
        frappe.throw(_("The current Count line was not found."))
    doc = _current_session(session, {str(candidates[0].warehouse)})
    if not count_revision_accepts_observations(doc):
        frappe.throw(_("The current Count revision is unavailable for observation."))
    if int(doc.get("evidence_revision") or 0) != int(evidence_revision):
        frappe.throw(_("Count revision changed; reload and count again."))
    lines = [
        row
        for row in doc.get("items") or []
        if row.get("line_key") == line_key
        and int(row.get("evidence_revision") or 0) == int(evidence_revision)
    ]
    if len(lines) != 1 or lines[0].name != candidates[0].name:
        frappe.throw(_("Count line changed; reload and count again."))
    line = lines[0]
    if pass_type not in {"Initial", "Recount"}:
        frappe.throw(_("Choose Initial or Recount observation."))
    qty = _quantity(counted_qty)
    if line.get("serial_no") and qty not in {Decimal(0), Decimal(1)}:
        frappe.throw(_("A Serial count must be zero or one."))
    existing = frappe.db.get_values(
        "Stock Count Observation",
        {"session": session, "line_key": line_key, "evidence_revision": evidence_revision},
        ["name", "pass_type", "observer_user"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    if pass_type == "Initial" and existing:
        frappe.throw(_("This line already has an Initial count; use Recount when required."))
    initial = next((row for row in existing if row.pass_type == "Initial"), None)
    if pass_type == "Recount" and (
        initial is None
        or Decimal(str(line.get("system_qty") or 0)) == Decimal(str(line.get("counted_qty") or 0))
    ):
        frappe.throw(_("Recount requires a completed Initial observation with a variance."))
    user = str(frappe.session.user)
    if (
        pass_type == "Recount"
        and initial is not None
        and (user == initial.observer_user or user == doc.get("checker_user"))
    ):
        frappe.throw(_("Recount must use an independent observer."))
    observed_at = now()
    employee = _employee_for_user(user)
    clean_note = str(note or "")[:1000]
    digest = sha256(
        json.dumps(
            {
                "session": session,
                "line_key": line_key,
                "revision": evidence_revision,
                "pass_type": pass_type,
                "identity": {
                    field: str(line.get(field) or "")
                    for field in (
                        "item_code",
                        "company",
                        "warehouse",
                        "storage_location",
                        "batch_no",
                        "serial_no",
                    )
                },
                "counted_qty": str(qty),
                "count_uom": str(line.get("stock_uom")),
                "observer_user": user,
                "observer_employee": employee,
                "observed_at": observed_at,
                "note": clean_note,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    observation = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Stock Count Observation",
                "session": session,
                "line_key": line_key,
                "evidence_revision": evidence_revision,
                "pass_type": pass_type,
                **{
                    field: line.get(field)
                    for field in (
                        "item_code",
                        "company",
                        "warehouse",
                        "storage_location",
                        "stock_uom",
                        "batch_no",
                        "serial_no",
                    )
                },
                "counted_qty": float(qty),
                "count_uom": line.stock_uom,
                "observer_user": user,
                "observer_employee": employee,
                "observed_at": observed_at,
                "note": clean_note,
                "signature_digest": digest,
            }
        ),
    )
    _insert_count_evidence(observation)
    line.latest_observation = observation.name
    line.counted_qty = float(qty)
    line.variance_qty = float(qty - Decimal(str(line.get("system_qty") or 0)))
    line.recount_required = bool(pass_type == "Initial" and line.variance_qty)
    line.recount_complete = pass_type == "Recount"
    line.line_state = "Recounted" if pass_type == "Recount" else "Counted"
    with parent_write_grant(doc, {"items"}):
        doc.save()
    return {"data": {"observation": observation.name}, "message": "Count observation recorded."}


@frappe.whitelist()
def set_stock_count_decision_reason(session: str, action: str, reason: str) -> dict[str, object]:
    """Persist one action-bound reason; native Desk applies the Workflow once."""
    preliminary = _visible_session(session, "write")
    warehouses = {str(row.warehouse) for row in preliminary.get("scope") or []}
    doc = _current_session(session, warehouses)
    if action not in _REASON_ACTIONS or not any(
        transition.get("action") == action for transition in get_transitions(doc)
    ):
        frappe.throw(_("The selected Count decision is unavailable."))
    clean = str(reason or "").strip()
    if not clean or len(clean) > 1000:
        frappe.throw(_("Give a decision reason of at most 1000 characters."))
    cancellation_action = action in {
        "Request Count Cancellation Accounting Review",
        "Return Count Cancellation Review",
        "Return Approved Count Cancellation",
    }
    reason_digest = (
        _cancellation_gl_source(doc)[1] if cancellation_action else doc.get("snapshot_digest") or ""
    )
    for field, value in {
        "pending_reason_action": action,
        "pending_reason_actor": str(frappe.session.user),
        "pending_reason_state": doc.get("workflow_state"),
        "pending_reason_revision": doc.get("evidence_revision") or 0,
        "pending_reason_digest": reason_digest,
        "pending_reason_text": clean,
        "pending_reason_at": now(),
    }.items():
        doc.set(field, value)
    # This endpoint is deliberately reason-only. The native Desk Workflow
    # controller reloads the persisted document and invokes apply_workflow.
    with parent_write_grant(doc, {field for field in doc.as_dict() if field.startswith("pending_reason_")}):
        if action in {"Return Count Cancellation Review", "Return Approved Count Cancellation"}:
            with account_submit_grant(doc, action, str(doc.get("workflow_state") or "")):
                doc.save()
        else:
            doc.save()
    return {"data": {"action": action}, "message": "Decision reason saved."}


@frappe.whitelist()
def record_location_coverage(
    session: str, scope_row: str, storage_location: str, evidence_revision: int
) -> dict[str, object]:
    """Sign the current revision's physical location checklist row."""
    preliminary = _visible_session(session, "write")
    if "Stock User" not in frappe.get_roles():
        raise frappe.PermissionError(_("Only Stock User may confirm Count locations."))
    selected = [row for row in preliminary.get("scope") or [] if row.name == scope_row]
    if len(selected) != 1:
        frappe.throw(_("Select one current Count scope row."))
    warehouse = str(selected[0].warehouse)
    if not any(
        row.get("scope_row") == scope_row
        and row.get("storage_location") == storage_location
        and int(row.get("evidence_revision") or 0) == int(evidence_revision)
        for row in preliminary.get("locations") or []
    ):
        frappe.throw(_("This Storage Location is outside the current Count checklist."))
    doc = _current_session(session, {warehouse})
    if not count_revision_accepts_observations(doc):
        frappe.throw(_("Count location confirmation is unavailable in this state."))
    if int(doc.get("evidence_revision") or 0) != int(evidence_revision):
        frappe.throw(_("Count revision changed; reload before confirming the location."))
    matches = [
        row
        for row in doc.get("locations") or []
        if row.get("scope_row") == scope_row
        and row.get("storage_location") == storage_location
        and int(row.get("evidence_revision") or 0) == int(evidence_revision)
    ]
    if len(matches) != 1 or matches[0].coverage_state != "Not Started":
        frappe.throw(_("Count location was already confirmed or changed."))
    row = matches[0]
    row.coverage_state = "Counted"
    row.counter_user = str(frappe.session.user)
    row.counted_at = now()
    row.completed_at = row.counted_at
    with parent_write_grant(doc, {"locations"}):
        doc.save()
    return {"data": {"location": row.name}, "message": "Count location confirmed."}


@frappe.whitelist()
def get_count_baseline(session: str) -> dict[str, object]:
    """Return visible current system quantities and physical count progress."""
    doc = _visible_session(session, "read")
    revision = int(doc.get("evidence_revision") or 0)
    rows = [
        {
            "line_key": row.get("line_key"),
            "item_code": row.get("item_code"),
            "warehouse": row.get("warehouse"),
            "storage_location": row.get("storage_location"),
            "batch_no": row.get("batch_no"),
            "serial_no": row.get("serial_no"),
            "system_qty": row.get("system_qty"),
            "counted_qty": row.get("counted_qty"),
            "variance_qty": row.get("variance_qty"),
            "line_state": row.get("line_state"),
        }
        for row in doc.get("items") or []
        if int(row.get("evidence_revision") or 0) == revision
    ]
    return {
        "data": {"session": doc.name, "evidence_revision": revision, "items": rows},
        "message": "Current Count baseline loaded.",
    }


@frappe.whitelist()
def add_unexpected_count_line(
    session: str,
    item_code: str,
    warehouse: str,
    storage_location: str,
    evidence_revision: int,
    batch_no: str = "",
    serial_no: str = "",
) -> dict[str, object]:
    """Add a physically observed identity only after proving its exact baseline is zero."""
    from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import _line_key
    from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
    from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
        require_location_warehouse,
    )

    preliminary = _visible_session(session, "write")
    if "Stock User" not in frappe.get_roles():
        raise frappe.PermissionError(_("Only Stock User may add observed Count lines."))
    if not any(row.get("warehouse") == warehouse for row in preliminary.get("scope") or []):
        frappe.throw(_("Warehouse is outside the selected Count scope."))
    doc = _current_session(session, {warehouse})
    if not count_revision_accepts_observations(doc):
        frappe.throw(_("Unexpected Count lines require an active current count."))
    if int(doc.get("evidence_revision") or 0) != int(evidence_revision):
        frappe.throw(_("Count revision changed; reload and count again."))
    if not any(
        row.get("warehouse") == warehouse
        and (doc.get("scope_type") == "Full" or row.get("item_code") == item_code)
        for row in doc.get("scope") or []
    ):
        frappe.throw(_("Item is outside the selected Cycle Count scope."))
    if not any(
        row.get("warehouse") == warehouse
        and row.get("storage_location") == storage_location
        and int(row.get("evidence_revision") or 0) == evidence_revision
        for row in doc.get("locations") or []
    ):
        frappe.throw(_("Storage Location is outside the current Count checklist."))
    require_location_warehouse(storage_location, warehouse)
    batch, serial = str(batch_no or "").strip(), str(serial_no or "").strip()
    if len(batch) > 140 or len(serial) > 140:
        frappe.throw(_("Batch and Serial identifiers must be at most 140 characters."))
    item = frappe.get_doc("Item", item_code)
    if not frappe.has_permission("Item", ptype="read", doc=item, user=frappe.session.user):
        raise frappe.PermissionError(_("You cannot count this Item."))
    if (
        not item.get("is_stock_item")
        or bool(item.get("has_batch_no")) != bool(batch)
        or bool(item.get("has_serial_no")) != bool(serial)
    ):
        frappe.throw(_("Observed Batch and Serial identity must match Item tracking."))
    snapshot = snapshot_location(
        company=str(doc.get("company")),
        item_code=item_code,
        warehouse=warehouse,
        storage_location=storage_location,
        cutoff=now(),
        locking_read=True,
    )
    existing_qty = (
        next((qty for s, b, qty in snapshot.identities if s == serial and b == batch), Decimal(0))
        if batch or serial
        else snapshot.quantity
    )
    if existing_qty:
        frappe.throw(_("Observed identity already has stock; recapture the full Count scope."))
    key = _line_key(item_code, warehouse, storage_location, batch, serial)
    if any(
        row.get("line_key") == key and int(row.get("evidence_revision") or 0) == evidence_revision
        for row in doc.get("items") or []
    ):
        frappe.throw(_("This Count identity already has a current baseline line."))
    line = doc.append(
        "items",
        {
            "line_key": key,
            "item_code": item_code,
            "company": doc.get("company"),
            "warehouse": warehouse,
            "storage_location": storage_location,
            "stock_uom": item.get("stock_uom"),
            "batch_no": batch,
            "serial_no": serial,
            "evidence_revision": evidence_revision,
            "system_qty": 0,
            "snapshot_at": now(),
            "snapshot_digest": sha256(f"{key}:0".encode()).hexdigest(),
            "baseline_source": "Observed exact zero baseline",
            "line_state": "Pending",
        },
    )
    with parent_write_grant(doc, {"items"}):
        doc.save()
    return {"data": {"line_key": key, "line": line.name}, "message": "Observed Count line added."}


def _native_visible_scope(user: str) -> tuple[set[str], set[str]]:
    """Ask native Frappe list permissions for effective Company/Warehouse visibility."""
    companies = set(
        str(name) for name in frappe.get_list("Company", pluck="name", limit_page_length=0, user=user)
    )
    warehouses = set(
        str(name) for name in frappe.get_list("Warehouse", pluck="name", limit_page_length=0, user=user)
    )
    return companies, warehouses


def _scope_visible(doc: Document, user: str) -> bool:
    companies, warehouses = _native_visible_scope(user)
    scope = doc.get("scope") or []
    return bool(
        doc.get("company") in companies
        and scope
        and all(str(row.get("warehouse") or "") in warehouses for row in scope)
    )


def session_has_permission(doc: Document | None = None, ptype: str = "read", user: str | None = None) -> bool:
    """Preserve native role/DocPerm and effective scope permissions on one Session."""
    actor = str(user or frappe.session.user)
    roles = set(frappe.get_roles(actor))
    grant = getattr(frappe.local, "_stock_count_account_submit_grant", None)
    if (
        ptype == "submit"
        and "Accounts Manager" in roles
        and (grant is not None or "Stock Manager" not in roles)
    ):
        if (
            doc is not None
            and isinstance(grant, dict)
            and grant.get("document") is doc
            and grant.get("actor") == actor
            and not grant.get("seen")
            and doc.docstatus == 1
            and doc.get("workflow_state") == grant.get("state")
            and grant.get("action")
            in {
                "Approve Count Cancellation",
                "Return Count Cancellation Review",
                "Return Approved Count Cancellation",
            }
            and _scope_visible(doc, actor)
        ):
            grant["seen"] = True
            return True
        return False
    allowed = {
        "read": {"Stock User", "Stock Manager", "Accounts Manager", "C-Level Approver", "System Manager"},
        "write": {"Stock User", "Stock Manager", "Accounts Manager"},
        "create": {"Stock User", "Stock Manager"},
        "submit": {"Stock Manager"},
        "cancel": {"Stock Manager"},
    }
    if not roles.intersection(allowed.get(ptype, set())):
        return False
    if doc is None:
        return ptype == "create"
    return _scope_visible(doc, actor)


def _query_condition(table: str, user: str | None) -> str:
    actor = str(user or frappe.session.user)
    roles = set(frappe.get_roles(actor))
    if not roles.intersection(
        {"Stock User", "Stock Manager", "Accounts Manager", "C-Level Approver", "System Manager"}
    ):
        return "1=0"
    companies, warehouses = _native_visible_scope(actor)
    if not companies or not warehouses:
        return "1=0"
    company_values = ",".join(frappe.db.escape(name) for name in sorted(companies))
    warehouse_values = ",".join(frappe.db.escape(name) for name in sorted(warehouses))
    parent = "`tabStock Count Session`"
    condition = (
        f"{parent}.company in ({company_values}) and exists ("
        "select 1 from `tabStock Count Session Scope` count_scope "
        f"where count_scope.parent = {parent}.name and count_scope.parenttype = 'Stock Count Session' "
        "and count_scope.parentfield = 'scope') and not exists ("
        "select 1 from `tabStock Count Session Scope` denied_scope "
        f"where denied_scope.parent = {parent}.name and denied_scope.parenttype = 'Stock Count Session' "
        f"and denied_scope.parentfield = 'scope' and denied_scope.warehouse not in ({warehouse_values}))"
    )
    if table == "Stock Count Session":
        return condition
    return f"exists (select 1 from {parent} where {parent}.name = `tab{table}`.session and {condition})"


def session_query_conditions(user: str | None = None) -> str:
    return _query_condition("Stock Count Session", user)


def observation_query_conditions(user: str | None = None) -> str:
    return _query_condition("Stock Count Observation", user)


def receipt_query_conditions(user: str | None = None) -> str:
    return _query_condition("Stock Count Notification Receipt", user)


def event_query_conditions(user: str | None = None) -> str:
    return _query_condition("Stock Count Evidence Event", user)


def evidence_has_permission(
    doc: Document | None = None, ptype: str = "read", user: str | None = None
) -> bool:
    actor = str(user or frappe.session.user)
    if doc is None or ptype != "read":
        return False
    if doc.doctype == "Stock Count Notification Receipt" and "Stock Manager" not in frappe.get_roles(actor):
        return False
    if not frappe.db.exists("Stock Count Session", doc.get("session")):
        return False
    parent = cast(Document, frappe.get_doc("Stock Count Session", doc.get("session")))
    return session_has_permission(parent, "read", actor)
