# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Current Count leases and protected Count evidence boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_warehouses
from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    require_location_warehouse,
    require_operational_warehouse,
)

_PARENT = "Stock Count Session"
_SCOPE = "Stock Count Session Scope"
_COUNT_POSTING_POLICY = "Scope Freeze Time"
_EVIDENCE = frozenset(
    {
        "Stock Count Observation",
        "Stock Count Notification Receipt",
        "Stock Count Evidence Event",
    }
)


@dataclass(frozen=True)
class ActiveCountScope:
    session: str
    row: str
    warehouse: str
    item_code: str
    revision: int

    def intersects(self, item_code: str, warehouse: str) -> bool:
        return self.warehouse == warehouse and (not self.item_code or self.item_code == item_code)


def get_active_count_scopes(warehouses: set[str]) -> tuple[ActiveCountScope, ...]:
    """Return current committed lease rows after callers hold sorted Warehouse locks."""
    if not warehouses:
        return ()
    result: list[ActiveCountScope] = []
    for warehouse in sorted(warehouses):
        rows = frappe.db.get_values(
            _SCOPE,
            filters={"warehouse": warehouse, "parenttype": _PARENT, "parentfield": "scope"},
            fieldname=[
                "name",
                "parent",
                "item_code",
                "freeze_active",
                "lease_state",
                "snapshot_revision",
            ],
            as_dict=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        for row in rows:
            if not row.freeze_active:
                continue
            if row.lease_state != "Active" or int(row.snapshot_revision or 0) < 1:
                frappe.throw(_("An active Count lease has inconsistent evidence."))
            result.append(
                ActiveCountScope(
                    session=str(row.parent),
                    row=str(row.name),
                    warehouse=warehouse,
                    item_code=str(row.item_code or ""),
                    revision=int(row.snapshot_revision),
                )
            )
    return tuple(result)


def count_revision_accepts_observations(doc: Document) -> bool:
    """Permit recapture evidence while denying a second emergency in that revision."""
    state = str(doc.get("workflow_state") or "")
    if state not in {"Frozen", "Returned", "Recapture Required"}:
        return False
    if not doc.get("evidence_invalidated"):
        return True
    if state != "Recapture Required":
        return False
    return not _has_current_revision_emergency(doc)


def _has_current_revision_emergency(doc: Document) -> bool:
    """An emergency after recapture is stamped with the new revision."""
    events = frappe.db.get_values(
        "Stock Count Evidence Event",
        {
            "session": doc.name,
            "from_revision": doc.get("evidence_revision"),
            "event_type": ("in", ["Emergency Invalidated", "Emergency Cancel Invalidated"]),
        },
        "name",
        pluck=True,
        for_update=True,
        wait=False,
        limit=1,
    )
    return bool(events)


def _effect_scope(doc: Document) -> tuple[set[tuple[str, str]], set[str]]:
    # Import at use time because the shared freeze adapter imports this module.
    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import _rows_to_check

    if doc.doctype in {"Sales Invoice", "Purchase Invoice"} and not doc.get("update_stock"):
        return set(), set()
    return _rows_to_check(doc)


def _count_effect_item_links(doc: Document) -> dict[str, tuple[str, str, str]]:
    """Bind the private posting proof to the exact correction child links."""
    return {
        str(row.name): (
            str(row.get("stock_count_session_source_item") or ""),
            str(row.get("stock_count_session_target_item") or ""),
            str(row.get("stock_count_effect_key") or ""),
        )
        for row in doc.get("items") or []
    }


def enforce_count_freeze(doc: Document, method: str | None = None) -> None:
    """Deny ordinary physical effects over a current Count lease."""
    pairs, warehouses = _effect_scope(doc)
    if not warehouses:
        return
    lock_warehouses(warehouses)
    leases = get_active_count_scopes(warehouses)
    if not leases:
        return
    if _approved_count_effect(doc, method, leases):
        return
    if any(lease.intersects(item, warehouse) for item, warehouse in pairs for lease in leases):
        frappe.throw(_("Stock is frozen by an active Stock Count Session."))


def _approved_count_effect(doc: Document, method: str | None, leases: tuple[ActiveCountScope, ...]) -> bool:
    proof = getattr(frappe.local, "_stock_count_effect_proof", None)
    if not isinstance(proof, dict) or proof.get("document") is not doc:
        return False
    if method not in {"before_submit", "before_cancel"}:
        return False
    if proof.get("phase") != method or proof.get("consumed") or not proof.get("guarded"):
        return False
    if proof.get("items") != _count_effect_item_links(doc):
        return False
    pairs, _warehouses = _effect_scope(doc)
    intersecting = tuple(
        lease for lease in leases if any(lease.intersects(item, warehouse) for item, warehouse in pairs)
    )
    return bool(
        proof.get("session")
        and proof.get("revision")
        and intersecting
        and all(
            lease.session == proof["session"] and lease.revision == proof["revision"]
            for lease in intersecting
        )
    )


def begin_count_emergency_effect(doc: Document, phase: str) -> None:
    """Bind the already authorized native emergency action to current Count leases."""
    from connect_diagnostics_core.api.erpnext.stock_entry_workflow import (
        get_approval_digest,
        has_freeze_exception,
        is_direct_transfer,
    )

    if phase not in {"before_submit", "before_cancel"}:
        frappe.throw(_("Unsupported emergency stock-effect phase."))
    if not is_direct_transfer(doc) or not has_freeze_exception(doc):
        frappe.throw(_("Count emergency proof requires a direct approved Material Transfer."))
    source_state = (
        "Emergency Stock Movement Approved"
        if phase == "before_submit"
        else "Emergency Stock Movement Submitted"
    )
    target_state = (
        "Emergency Stock Movement Submitted"
        if phase == "before_submit"
        else "Emergency Stock Movement Cancelled"
    )
    if doc.get("workflow_state") != target_state:
        frappe.throw(_("Emergency movement must use its exact native Workflow action."))
    pairs, warehouses = _effect_scope(doc)
    lock_warehouses(warehouses)
    persisted = frappe.db.get_value(
        "Stock Entry",
        doc.name,
        [
            "workflow_state",
            "docstatus",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "approval_critical_digest",
        ],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if (
        not persisted
        or persisted.workflow_state != source_state
        or persisted.docstatus != (0 if phase == "before_submit" else 1)
        or persisted.approval_critical_digest != get_approval_digest(doc)
        or len(
            {
                str(persisted.approval_maker_user or ""),
                str(persisted.approval_reviewer_user or ""),
                str(persisted.approval_authorized_user or ""),
            }
        )
        != 3
        or not all(
            (
                persisted.approval_maker_user,
                persisted.approval_reviewer_user,
                persisted.approval_authorized_user,
            )
        )
        or "Stock Manager" not in frappe.get_roles(str(frappe.session.user))
    ):
        frappe.throw(_("Emergency movement signed approval or source state is stale."))
    leases = get_active_count_scopes(warehouses)
    impacted = {
        (lease.session, lease.revision, lease.row)
        for lease in leases
        if any(lease.intersects(item, warehouse) for item, warehouse in pairs)
    }
    if not impacted:
        return
    if getattr(frappe.local, "_stock_count_emergency_proof", None):
        frappe.throw(_("An emergency Count stock-effect proof is already active."))
    frappe.local._stock_count_emergency_proof = {
        "document": doc,
        "phase": phase,
        "post_phase": "on_submit" if phase == "before_submit" else "on_cancel",
        "action": "Submit Emergency Stock Movement"
        if phase == "before_submit"
        else "Cancel Emergency Stock Movement",
        "leases": {(lease.session, lease.revision, lease.row) for lease in leases},
        "consumed": False,
    }


def _has_count_identity(doc: Document) -> bool:
    return bool(
        doc.get("stock_count_session")
        or doc.get("stock_count_evidence_revision")
        or any(
            row.get("stock_count_session_source_item")
            or row.get("stock_count_session_target_item")
            or row.get("stock_count_effect_key")
            for row in doc.get("items") or []
        )
    )


def is_count_stock_entry(doc: Document) -> bool:
    """Detect current or persisted Count identity, including marker stripping."""
    if _has_count_identity(doc):
        return True
    if doc.is_new() or not doc.name:
        return False
    previous = doc.get_doc_before_save()
    if previous is not None:
        return _has_count_identity(previous)
    if frappe.get_meta("Stock Entry").has_field("stock_count_session") and frappe.db.get_value(
        "Stock Entry", doc.name, "stock_count_session", for_update=True, wait=False
    ):
        return True
    detail_meta = frappe.get_meta("Stock Entry Detail")
    present_fields = [
        field
        for field in (
            "stock_count_session_source_item",
            "stock_count_session_target_item",
            "stock_count_effect_key",
        )
        if detail_meta.has_field(field)
    ]
    if not present_fields:
        return False
    persisted_rows = frappe.db.get_values(
        "Stock Entry Detail",
        {"parent": doc.name, "parenttype": "Stock Entry"},
        present_fields,
        as_dict=True,
        for_update=True,
        wait=False,
    )
    return any(any(row.get(field) for field in present_fields) for row in persisted_rows)


def _require_candidate_shape(parent: Document, entry: Document) -> None:
    from decimal import Decimal

    rows = list(entry.get("items") or [])
    if (
        not entry.name
        or not rows
        or entry.get("stock_count_session") != parent.name
        or int(entry.get("stock_count_evidence_revision") or 0) != int(parent.get("evidence_revision") or 0)
        or entry.get("company") != parent.get("company")
    ):
        frappe.throw(_("Count correction has an incomplete parent or revision link."))
    warehouse = str(rows[0].get("s_warehouse") or rows[0].get("t_warehouse") or "")
    group = (str(entry.get("purpose") or ""), warehouse)
    expected = _correction_rows(parent, {group: str(entry.name)}).get(group)
    if expected is None or not expected or len(expected) != len(rows):
        frappe.throw(_("Count correction has an unexpected native effect group."))
    fields = (
        "item_code",
        "uom",
        "stock_uom",
        "s_warehouse",
        "t_warehouse",
        "storage_location",
        "to_storage_location",
        "batch_no",
        "serial_no",
        "stock_count_session_source_item",
        "stock_count_session_target_item",
        "stock_count_effect_key",
    )
    actual_rows = sorted(
        (
            tuple(str(row.get(field) or "") for field in fields),
            Decimal(str(row.get("qty") or 0)),
            Decimal(str(row.get("conversion_factor") or 0)),
        )
        for row in rows
    )
    expected_rows = sorted(
        (
            tuple(str(row.get(field) or "") for field in fields),
            Decimal(str(row.get("qty") or 0)),
            Decimal(str(row.get("conversion_factor") or 0)),
        )
        for row in (expected or [])
    )
    if actual_rows != expected_rows:
        frappe.throw(_("Count correction native details differ from the signed Count effect."))


def guard_count_stock_entry(doc: Document, method: str) -> None:
    """Independently verify each exact Count candidate/effect lifecycle phase."""
    if not is_count_stock_entry(doc):
        return
    if method == "on_trash":
        frappe.throw(_("Count correction history cannot be deleted."))
    session = str(doc.get("stock_count_session") or "")
    if not session or method == "before_update_after_submit":
        frappe.throw(_("Count correction identity and submitted state are protected."))
    candidate_proof = getattr(frappe.local, "_stock_count_candidate_proof", None)
    effect_proof = getattr(frappe.local, "_stock_count_effect_proof", None)
    if candidate_proof and effect_proof:
        frappe.throw(_("Count candidate and posting proofs cannot overlap."))
    if method == "validate" and isinstance(candidate_proof, dict):
        if (
            candidate_proof.get("document") is not doc
            or candidate_proof.get("session") != session
            or candidate_proof.get("actor") != frappe.session.user
            or candidate_proof.get("consumed")
            or candidate_proof.get("operation") not in {"prepare", "refresh", "bundle", "retire"}
        ):
            frappe.throw(_("Count correction Draft change lacks its exact private proof."))
        operation = str(candidate_proof["operation"])
    elif method in {"validate", "before_submit", "before_cancel"} and isinstance(effect_proof, dict):
        if (
            effect_proof.get("document") is not doc
            or effect_proof.get("session") != session
            or effect_proof.get("actor") != frappe.session.user
            or effect_proof.get("consumed")
            or effect_proof.get("phase") not in {"before_submit", "before_cancel"}
        ):
            frappe.throw(_("Count correction effect lacks its exact private proof."))
        operation = "submit" if effect_proof["phase"] == "before_submit" else "cancel"
    else:
        frappe.throw(_("Count corrections must use an approved Count Session native action."))
    _pairs, warehouses = _effect_scope(doc)
    lock_warehouses(warehouses)
    parent = cast(Document, frappe.get_doc(_PARENT, session, for_update=True))
    if int(parent.get("evidence_revision") or 0) != int(doc.get("stock_count_evidence_revision") or 0):
        frappe.throw(_("Count candidate revision is stale."))
    if isinstance(candidate_proof, dict) and (
        candidate_proof.get("revision") != int(parent.get("evidence_revision") or 0)
        or candidate_proof.get("snapshot_digest") != parent.get("snapshot_digest")
        or (
            candidate_proof.get("operation") != "prepare"
            and candidate_proof.get("candidate_digest") != parent.get("accounting_candidate_digest")
        )
    ):
        frappe.throw(_("Count candidate write proof is stale."))
    _require_candidate_shape(parent, doc)
    if operation == "prepare":
        if parent.get("workflow_state") != "Pending Review" or parent.docstatus != 0:
            frappe.throw(_("Count candidate preparation requires current independent review."))
    elif operation in {"refresh", "bundle", "submit"}:
        if (
            parent.get("workflow_state") != "Approved"
            or parent.docstatus != 0
            or not parent.get("stock_approver_user")
            or (parent.get("accounting_review_required") and not parent.get("accounts_approver_user"))
            or parent.get("evidence_invalidated")
        ):
            frappe.throw(_("Count correction approval is not current."))
    elif operation == "cancel":
        if parent.docstatus != 1 or parent.get("workflow_state") not in {
            "Closed",
            "Cancellation Approved",
        }:
            frappe.throw(_("Count correction cancellation lacks its submitted parent."))
    elif operation == "retire":
        assert isinstance(candidate_proof, dict)
        if (
            parent.docstatus != 0
            or parent.get("workflow_state") != candidate_proof.get("source_state")
            or candidate_proof.get("source_action") != parent.get("pending_reason_action")
            or candidate_proof.get("actor") != parent.get("pending_reason_actor")
            or doc.get("workflow_state") != "Stock Count Correction Retired"
        ):
            frappe.throw(_("Count correction retirement is detached from its parent decision."))
        candidate_payload = _candidate_projection(parent, [doc])["entries"][0]
        current_digest = sha256(
            json.dumps(candidate_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if current_digest != candidate_proof.get("entry_digest"):
            frappe.throw(_("Count correction changed during protected retirement."))
    if operation in {"submit", "cancel"}:
        persisted_entry = cast(Document, frappe.get_doc("Stock Entry", doc.name, for_update=True))
        expected_status = 0 if operation == "submit" else 1
        if persisted_entry.docstatus != expected_status:
            frappe.throw(_("Count correction native document status changed."))
        current_input = _candidate_projection(parent, [doc])["entries"][0]
        persisted_input = _candidate_projection(parent, [persisted_entry])["entries"][0]
        if current_input != persisted_input:
            frappe.throw(_("Count correction native accounting inputs changed during action."))
    if method == "validate" and isinstance(candidate_proof, dict):
        candidate_proof["consumed"] = True
        return
    if method == "validate":
        return
    if method == "before_submit" and operation != "submit":
        frappe.throw(_("Count correction Submit proof phase changed."))
    if method == "before_cancel" and operation != "cancel":
        frappe.throw(_("Count correction Cancel proof phase changed."))
    assert isinstance(effect_proof, dict)
    if (
        effect_proof.get("revision") != int(parent.get("evidence_revision") or 0)
        or effect_proof.get("digest") != parent.get("approved_digest")
        or effect_proof.get("candidate_digest") != parent.get("accounting_candidate_digest")
        or effect_proof.get("items") != _count_effect_item_links(doc)
    ):
        frappe.throw(_("Count correction approval seal changed before native effect."))
    effect_proof["guarded"] = True


def validate_append_only_evidence(doc: Document, method: str) -> None:
    """Evidence can be inserted only by the active object-bound Count service."""
    if doc.doctype not in _EVIDENCE:
        frappe.throw(_("Unsupported Count evidence document."))
    if method != "before_insert":
        frappe.throw(_("Count evidence is immutable."))
    if doc.docstatus != 0:
        frappe.throw(_("Count evidence must be inserted as a Draft audit record."))
    proof = getattr(frappe.local, "_stock_count_evidence_proof", None)
    if not isinstance(proof, dict) or proof.get("document") is not doc or proof.get("consumed"):
        frappe.throw(_("Count evidence must be recorded through the Count Session service."))
    assert isinstance(proof, dict)
    if proof.get("session") != doc.get("session") or proof.get("doctype") != doc.doctype:
        frappe.throw(_("Count evidence is bound to a different Session."))
    proof["consumed"] = True


def invalidate_count_after_emergency(doc: Document, method: str) -> None:
    """Require exact approved emergency proof before Count parent invalidation."""
    if method not in {"on_submit", "on_cancel"}:
        frappe.throw(_("Emergency Count invalidation requires a native stock effect."))
    pairs, warehouses = _effect_scope(doc)
    lock_warehouses(warehouses)
    current_leases = get_active_count_scopes(warehouses)
    impacted = {
        (lease.session, lease.revision)
        for lease in current_leases
        if any(lease.intersects(item, warehouse) for item, warehouse in pairs)
    }
    if not impacted:
        return
    proof = getattr(frappe.local, "_stock_count_emergency_proof", None)
    if not isinstance(proof, dict) or proof.get("document") is not doc or proof.get("consumed"):
        frappe.throw(_("Emergency Count invalidation requires an approved native stock effect."))
    assert isinstance(proof, dict)
    if proof.get("post_phase") != method:
        frappe.throw(_("Emergency Count invalidation phase is stale."))
    expected = cast(set[tuple[str, int, str]], proof.get("leases") or set())
    actual = {(lease.session, lease.revision, lease.row) for lease in current_leases}
    if actual != expected:
        frappe.throw(_("Emergency Count scope changed before its stock effect completed."))
    native_legs = frappe.db.get_values(
        "Stock Ledger Entry",
        {"voucher_type": "Stock Entry", "voucher_no": doc.name},
        ["name", "item_code", "warehouse", "actual_qty"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    if not native_legs or not any(row.actual_qty for row in native_legs):
        frappe.throw(_("Emergency Stock Entry has no native ledger effect to record."))
    event_type = "Emergency Invalidated" if method == "on_submit" else "Emergency Cancel Invalidated"
    timestamp = frappe.utils.now()
    for session_name, revision in sorted(impacted):
        current = frappe.db.get_value(
            _PARENT,
            session_name,
            ["name", "docstatus", "evidence_revision", "snapshot_digest", "evidence_invalidated"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not current or current.docstatus != 0 or int(current.evidence_revision) != revision:
            frappe.throw(_("Emergency Count Session changed before invalidation."))
        event = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Stock Count Evidence Event",
                    "session": session_name,
                    "event_type": event_type,
                    "source_action": str(proof.get("action") or ""),
                    "from_revision": revision,
                    "source_stock_entry": doc.name,
                    "reason": str(doc.get("freeze_exception_reason") or ""),
                    "actor_user": str(frappe.session.user),
                    "event_at": timestamp,
                    "prior_snapshot_digest": current.snapshot_digest,
                }
            ),
        )
        _insert_count_evidence(event)
        session = cast(Document, frappe.get_doc(_PARENT, session_name, for_update=True))
        if session.docstatus != 0 or int(session.get("evidence_revision") or 0) != revision:
            frappe.throw(_("Emergency Count Session changed before protected invalidation."))
        session.set("evidence_invalidated", 1)
        session.set("invalidation_reason", str(doc.get("freeze_exception_reason") or ""))
        session.set("invalidation_stock_entry", doc.name)
        session.set("source_emergency_stock_entry", doc.name)
        session.set("invalidation_at", timestamp)
        with parent_write_grant(
            session,
            {
                "evidence_invalidated",
                "invalidation_reason",
                "invalidation_stock_entry",
                "source_emergency_stock_entry",
                "invalidation_at",
            },
        ):
            session.save(ignore_permissions=True)
    proof["consumed"] = True
    frappe.local._stock_count_emergency_proof = None


def _insert_count_evidence(doc: Document) -> None:
    """Insert an exact immutable event using a private object-bound grant."""
    previous = getattr(frappe.local, "_stock_count_evidence_proof", None)
    frappe.local._stock_count_evidence_proof = {
        "document": doc,
        "session": str(doc.get("session") or ""),
        "doctype": doc.doctype,
        "consumed": False,
    }
    try:
        doc.insert(ignore_permissions=True)
        if not frappe.local._stock_count_evidence_proof["consumed"]:
            frappe.throw(_("Count evidence insertion was not authorized."))
    finally:
        frappe.local._stock_count_evidence_proof = previous


@contextmanager
def parent_write_grant(doc: Document, fields: set[str]) -> Iterator[None]:
    """Grant one exact parent object one protected save in this request."""
    previous = getattr(frappe.local, "_stock_count_parent_grant", None)
    grant: dict[str, Any] = {"document": doc, "fields": frozenset(fields), "consumed": False}
    frappe.local._stock_count_parent_grant = grant
    try:
        yield
        if not grant["consumed"]:
            frappe.throw(_("Count Session protected save did not consume its grant."))
    finally:
        frappe.local._stock_count_parent_grant = previous


@contextmanager
def account_submit_grant(doc: Document, action: str, state: str) -> Iterator[None]:
    """Bound Frappe submitted-update ACL for one Accounts Manager Count save."""
    if getattr(frappe.local, "_stock_count_account_submit_grant", None):
        frappe.throw(_("Another Count accounting permission grant is active."))
    grant: dict[str, Any] = {
        "document": doc,
        "actor": str(frappe.session.user or ""),
        "action": action,
        "state": state,
        "seen": False,
    }
    frappe.local._stock_count_account_submit_grant = grant
    try:
        yield
        if not grant["seen"]:
            frappe.throw(_("Count accounting permission was not used by its bound save."))
    finally:
        frappe.local._stock_count_account_submit_grant = None


def authorize_account_submit_transition(doc: Document, action: str) -> None:
    """The native Workflow task grants exactly its following submitted save."""
    if getattr(frappe.local, "_stock_count_account_submit_grant", None):
        frappe.throw(_("Another Count accounting permission grant is active."))
    frappe.local._stock_count_account_submit_grant = {
        "document": doc,
        "actor": str(frappe.session.user or ""),
        "action": action,
        "state": str(doc.get("workflow_state") or ""),
        "seen": False,
    }


def _scope_pairs(doc: Document) -> tuple[tuple[str, str], ...]:
    kind = str(doc.get("scope_type") or "")
    if kind not in {"Full", "Cycle"}:
        frappe.throw(_("Choose Full or Cycle Count scope."))
    rows: list[tuple[str, str]] = []
    for row in doc.get("scope") or []:
        warehouse = str(row.get("warehouse") or "")
        item = str(row.get("item_code") or "")
        if (
            not warehouse
            or row.get("scope_kind") != ("Warehouse" if kind == "Full" else "Item/Warehouse")
            or bool(item) != (kind == "Cycle")
        ):
            frappe.throw(_("Count scope has an inconsistent Warehouse and Item."))
        rows.append((warehouse, item))
    if not rows or len(rows) != len(set(rows)):
        frappe.throw(_("Count scope requires distinct Warehouse and Item rows."))
    return tuple(sorted(rows))


def _lock_session(doc: Document, source_states: set[str]) -> None:
    warehouses = {warehouse for warehouse, _item in _scope_pairs(doc)}
    lock_warehouses(warehouses)
    persisted = frappe.db.get_value(
        _PARENT,
        doc.name,
        ["workflow_state", "docstatus", "evidence_revision"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if (
        not persisted
        or persisted.workflow_state not in source_states
        or persisted.docstatus != doc.docstatus
        or int(persisted.evidence_revision or 0) != int(doc.get("evidence_revision") or 0)
    ):
        frappe.throw(_("Count state or revision changed; reload and retry."))


def _actor(doc: Document, role: str) -> tuple[str, str]:
    user = str(frappe.session.user or "")
    if role not in frappe.get_roles(user):
        raise frappe.PermissionError(_("This Count action requires {0}.").format(role))
    if not frappe.has_permission(doc.doctype, ptype="write", doc=doc, user=user):
        raise frappe.PermissionError(_("You cannot edit this Count Session."))
    employees = frappe.db.get_values(
        "Employee", {"user_id": user, "status": "Active"}, "name", pluck=True, limit=2
    )
    if len(employees) > 1:
        frappe.throw(_("The Count actor has multiple active Employee records."))
    return user, str(employees[0]) if employees else ""


def _line_key(item: str, warehouse: str, location: str, batch: str, serial: str) -> str:
    payload = json.dumps((item, warehouse, location, batch, serial), separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


def _evidence_digest(doc: Document) -> str:
    revision = int(doc.get("evidence_revision") or 0)
    payload = {
        "company": doc.get("company"),
        "description": doc.get("description"),
        "reason": doc.get("reason"),
        "scope": _scope_pairs(doc),
        "revision": revision,
        "cutoff": str(doc.get("cutoff_datetime") or ""),
        "locations": sorted(
            (
                str(row.get("warehouse") or ""),
                str(row.get("storage_location") or ""),
                str(row.get("coverage_state") or ""),
                str(row.get("counter_user") or ""),
            )
            for row in doc.get("locations") or []
            if int(row.get("evidence_revision") or 0) == revision
        ),
        "items": sorted(
            (
                str(row.get("line_key") or ""),
                str(row.get("system_qty") or 0),
                str(row.get("counted_qty") or 0),
                str(row.get("latest_observation") or ""),
                str(row.get("line_state") or ""),
            )
            for row in doc.get("items") or []
            if int(row.get("evidence_revision") or 0) == revision
        ),
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _authorize_transition_save(doc: Document, fields: set[str]) -> None:
    """The native apply_workflow task grants only its next save of this object."""
    if getattr(frappe.local, "_stock_count_parent_grant", None):
        frappe.throw(_("Another Count parent-write grant is still active."))
    frappe.local._stock_count_parent_grant = {
        "document": doc,
        "fields": frozenset(fields),
        "consumed": False,
    }


def _capture_revision(doc: Document, *, first: bool) -> None:
    revision = int(doc.get("evidence_revision") or 0) + 1
    cutoff = now()
    scope = _scope_pairs(doc)
    for warehouse, selected_item in scope:
        require_operational_warehouse(warehouse)
        warehouse_row = frappe.db.get_value(
            "Warehouse",
            warehouse,
            ["company", "is_group"],
            as_dict=True,
            for_update=True,
            wait=False,
        )
        if not warehouse_row or warehouse_row.company != doc.get("company") or warehouse_row.is_group:
            frappe.throw(_("Count Warehouse must be an operational leaf in the selected Company."))
        matching_scope = [
            row
            for row in doc.get("scope") or []
            if row.get("warehouse") == warehouse and str(row.get("item_code") or "") == selected_item
        ]
        if len(matching_scope) != 1:
            frappe.throw(_("Count scope row changed during capture."))
        scope_row = matching_scope[0]
        location_rows = frappe.db.get_values(
            "Storage Location",
            {"warehouse": warehouse},
            "name",
            pluck=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        if not location_rows:
            frappe.throw(_("Count Warehouse requires a Storage Location."))
        location_names = {str(name) for name in location_rows}
        ledger_rows = frappe.db.sql(
            """select distinct item_code, storage_location from `tabStock Ledger Entry`
            where company = %s and warehouse = %s and docstatus = 1 and is_cancelled = 0
              and (%s = '' or item_code = %s) for update nowait""",
            (doc.get("company"), warehouse, selected_item, selected_item),
            as_dict=True,
        )
        if any(not row.storage_location or row.storage_location not in location_names for row in ledger_rows):
            frappe.throw(_("Count scope has an unlocated or invalid native stock ledger entry."))
        for location in sorted(location_names):
            require_location_warehouse(location, warehouse)
            doc.append(
                "locations",
                {
                    "scope_row": scope_row.name,
                    "company": doc.get("company"),
                    "warehouse": warehouse,
                    "storage_location": location,
                    "evidence_revision": revision,
                    "coverage_state": "Not Started",
                },
            )
        pairs = sorted({(str(row.item_code), str(row.storage_location)) for row in ledger_rows})
        for item_code, location in pairs:
            item = frappe.db.get_value(
                "Item",
                item_code,
                ["stock_uom", "has_batch_no", "has_serial_no", "is_stock_item"],
                as_dict=True,
                for_update=True,
                wait=False,
            )
            if not item or not item.is_stock_item:
                frappe.throw(_("Count ledger Item must be an existing stock Item."))
            snapshot = snapshot_location(
                company=str(doc.get("company")),
                item_code=item_code,
                warehouse=warehouse,
                storage_location=location,
                cutoff=cutoff,
                locking_read=True,
            )
            if item.has_batch_no or item.has_serial_no:
                balances = ((serial, batch, qty) for serial, batch, qty in snapshot.identities if qty)
            else:
                balances = (("", "", snapshot.quantity),) if snapshot.quantity else ()
            for serial, batch, quantity in balances:
                key = _line_key(item_code, warehouse, location, batch, serial)
                doc.append(
                    "items",
                    {
                        "line_key": key,
                        "item_code": item_code,
                        "company": doc.get("company"),
                        "warehouse": warehouse,
                        "storage_location": location,
                        "stock_uom": item.stock_uom,
                        "batch_no": batch,
                        "serial_no": serial,
                        "evidence_revision": revision,
                        "system_qty": float(quantity),
                        "snapshot_at": cutoff,
                        "snapshot_digest": sha256(f"{key}:{quantity}:{cutoff}".encode()).hexdigest(),
                        "baseline_source": "Native Stock Ledger Entry",
                        "line_state": "Pending",
                    },
                )
    doc.set("evidence_revision", revision)
    doc.set("cutoff_datetime", cutoff)
    doc.set("snapshot_digest", _evidence_digest(doc))
    if first:
        doc.set("frozen_at", cutoff)
    for row in doc.get("scope") or []:
        row.snapshot_revision = revision
        row.cutoff_datetime = cutoff
        row.freeze_active = 1
        row.lease_state = "Active"
        row.activated_at = cutoff


def freeze_count(doc: Document) -> None:
    """Draft → Frozen native transition task; publish lease with its baseline."""
    _lock_session(doc, {"Draft"})
    user, employee = _actor(doc, "Stock User")
    if doc.get("workflow_state") != "Frozen" or doc.get("evidence_revision"):
        frappe.throw(_("Only a new Draft Count Session can be frozen."))
    from connect_diagnostics_core.api.erpnext.repost_item_valuation_reservation import check_count_activation
    from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import (
        _check_item_level,
        _check_warehouse_level,
    )

    scope = _scope_pairs(doc)
    warehouses = {warehouse for warehouse, _item in scope}
    check_count_activation(warehouses)
    reconciliation_conflicts = (
        _check_warehouse_level(warehouses)
        if doc.get("scope_type") == "Full"
        else _check_item_level({(item, warehouse) for warehouse, item in scope})
    )
    if reconciliation_conflicts:
        frappe.throw("<br>".join(reconciliation_conflicts), title=_("Stock Reconciliation in progress"))
    if any(
        lease.intersects(item, warehouse)
        for lease in get_active_count_scopes(warehouses)
        for warehouse, item in scope
    ):
        frappe.throw(_("Another Count Session already freezes this scope."))
    _capture_revision(doc, first=True)
    doc.set("maker_user", user)
    doc.set("maker_employee", employee)
    doc.set("maker_at", now())
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "scope",
            "locations",
            "items",
            "evidence_revision",
            "cutoff_datetime",
            "snapshot_digest",
            "frozen_at",
            "maker_user",
            "maker_employee",
            "maker_at",
        },
    )


def _current_lines(doc: Document) -> list[Document]:
    revision = int(doc.get("evidence_revision") or 0)
    return [
        cast(Document, row)
        for row in doc.get("items") or []
        if int(row.get("evidence_revision") or 0) == revision
    ]


def _current_locations(doc: Document) -> list[Document]:
    revision = int(doc.get("evidence_revision") or 0)
    return [
        cast(Document, row)
        for row in doc.get("locations") or []
        if int(row.get("evidence_revision") or 0) == revision
    ]


def _verify_complete(doc: Document) -> bool:
    """Verify immutable observations, checklist, derived variances and recounts."""
    locations = _current_locations(doc)
    if not locations or any(
        row.get("coverage_state") != "Counted" or not row.get("counter_user") for row in locations
    ):
        frappe.throw(_("Every current Count location must be confirmed."))
    lines = _current_lines(doc)
    if not lines:
        return False
    keys = [str(row.get("line_key") or "") for row in lines]
    if len(keys) != len(set(keys)):
        frappe.throw(_("Current Count lines contain duplicate identities."))
    observations = frappe.db.get_values(
        "Stock Count Observation",
        {"session": doc.name, "evidence_revision": doc.get("evidence_revision")},
        ["name", "line_key", "pass_type", "counted_qty", "observer_user", "observed_at"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    by_key: dict[str, list[Any]] = {}
    for event in observations:
        by_key.setdefault(str(event.line_key), []).append(event)
    has_variance = False
    for line in lines:
        events = by_key.get(str(line.get("line_key")), [])
        initial = [event for event in events if event.pass_type == "Initial"]
        recount = [event for event in events if event.pass_type == "Recount"]
        if len(initial) != 1:
            frappe.throw(_("Every current Count line needs exactly one Initial observation."))
        from decimal import Decimal

        baseline = Decimal(str(line.get("system_qty") or 0))
        first = Decimal(str(initial[0].counted_qty))
        if first != baseline:
            latest = next((event for event in recount if event.name == line.get("latest_observation")), None)
            if latest is None or latest.observer_user == initial[0].observer_user:
                frappe.throw(_("A variance needs an independent Recount observation."))
            assert latest is not None
            final = Decimal(str(latest.counted_qty))
        else:
            if recount:
                frappe.throw(_("A no-variance Count line cannot contain an unnecessary Recount."))
            final = first
            if line.get("latest_observation") != initial[0].name:
                frappe.throw(_("Count line projection does not match its Initial observation."))
        if Decimal(str(line.get("counted_qty") or 0)) != final:
            frappe.throw(_("Count line quantity differs from signed observation."))
        if Decimal(str(line.get("variance_qty") or 0)) != final - baseline:
            frappe.throw(_("Count line variance differs from its native baseline."))
        if final != baseline:
            has_variance = True
    return has_variance


def _native_number(value: Any, doctype: str, fieldname: str) -> str:
    from decimal import Decimal, InvalidOperation

    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        frappe.throw(_("Native Count accounting input has an invalid number."))
    if not number.is_finite():
        frappe.throw(_("Native Count accounting input must be finite."))
    precision = int(frappe.get_precision(doctype, fieldname) or 0)
    return str(number.quantize(Decimal(1).scaleb(-precision)))


def _lock_source_rows(doctype: str, filters: dict[str, Any], fields: list[str]) -> list[Any]:
    """Read mutable valuation/account sources in a stable lock order."""
    return frappe.db.get_values(
        doctype,
        filters,
        fields,
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )


def _refresh_native_source_caches(
    company: str,
    item_codes: set[str],
    warehouse_names: set[str],
    item_groups: set[str],
    brands: set[str],
    account_names: set[str],
) -> None:
    """Evict only named source docs and this Count's native resolver keys."""
    from erpnext.stock import get_warehouse_account_map
    from erpnext.stock.utils import get_valuation_method

    # Native getters use cached Documents; clearing a named DocType also evicts
    # that DocType's local frappe.db.value_cache entries in this Frappe version.
    for doctype, names in (
        ("Company", {company}),
        ("Item", item_codes),
        ("Warehouse", warehouse_names),
        ("Item Group", item_groups),
        ("Brand", brands),
        ("Account", account_names),
        ("Stock Settings", {"Stock Settings"}),
    ):
        for name in sorted(names):
            frappe.clear_document_cache(doctype, name)
    maps = getattr(frappe.flags, "warehouse_account_map", None)
    if isinstance(maps, dict):
        maps.pop(company, None)
    request_cache = getattr(frappe.local, "request_cache", None)
    wrapped = getattr(get_valuation_method, "__wrapped__", None)
    if isinstance(request_cache, dict) and wrapped is not None:
        values = request_cache.get(wrapped)
        if isinstance(values, dict):
            for item_code in item_codes:
                values.pop((item_code, company), None)
    # Keep reference to the native resolver for tests and make its cache
    # identity explicit; StockEntry calls this resolver after this point.
    _ = get_warehouse_account_map


def _candidate_projection(doc: Document, entries: list[Document]) -> dict[str, Any]:
    """Finite, current-read native valuation and account inputs approved for Close."""
    from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
    from erpnext.stock.utils import get_valuation_method

    company_fields = [
        "default_currency",
        "enable_perpetual_inventory",
        "enable_provisional_accounting_for_non_stock_items",
        "enable_item_wise_inventory_account",
        "default_expense_account",
        "stock_adjustment_account",
        "default_inventory_account",
        "valuation_method",
    ]
    company = frappe.db.get_value(
        "Company", doc.get("company"), company_fields, as_dict=True, for_update=True, wait=False
    )
    if not company:
        frappe.throw(_("Count Company accounting policy is unavailable."))
    dimensions = frappe.db.get_values(
        "Accounting Dimension",
        {"disabled": 0},
        ["name", "fieldname", "document_type"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    dimension_names = sorted({str(row.fieldname) for row in dimensions if row.fieldname})
    item_codes = sorted({str(row.get("item_code")) for entry in entries for row in entry.get("items") or []})
    items = (
        _lock_source_rows(
            "Item",
            {"name": ("in", item_codes)},
            [
                "name",
                "is_stock_item",
                "is_fixed_asset",
                "valuation_method",
                "valuation_rate",
                "standard_rate",
                "has_serial_no",
                "has_batch_no",
                "item_group",
                "brand",
            ],
        )
        if item_codes
        else []
    )
    if len(items) != len(item_codes) or any(not item.is_stock_item or item.is_fixed_asset for item in items):
        frappe.throw(_("Count correction requires current stock Items that are not fixed assets."))
    warehouse_names = {
        str(value) for line in _current_lines(doc) for value in (line.get("warehouse"),) if value
    }
    # Include all ancestors: ERPNext resolves a missing Warehouse.account by
    # walking the nested set from the leaf toward its parents.
    warehouse_rows: list[Any] = []
    pending = set(warehouse_names)
    while pending:
        found = _lock_source_rows(
            "Warehouse",
            {"name": ("in", sorted(pending))},
            ["name", "parent_warehouse", "account", "company", "lft", "rgt", "is_group"],
        )
        warehouse_rows.extend(found)
        seen = {str(row.name) for row in warehouse_rows}
        pending = {
            str(row.parent_warehouse)
            for row in found
            if row.parent_warehouse and str(row.parent_warehouse) not in seen
        }
    warehouse_names.update(str(row.name) for row in warehouse_rows)
    item_groups = sorted({str(row.item_group) for row in items if row.item_group})
    brands = sorted({str(row.brand) for row in items if row.brand})
    item_defaults = _lock_source_rows(
        "Item Default",
        {"parent": ("in", item_codes), "parenttype": "Item"},
        ["name", "parent", "company", "default_warehouse", "expense_account", "income_account"],
    )
    group_defaults: list[Any] = []
    pending_groups = set(item_groups)
    while pending_groups:
        found_groups = _lock_source_rows(
            "Item Group",
            {"name": ("in", sorted(pending_groups))},
            ["name", "parent_item_group", "default_expense_account", "default_income_account"],
        )
        group_defaults.extend(found_groups)
        seen_groups = {str(row.name) for row in group_defaults}
        pending_groups = {
            str(row.parent_item_group)
            for row in found_groups
            if row.parent_item_group and str(row.parent_item_group) not in seen_groups
        }
    item_groups = sorted({str(row.name) for row in group_defaults})
    brand_defaults = _lock_source_rows(
        "Brand", {"name": ("in", brands)}, ["name", "default_expense_account", "default_income_account"]
    )
    stock_settings = frappe.db.get_single_value(
        "Stock Settings", "do_not_use_batchwise_valuation", cache=False, for_update=True
    )
    source: list[tuple[Any, ...]] = []
    for item_code, warehouse, location in sorted(
        {
            (str(line.get("item_code")), str(line.get("warehouse")), str(line.get("storage_location")))
            for line in _current_lines(doc)
        }
    ):
        snapshot = snapshot_location(
            company=str(doc.get("company")),
            item_code=item_code,
            warehouse=warehouse,
            storage_location=location,
            cutoff=now(),
            locking_read=True,
        )
        source.append(
            (
                item_code,
                warehouse,
                location,
                str(snapshot.quantity),
                tuple((serial, batch, str(qty)) for serial, batch, qty in snapshot.identities),
            )
        )
    batch_names = {
        str(row.get("batch_no"))
        for entry in entries
        for row in entry.get("items") or []
        if row.get("batch_no")
    }
    batch_rows = (
        _lock_source_rows(
            "Batch",
            {"name": ("in", sorted(batch_names))},
            ["name", "use_batchwise_valuation"],
        )
        if batch_names
        else []
    )
    item_prices = (
        _lock_source_rows(
            "Item Price",
            {"item_code": ("in", item_codes), "buying": 1, "currency": str(company.default_currency or "")},
            ["name", "item_code", "price_list", "currency", "buying", "price_list_rate"],
        )
        if item_codes
        else []
    )
    history: list[Any] = []
    for item_code, warehouse, _location in sorted(
        {
            (str(line.get("item_code")), str(line.get("warehouse")), str(line.get("storage_location")))
            for line in _current_lines(doc)
        }
    ):
        history.extend(
            _lock_source_rows(
                "Stock Ledger Entry",
                {"item_code": item_code, "warehouse": warehouse, "is_cancelled": 0},
                [
                    "name",
                    "item_code",
                    "warehouse",
                    "posting_date",
                    "posting_time",
                    "posting_datetime",
                    "creation",
                    "actual_qty",
                    "valuation_rate",
                    "stock_value_difference",
                    "stock_queue",
                    "batch_no",
                    "serial_and_batch_bundle",
                    "voucher_type",
                    "voucher_no",
                ],
            )
        )
    bundle_names = sorted(
        {str(row.serial_and_batch_bundle) for row in history if row.serial_and_batch_bundle}
    )
    bundle_rows = (
        _lock_source_rows(
            "Serial and Batch Bundle",
            {"name": ("in", bundle_names)},
            ["name", "posting_datetime", "warehouse", "item_code", "voucher_type", "voucher_no"],
        )
        if bundle_names
        else []
    )
    source_account_names = {
        str(row.get(field))
        for row in [*item_defaults, *group_defaults, *brand_defaults]
        for field in (
            "expense_account",
            "income_account",
            "default_expense_account",
            "default_income_account",
        )
        if row.get(field)
    }
    source_account_names.update(str(row.account) for row in warehouse_rows if row.account)
    source_account_names.update(
        str(company.get(field))
        for field in ("default_inventory_account", "default_expense_account", "stock_adjustment_account")
        if company.get(field)
    )
    native_entries: list[dict[str, Any]] = []
    account_names: set[str] = {
        str(company.get(field))
        for field in ("default_expense_account", "stock_adjustment_account", "default_inventory_account")
        if company.get(field)
    }
    account_names.update(source_account_names)
    account_names.update(
        str(row.get("expense_account"))
        for entry in entries
        for row in entry.get("items") or []
        if row.get("expense_account")
    )
    account_rows = (
        _lock_source_rows(
            "Account",
            {"name": ("in", sorted(account_names))},
            ["name", "company", "account_currency", "disabled", "is_group", "account_type", "report_type"],
        )
        if account_names
        else []
    )
    if len(account_rows) != len(account_names):
        frappe.throw(_("Count correction accounting map includes an unavailable Account."))
    _refresh_native_source_caches(
        str(doc.get("company")),
        set(item_codes),
        warehouse_names,
        set(item_groups),
        set(brands),
        account_names,
    )
    for doctype, names in (("Batch", batch_names), ("Item Price", {str(row.name) for row in item_prices})):
        for name in sorted(names):
            frappe.clear_document_cache(doctype, name)
    for entry in sorted(entries, key=lambda candidate: str(candidate.name)):
        if entry.docstatus not in {0, 1, 2} or entry.get("company") != doc.get("company"):
            frappe.throw(_("Count correction candidate has an invalid native state."))
        inventory_map = cast(StockEntry, entry).get_inventory_account_map()
        normalized_map = []
        for key, value in sorted(inventory_map.items()):
            account = str(value.get("account") or "")
            currency = str(value.get("account_currency") or "")
            normalized_map.append((str(key), account, currency))
            if account:
                account_names.add(account)
        rows = []
        for row in sorted(entry.get("items") or [], key=lambda item: (int(item.idx or 0), str(item.name))):
            expense_account = str(row.get("expense_account") or "")
            if expense_account:
                account_names.add(expense_account)
            numeric_fields = (
                "qty",
                "transfer_qty",
                "conversion_factor",
                "basic_rate",
                "basic_amount",
                "valuation_rate",
                "incoming_rate",
            )
            native_numbers = {
                field: _native_number(row.get(field), "Stock Entry Detail", field)
                if frappe.get_meta("Stock Entry Detail").get_field(field)
                else str(row.get(field) or "")
                for field in numeric_fields
            }
            rows.append(
                {
                    "name": str(row.name),
                    "idx": int(row.idx or 0),
                    "item_code": str(row.get("item_code") or ""),
                    "uom": str(row.get("uom") or ""),
                    "stock_uom": str(row.get("stock_uom") or ""),
                    "s_warehouse": str(row.get("s_warehouse") or ""),
                    "t_warehouse": str(row.get("t_warehouse") or ""),
                    "storage_location": str(row.get("storage_location") or ""),
                    "to_storage_location": str(row.get("to_storage_location") or ""),
                    "batch_no": str(row.get("batch_no") or ""),
                    "serial_no": str(row.get("serial_no") or ""),
                    "serial_master_present": bool(
                        row.get("serial_no")
                        and frappe.db.get_value(
                            "Serial No", str(row.get("serial_no")), "name", for_update=True, wait=False
                        )
                    ),
                    "source_item": str(row.get("stock_count_session_source_item") or ""),
                    "target_item": str(row.get("stock_count_session_target_item") or ""),
                    "effect_key": str(row.get("stock_count_effect_key") or ""),
                    "expense_account": expense_account,
                    "cost_center": str(row.get("cost_center") or ""),
                    "project": str(row.get("project") or ""),
                    "allow_zero_valuation_rate": int(row.get("allow_zero_valuation_rate") or 0),
                    "dimensions": {field: str(row.get(field) or "") for field in dimension_names},
                    "numbers": native_numbers,
                }
            )
        native_entries.append(
            {
                "name": str(entry.name),
                "purpose": str(entry.get("purpose") or ""),
                "stock_entry_type": str(entry.get("stock_entry_type") or ""),
                "company": str(entry.get("company") or ""),
                "revision": int(entry.get("stock_count_evidence_revision") or 0),
                "set_posting_time": int(entry.get("set_posting_time") or 0),
                "posting_date": str(entry.get("posting_date") or ""),
                "posting_time": str(entry.get("posting_time") or ""),
                "use_item_inventory_account": int(entry.get("use_item_inventory_account") or 0),
                "project": str(entry.get("project") or ""),
                "inventory_map": normalized_map,
                "rows": rows,
            }
        )
    if any(
        str(value.get("account") or "") not in account_names
        for candidate in native_entries
        for key, account, _currency in candidate["inventory_map"]
        for value in [{"account": account}]
    ):
        frappe.throw(_("Count native account resolver selected an unlocked Account."))
    return {
        "session": doc.name,
        "revision": int(doc.get("evidence_revision") or 0),
        "snapshot_digest": str(doc.get("snapshot_digest") or ""),
        "frozen_at": str(doc.get("frozen_at") or ""),
        "posting_policy": _COUNT_POSTING_POLICY,
        "site_timezone": str(frappe.utils.get_system_timezone()),
        "company": str(doc.get("company")),
        "company_policy": {field: str(company.get(field) or "") for field in company_fields},
        "precision": {
            "stock_value_difference": int(
                frappe.get_precision("Stock Ledger Entry", "stock_value_difference") or 0
            ),
            "gl_debit": int(frappe.get_precision("GL Entry", "debit") or 0),
            "gl_credit": int(frappe.get_precision("GL Entry", "credit") or 0),
        },
        "dimensions": [(str(row.name), str(row.fieldname), str(row.document_type)) for row in dimensions],
        "item_valuation": [
            (
                str(item.name),
                str(item.valuation_method or ""),
                str(item.valuation_rate or ""),
                str(item.standard_rate or ""),
                int(item.has_serial_no or 0),
                int(item.has_batch_no or 0),
                str(get_valuation_method(item.name, doc.get("company"))),
            )
            for item in items
        ],
        "warehouse_sources": [
            tuple(
                str(row.get(field) or "")
                for field in ("name", "parent_warehouse", "account", "company", "lft", "rgt", "is_group")
            )
            for row in sorted(warehouse_rows, key=lambda value: (int(value.lft or 0), str(value.name)))
        ],
        "item_defaults": [
            tuple(
                str(row.get(field) or "")
                for field in (
                    "name",
                    "parent",
                    "company",
                    "default_warehouse",
                    "expense_account",
                    "income_account",
                )
            )
            for row in item_defaults
        ],
        "item_group_defaults": [
            tuple(
                str(row.get(field) or "")
                for field in (
                    "name",
                    "parent_item_group",
                    "default_expense_account",
                    "default_income_account",
                )
            )
            for row in group_defaults
        ],
        "brand_defaults": [
            tuple(
                str(row.get(field) or "")
                for field in ("name", "default_expense_account", "default_income_account")
            )
            for row in brand_defaults
        ],
        "valuation_policy": {
            "stock_settings_do_not_use_batchwise_valuation": int(stock_settings or 0),
            "batches": [
                tuple(str(row.get(field) or "") for field in ("name", "use_batchwise_valuation"))
                for row in batch_rows
            ],
            "item_prices": [
                tuple(
                    str(row.get(field) or "")
                    for field in ("name", "item_code", "price_list", "currency", "buying", "price_list_rate")
                )
                for row in item_prices
            ],
            "sle_history": [
                tuple(
                    str(row.get(field) or "")
                    for field in (
                        "name",
                        "item_code",
                        "warehouse",
                        "posting_date",
                        "posting_time",
                        "posting_datetime",
                        "creation",
                        "actual_qty",
                        "valuation_rate",
                        "stock_value_difference",
                        "stock_queue",
                        "batch_no",
                        "serial_and_batch_bundle",
                        "voucher_type",
                        "voucher_no",
                    )
                )
                for row in history
            ],
            "bundles": [
                tuple(
                    str(row.get(field) or "")
                    for field in (
                        "name",
                        "posting_datetime",
                        "warehouse",
                        "item_code",
                        "voucher_type",
                        "voucher_no",
                    )
                )
                for row in bundle_rows
            ],
        },
        "accounts": [
            tuple(
                str(row.get(field) or "")
                for field in (
                    "name",
                    "company",
                    "account_currency",
                    "disabled",
                    "is_group",
                    "account_type",
                    "report_type",
                )
            )
            for row in account_rows
        ],
        "source": source,
        "entries": native_entries,
    }


def _candidate_digest(doc: Document, entries: list[Document]) -> str:
    payload = _candidate_projection(doc, entries)
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _count_effective_timestamp(doc: Document) -> Any:
    """Return the immutable freeze cutoff used as the native stock posting time."""
    from frappe.utils import get_datetime

    frozen_at = doc.get("frozen_at")
    if not frozen_at:
        frappe.throw(_("Frozen Count is missing its effective posting timestamp."))
    return get_datetime(frozen_at)


def _candidate_posting_stamp(entry: Document) -> Any:
    """Return the exact posting timestamp bound into the approved candidate digest."""
    from frappe.utils import get_datetime

    posting_date = entry.get("posting_date")
    posting_time = entry.get("posting_time")
    if not posting_date or not posting_time:
        frappe.throw(_("Approved Count correction is missing its posting timestamp."))
    return get_datetime(f"{posting_date} {posting_time}")


@contextmanager
def _candidate_write_proof(doc: Document, entry: Document, operation: str) -> Iterator[dict[str, Any]]:
    if getattr(frappe.local, "_stock_count_candidate_proof", None):
        frappe.throw(_("Another Count correction candidate operation is active."))
    proof: dict[str, Any] = {
        "document": entry,
        "session": doc.name,
        "revision": int(doc.get("evidence_revision") or 0),
        "snapshot_digest": str(doc.get("snapshot_digest") or ""),
        "candidate_digest": str(doc.get("accounting_candidate_digest") or ""),
        "operation": operation,
        "actor": str(frappe.session.user or ""),
        "consumed": False,
    }
    frappe.local._stock_count_candidate_proof = proof
    try:
        yield proof
        if not proof["consumed"]:
            frappe.throw(_("Native Count candidate did not consume its protected operation."))
    finally:
        frappe.local._stock_count_candidate_proof = None


def _prepared_candidates(doc: Document, *, require_complete: bool = True) -> list[Document]:
    from decimal import Decimal

    records = frappe.db.get_values(
        "Stock Entry",
        {
            "stock_count_session": doc.name,
            "stock_count_evidence_revision": doc.get("evidence_revision"),
        },
        ["name", "docstatus", "workflow_state"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    names: list[str] = []
    for record in records:
        status, state = int(record.docstatus), str(record.workflow_state or "")
        if (status, state) == (0, "Stock Entry Draft"):
            names.append(str(record.name))
        elif (status, state) not in {
            (0, "Stock Count Correction Retired"),
            (2, "Stock Entry Cancelled"),
        }:
            frappe.throw(_("Count has an unexpected nonterminal correction candidate."))
    candidates = [cast(Document, frappe.get_doc("Stock Entry", name, for_update=True)) for name in names]
    expected_groups = _correction_rows(doc)
    actual_groups: dict[tuple[str, str], Document] = {}
    for entry in candidates:
        items = list(entry.get("items") or [])
        if not items or entry.get("company") != doc.get("company"):
            frappe.throw(_("Count correction candidate has an invalid Company or empty detail."))
        warehouse = str(items[0].get("s_warehouse") or items[0].get("t_warehouse") or "")
        group = (str(entry.get("purpose") or ""), warehouse)
        if group not in expected_groups or group in actual_groups:
            frappe.throw(_("Count correction has an extra or duplicate active native Draft."))
        actual_groups[group] = entry
        expected_rows = _correction_rows(doc, {group: str(entry.name)})[group]
        fields = (
            "item_code",
            "uom",
            "stock_uom",
            "s_warehouse",
            "t_warehouse",
            "storage_location",
            "to_storage_location",
            "batch_no",
            "serial_no",
            "stock_count_session_source_item",
            "stock_count_session_target_item",
            "stock_count_effect_key",
        )
        actual_rows = sorted(
            (
                tuple(str(row.get(field) or "") for field in fields),
                Decimal(str(row.get("qty") or 0)),
                Decimal(str(row.get("conversion_factor") or 0)),
            )
            for row in items
        )
        signed_rows = sorted(
            (
                tuple(str(row.get(field) or "") for field in fields),
                Decimal(str(row.get("qty") or 0)),
                Decimal(str(row.get("conversion_factor") or 0)),
            )
            for row in expected_rows
        )
        if actual_rows != signed_rows or int(entry.get("stock_count_evidence_revision") or 0) != int(
            doc.get("evidence_revision") or 0
        ):
            frappe.throw(_("Count correction candidate differs from its current signed effect."))
    if require_complete and set(actual_groups) != set(expected_groups):
        frappe.throw(_("Count correction candidate set is missing an approved group."))
    return candidates


def _prepare_candidates(doc: Document) -> list[Document]:
    if _prepared_candidates(doc, require_complete=False):
        frappe.throw(_("Count correction candidates already exist for this revision."))
    groups = _correction_rows(doc)
    if bool(groups) != bool(doc.get("has_variance")):
        frappe.throw(_("Count variance has no exact native correction group."))
    candidates: list[Document] = []
    stamp = _count_effective_timestamp(doc)
    for (purpose, warehouse), rows in sorted(groups.items()):
        if not rows or any(
            warehouse not in {str(row.get("s_warehouse") or ""), str(row.get("t_warehouse") or "")}
            for row in rows
        ):
            frappe.throw(_("Count correction group has an inconsistent Warehouse."))
        entry = frappe.new_doc("Stock Entry")
        entry.update(
            {
                "company": doc.get("company"),
                "purpose": purpose,
                "stock_entry_type": purpose,
                "stock_count_session": doc.name,
                "stock_count_evidence_revision": doc.get("evidence_revision"),
                "set_posting_time": 1,
                "posting_date": stamp.date(),
                "posting_time": stamp.time(),
            }
        )
        for row in rows:
            entry.append("items", row)
        entry.set_new_name(set_child_names=True)
        if not entry.name or any(not row.name for row in entry.get("items") or []):
            frappe.throw(_("Native Count candidate naming did not assign every row."))
        lines = {str(line.name): line for line in _current_lines(doc)}
        for row in entry.get("items") or []:
            source = lines.get(str(row.get("stock_count_session_source_item") or ""))
            target = lines.get(str(row.get("stock_count_session_target_item") or ""))
            row.set("stock_count_effect_key", _effect_key(doc, str(entry.name), source, target, purpose))
        before_serial = {
            str(row.get("serial_no")): bool(
                frappe.db.get_value(
                    "Serial No", str(row.get("serial_no")), "name", for_update=True, wait=False
                )
            )
            for row in rows
            if row.get("serial_no")
        }
        with _candidate_write_proof(doc, entry, "prepare"):
            entry.insert()
        if entry.docstatus != 0 or any(
            row.get("serial_and_batch_bundle") for row in entry.get("items") or []
        ):
            frappe.throw(_("Draft Count candidate created a native stock or Bundle effect."))
        if any(
            bool(frappe.db.get_value("Serial No", serial, "name", for_update=True, wait=False)) != present
            for serial, present in before_serial.items()
        ):
            frappe.throw(_("Draft Count candidate changed a Serial No master before approval."))
        candidates.append(entry)
    return candidates


def retire_count_correction(entry: Document) -> None:
    """Native terminal transition task; the adapter consumes its parent-bound proof."""
    proof = getattr(frappe.local, "_stock_count_candidate_proof", None)
    if (
        not isinstance(proof, dict)
        or proof.get("document") is not entry
        or proof.get("operation") != "retire"
        or proof.get("actor") != frappe.session.user
        or entry.docstatus != 0
        or entry.get("workflow_state") != "Stock Count Correction Retired"
    ):
        frappe.throw(_("Count correction retirement requires its protected parent decision."))
    for doctype in ("Stock Ledger Entry", "GL Entry"):
        if frappe.db.exists(doctype, {"voucher_type": "Stock Entry", "voucher_no": entry.name}):
            frappe.throw(_("A Count correction with native effects cannot be retired."))


def _retire_candidates(doc: Document, action: str, source: str, target: str) -> None:
    from frappe.model.workflow import apply_workflow

    candidates = _prepared_candidates(doc)
    for entry in candidates:
        if entry.get("workflow_state") != "Stock Entry Draft":
            frappe.throw(_("A stale Count correction cannot be retired from this native state."))
        prior_ignore_permissions = entry.flags.get("ignore_permissions")
        with _candidate_write_proof(doc, entry, "retire") as proof:
            proof.update(
                {
                    "source_action": action,
                    "source_state": source,
                    "parent_target": target,
                    "entry_digest": sha256(
                        json.dumps(
                            _candidate_projection(doc, [entry])["entries"][0],
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                }
            )
            try:
                entry.flags.ignore_permissions = True
                entry = cast(Document, apply_workflow(entry, "Retire Count Correction"))
            finally:
                entry.flags.ignore_permissions = prior_ignore_permissions
        if entry.docstatus != 0 or entry.get("workflow_state") != "Stock Count Correction Retired":
            frappe.throw(_("Native Count correction retirement did not reach its terminal state."))


def send_count_for_review(doc: Document) -> None:
    _lock_session(doc, {"Frozen", "Returned"})
    user, _employee = _actor(doc, "Stock User")
    if user != doc.get("maker_user") or doc.get("workflow_state") != "Pending Review":
        frappe.throw(_("Only the Count maker may send its current evidence for review."))
    if doc.get("evidence_invalidated"):
        frappe.throw(_("Emergency movement requires a full new Count revision."))
    variance = _verify_complete(doc)
    doc.set("has_variance", int(variance))
    doc.set("count_complete", 1)
    doc.set("snapshot_digest", _evidence_digest(doc))
    _authorize_transition_save(doc, {"workflow_state", "has_variance", "count_complete", "snapshot_digest"})


def review_count(doc: Document) -> None:
    _lock_session(doc, {"Pending Review"})
    user, employee = _actor(doc, "Stock Manager")
    if doc.get("workflow_state") != "Pending Stock Approval" or user == doc.get("maker_user"):
        frappe.throw(_("Count checker must differ from the maker."))
    if doc.get("evidence_invalidated") or not doc.get("count_complete"):
        frappe.throw(_("Count evidence must be complete and current before review."))
    variance = _verify_complete(doc)
    if bool(variance) != bool(doc.get("has_variance")) or _evidence_digest(doc) != doc.get("snapshot_digest"):
        frappe.throw(_("Count evidence changed after it was sent for review."))
    recount_users = frappe.db.get_values(
        "Stock Count Observation",
        {"session": doc.name, "evidence_revision": doc.get("evidence_revision"), "pass_type": "Recount"},
        "observer_user",
        pluck=True,
        for_update=True,
        wait=False,
    )
    if user in recount_users:
        frappe.throw(_("Count checker must differ from every Recount observer."))
    _current_baseline_is_unchanged(doc)
    candidates = _prepare_candidates(doc)
    required, settings_digest = _accounting_settings(doc)
    doc.set("accounting_review_required", int(required))
    doc.set("accounting_predicate_revision", doc.get("evidence_revision"))
    doc.set("accounting_settings_digest", settings_digest)
    doc.set("accounting_candidate_digest", _candidate_digest(doc, candidates))
    doc.set("checker_user", user)
    doc.set("checker_employee", employee)
    doc.set("checker_at", now())
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "checker_user",
            "checker_employee",
            "checker_at",
            "accounting_review_required",
            "accounting_predicate_revision",
            "accounting_settings_digest",
            "accounting_candidate_digest",
        },
    )


def _accounting_settings(doc: Document) -> tuple[bool, str]:
    company = frappe.db.get_value(
        "Company",
        doc.get("company"),
        ["enable_perpetual_inventory", "enable_provisional_accounting_for_non_stock_items"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if not company:
        frappe.throw(_("Count Company accounting settings are unavailable."))
    item_codes = sorted({str(row.get("item_code")) for row in _current_lines(doc)})
    items = (
        frappe.db.get_values(
            "Item",
            {"name": ("in", item_codes)},
            ["name", "is_stock_item", "is_fixed_asset"],
            as_dict=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        if item_codes
        else []
    )
    if len(items) != len(item_codes) or any(not row.is_stock_item or row.is_fixed_asset for row in items):
        frappe.throw(_("Count lines require current stock Items that are not fixed assets."))
    payload = {
        "company": doc.get("company"),
        "perpetual": int(company.enable_perpetual_inventory or 0),
        "provisional": int(company.enable_provisional_accounting_for_non_stock_items or 0),
        "items": item_codes,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    required = bool(doc.get("has_variance") and (payload["perpetual"] or payload["provisional"]))
    return required, digest


def approve_count_stock(doc: Document) -> None:
    _lock_session(doc, {"Pending Stock Approval"})
    user, employee = _actor(doc, "Stock Manager")
    if user in {doc.get("maker_user"), doc.get("checker_user")}:
        frappe.throw(_("Stock approver must differ from the maker and checker."))
    if doc.get("evidence_invalidated") or _evidence_digest(doc) != doc.get("snapshot_digest"):
        frappe.throw(_("Count evidence changed after checker review."))
    required, settings_digest = _accounting_settings(doc)
    candidates = _prepared_candidates(doc)
    if (
        required != bool(doc.get("accounting_review_required"))
        or settings_digest != doc.get("accounting_settings_digest")
        or _candidate_digest(doc, candidates) != doc.get("accounting_candidate_digest")
        or int(doc.get("accounting_predicate_revision") or 0) != int(doc.get("evidence_revision") or 0)
    ):
        frappe.throw(_("Count accounting route changed after independent review."))
    expected = "Pending Accounting" if required else "Approved"
    if doc.get("workflow_state") != expected:
        frappe.throw(_("Stock approval chose the wrong accounting route."))
    doc.set("accounting_review_required", int(required))
    doc.set("accounting_predicate_revision", doc.get("evidence_revision"))
    doc.set("accounting_settings_digest", settings_digest)
    doc.set("approved_digest", doc.get("snapshot_digest"))
    doc.set("stock_approver_user", user)
    doc.set("stock_approver_employee", employee)
    doc.set("stock_approver_at", now())
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "accounting_review_required",
            "accounting_predicate_revision",
            "accounting_settings_digest",
            "approved_digest",
            "stock_approver_user",
            "stock_approver_employee",
            "stock_approver_at",
        },
    )


def approve_count_accounting(doc: Document) -> None:
    _lock_session(doc, {"Pending Accounting"})
    user, employee = _actor(doc, "Accounts Manager")
    if user in {doc.get("maker_user"), doc.get("checker_user"), doc.get("stock_approver_user")}:
        frappe.throw(_("Accounts approver must differ from earlier Count actors."))
    if doc.get("workflow_state") != "Approved" or not doc.get("accounting_review_required"):
        frappe.throw(_("Accounting approval requires a protected Count variance."))
    required, settings_digest = _accounting_settings(doc)
    candidates = _prepared_candidates(doc)
    if (
        not required
        or settings_digest != doc.get("accounting_settings_digest")
        or _evidence_digest(doc) != doc.get("approved_digest")
        or _candidate_digest(doc, candidates) != doc.get("accounting_candidate_digest")
    ):
        frappe.throw(_("Count accounting settings or evidence changed after stock approval."))
    doc.set("accounts_approver_user", user)
    doc.set("accounts_approver_employee", employee)
    doc.set("accounts_approver_at", now())
    doc.set("accounting_reviewed_digest", doc.get("accounting_candidate_digest"))
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "accounts_approver_user",
            "accounts_approver_employee",
            "accounts_approver_at",
            "accounting_reviewed_digest",
        },
    )


_REASON_SOURCES: dict[str, frozenset[str]] = {
    "Return Count for Recount": frozenset({"Pending Review"}),
    "Return Count from Stock Approval": frozenset({"Pending Stock Approval"}),
    "Return Count from Accounting": frozenset({"Pending Accounting"}),
    "Return Approved Count for Recapture": frozenset({"Approved"}),
    "Restart Frozen Count after Invalidation": frozenset({"Frozen"}),
    "Restart Count after Invalidation": frozenset({"Pending Review", "Pending Stock Approval"}),
    "Restart Approved Count after Invalidation": frozenset({"Approved"}),
    "Restart Returned Count after Invalidation": frozenset({"Returned"}),
    "Restart Recapture after Invalidation": frozenset({"Recapture Required"}),
    "Reject Count from Review": frozenset({"Pending Review"}),
    "Reject Count from Stock Approval": frozenset({"Pending Stock Approval"}),
    "Reject Restarted Count": frozenset({"Restart Required"}),
    "Reject Recaptured Count": frozenset({"Recapture Required"}),
    "Abandon Draft Count": frozenset({"Draft"}),
    "Abandon Frozen Count": frozenset({"Frozen"}),
    "Abandon Pending Review Count": frozenset({"Pending Review"}),
    "Abandon Returned Count": frozenset({"Returned"}),
    "Abandon Pending Approval Count": frozenset({"Pending Stock Approval"}),
    "Abandon Pending Accounting Count": frozenset({"Pending Accounting"}),
    "Abandon Approved Count": frozenset({"Approved"}),
    "Abandon Restarted Count": frozenset({"Restart Required"}),
    "Abandon Recaptured Count": frozenset({"Recapture Required"}),
}


def record_reasoned_decision(doc: Document) -> None:
    """One native Return/Restart/Reject/Abandon task consumes its bound reason."""
    action = str(doc.get("pending_reason_action") or "")
    sources = _REASON_SOURCES.get(action)
    if not sources:
        frappe.throw(_("This Count decision has no approved reasoned route."))
    assert sources is not None
    _lock_session(doc, set(sources))
    source = frappe.db.get_value(_PARENT, doc.name, "workflow_state", for_update=True, wait=False)
    target = str(doc.get("workflow_state") or "")
    expected = (
        "Returned"
        if action.startswith("Return")
        else "Restart Required"
        if action.startswith("Restart")
        else "Rejected"
        if action.startswith("Reject")
        else "Abandoned"
    )
    if target != expected or source not in sources:
        frappe.throw(_("Count decision does not match its native Workflow transition."))
    user = str(frappe.session.user or "")
    role = (
        "Stock User"
        if action == "Abandon Draft Count"
        else "Accounts Manager"
        if source == "Pending Accounting"
        else "Stock Manager"
    )
    _actor(doc, role)
    if (
        doc.get("pending_reason_actor") != user
        or doc.get("pending_reason_state") != source
        or int(doc.get("pending_reason_revision") or 0) != int(doc.get("evidence_revision") or 0)
        or doc.get("pending_reason_digest") != (doc.get("snapshot_digest") or "")
        or not str(doc.get("pending_reason_text") or "").strip()
    ):
        frappe.throw(_("Count decision reason is stale or belongs to another actor."))
    if target == "Restart Required" and not doc.get("evidence_invalidated"):
        _required, settings_digest = _accounting_settings(doc)
        if not doc.get("accounting_settings_digest") or settings_digest == doc.get(
            "accounting_settings_digest"
        ):
            frappe.throw(_("Restart requires an emergency invalidation or changed accounting settings."))
    if action == "Abandon Draft Count" and user != doc.owner:
        frappe.throw(_("Only the Draft Count owner may abandon it."))
    if source in {"Pending Stock Approval", "Pending Accounting", "Approved"}:
        _retire_candidates(doc, action, str(source), target)
    reason = str(doc.get("pending_reason_text"))
    timestamp = now()
    event_type = (
        "Returned"
        if target == "Returned"
        else "Restart Requested"
        if target == "Restart Required"
        else "Rejected"
        if target == "Rejected"
        else "Abandoned"
    )
    event = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Stock Count Evidence Event",
                "session": doc.name,
                "event_type": event_type,
                "source_action": action,
                "from_revision": doc.get("evidence_revision") or 0,
                "reason": reason,
                "actor_user": user,
                "event_at": timestamp,
                "prior_snapshot_digest": doc.get("snapshot_digest") or "",
            }
        ),
    )
    _insert_count_evidence(event)
    doc.set("decision_reason", reason)
    doc.set("decision_actor", user)
    doc.set("decision_at", timestamp)
    for field in (
        "pending_reason_action",
        "pending_reason_actor",
        "pending_reason_state",
        "pending_reason_revision",
        "pending_reason_digest",
        "pending_reason_text",
        "pending_reason_at",
    ):
        doc.set(field, None)
    fields = {
        "workflow_state",
        "decision_reason",
        "decision_actor",
        "decision_at",
        "pending_reason_action",
        "pending_reason_actor",
        "pending_reason_state",
        "pending_reason_revision",
        "pending_reason_digest",
        "pending_reason_text",
        "pending_reason_at",
    }
    if target in {"Returned", "Restart Required"}:
        for actor in ("checker", "stock_approver", "accounts_approver"):
            for suffix in ("user", "employee", "at"):
                field = f"{actor}_{suffix}"
                doc.set(field, None)
                fields.add(field)
        for field in (
            "approved_digest",
            "accounting_review_required",
            "accounting_predicate_revision",
            "accounting_settings_digest",
            "accounting_candidate_digest",
            "accounting_reviewed_digest",
        ):
            doc.set(field, None)
            fields.add(field)
    if target in {"Rejected", "Abandoned"}:
        for scope_row in doc.get("scope") or []:
            scope_row.freeze_active = 0
            scope_row.lease_state = "Released"
            scope_row.released_at = timestamp
        fields.add("scope")
    _authorize_transition_save(doc, fields)


def capture_new_count_revision(doc: Document) -> None:
    """Append a complete fresh baseline after a protected Restart action."""
    _lock_session(doc, {"Restart Required"})
    _actor(doc, "Stock Manager")
    if doc.get("workflow_state") != "Recapture Required":
        frappe.throw(_("New Count revision requires the native Capture action."))
    previous = int(doc.get("evidence_revision") or 0)
    prior_digest = str(doc.get("snapshot_digest") or "")
    _capture_revision(doc, first=False)
    doc.set("count_complete", 0)
    doc.set("has_variance", 0)
    event = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Stock Count Evidence Event",
                "session": doc.name,
                "event_type": "Revision Recaptured",
                "source_action": "Capture New Count Revision",
                "from_revision": previous,
                "to_revision": doc.get("evidence_revision"),
                "reason": doc.get("decision_reason"),
                "actor_user": str(frappe.session.user),
                "event_at": now(),
                "prior_snapshot_digest": prior_digest,
                "new_snapshot_digest": doc.get("snapshot_digest"),
            }
        ),
    )
    _insert_count_evidence(event)
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "scope",
            "locations",
            "items",
            "evidence_revision",
            "cutoff_datetime",
            "snapshot_digest",
            "count_complete",
            "has_variance",
        },
    )


def complete_recaptured_count(doc: Document) -> None:
    _lock_session(doc, {"Recapture Required"})
    user, _employee = _actor(doc, "Stock User")
    if user != doc.get("maker_user") or doc.get("workflow_state") != "Frozen":
        frappe.throw(_("Only the original maker may complete a recaptured Count."))
    if _has_current_revision_emergency(doc):
        frappe.throw(_("Another emergency changed stock after the latest Count capture."))
    variance = _verify_complete(doc)
    doc.set("has_variance", int(variance))
    doc.set("count_complete", 1)
    doc.set("snapshot_digest", _evidence_digest(doc))
    doc.set("evidence_invalidated", 0)
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "has_variance",
            "count_complete",
            "snapshot_digest",
            "evidence_invalidated",
        },
    )


def _current_baseline_is_unchanged(doc: Document) -> None:
    """Reject a correction when native dimensioned stock moved after recapture."""
    cutoff = now()
    for line in _current_lines(doc):
        snapshot = snapshot_location(
            company=str(doc.get("company")),
            item_code=str(line.get("item_code")),
            warehouse=str(line.get("warehouse")),
            storage_location=str(line.get("storage_location")),
            cutoff=cutoff,
            locking_read=True,
        )
        if line.get("serial_no") or line.get("batch_no"):
            current = next(
                (
                    qty
                    for serial, batch, qty in snapshot.identities
                    if serial == str(line.get("serial_no") or "") and batch == str(line.get("batch_no") or "")
                ),
                0,
            )
        else:
            current = snapshot.quantity
        from decimal import Decimal

        if Decimal(str(current)) != Decimal(str(line.get("system_qty") or 0)):
            frappe.throw(_("Native stock changed after Count capture; restart the full count."))


def _effect_key(
    doc: Document, candidate_name: str, source: Document | None, target: Document | None, purpose: str
) -> str:
    if not candidate_name:
        frappe.throw(_("Count correction requires an assigned native Stock Entry name."))
    payload = (
        doc.name,
        int(doc.get("evidence_revision") or 0),
        candidate_name,
        str(source.get("line_key") or "") if source else "",
        str(target.get("line_key") or "") if target else "",
        purpose,
    )
    return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _correction_rows(
    doc: Document, candidate_names: dict[tuple[str, str], str] | None = None
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Build native stock-UOM effects and pair proven relocated Serials."""
    from decimal import Decimal

    positives: list[Document] = []
    negatives: list[Document] = []
    for line in _current_lines(doc):
        delta = Decimal(str(line.get("variance_qty") or 0))
        if delta > 0:
            positives.append(line)
        elif delta < 0:
            negatives.append(line)
    paired: set[str] = set()
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def add(purpose: str, warehouse: str, row: dict[str, Any]) -> None:
        result.setdefault((purpose, warehouse), []).append(row)

    for source in negatives:
        if not source.get("serial_no"):
            continue
        matches = [
            target
            for target in positives
            if target.get("serial_no") == source.get("serial_no")
            and target.get("item_code") == source.get("item_code")
            and target.get("warehouse") == source.get("warehouse")
            and target.get("storage_location") != source.get("storage_location")
            and target.get("batch_no") == source.get("batch_no")
            and Decimal(str(target.get("variance_qty") or 0)) == 1
            and Decimal(str(source.get("variance_qty") or 0)) == -1
        ]
        if len(matches) > 1:
            frappe.throw(_("Relocated Serial has ambiguous Count destinations."))
        if not matches:
            continue
        target = matches[0]
        if target.name in paired:
            frappe.throw(_("Relocated Serial is paired more than once."))
        paired.update({str(source.name), str(target.name)})
        add(
            "Material Transfer",
            str(source.get("warehouse")),
            {
                "item_code": source.get("item_code"),
                "qty": 1,
                "uom": source.get("stock_uom"),
                "stock_uom": source.get("stock_uom"),
                "conversion_factor": 1,
                "s_warehouse": source.get("warehouse"),
                "t_warehouse": target.get("warehouse"),
                "storage_location": source.get("storage_location"),
                "to_storage_location": target.get("storage_location"),
                "batch_no": source.get("batch_no"),
                "serial_no": source.get("serial_no"),
                "stock_count_session_source_item": source.name,
                "stock_count_session_target_item": target.name,
                "stock_count_effect_key": (
                    _effect_key(
                        doc,
                        (candidate_names or {}).get(("Material Transfer", str(source.get("warehouse"))), ""),
                        source,
                        target,
                        "Material Transfer",
                    )
                    if candidate_names
                    and ("Material Transfer", str(source.get("warehouse"))) in candidate_names
                    else ""
                ),
            },
        )
    for purpose, lines in (("Material Issue", negatives), ("Material Receipt", positives)):
        for line in lines:
            if line.name in paired:
                continue
            delta = Decimal(str(line.get("variance_qty") or 0))
            if line.get("serial_no") and abs(delta) != 1:
                frappe.throw(_("Serial Count correction quantity must be exactly one."))
            warehouse = str(line.get("warehouse"))
            row: dict[str, Any] = {
                "item_code": line.get("item_code"),
                "qty": float(abs(delta)),
                "uom": line.get("stock_uom"),
                "stock_uom": line.get("stock_uom"),
                "conversion_factor": 1,
                "batch_no": line.get("batch_no"),
                "serial_no": line.get("serial_no"),
                "stock_count_effect_key": (
                    _effect_key(
                        doc,
                        (candidate_names or {}).get((purpose, warehouse), ""),
                        line if purpose == "Material Issue" else None,
                        line if purpose == "Material Receipt" else None,
                        purpose,
                    )
                    if candidate_names and (purpose, warehouse) in candidate_names
                    else ""
                ),
            }
            if purpose == "Material Issue":
                row.update(
                    {
                        "s_warehouse": warehouse,
                        "storage_location": line.get("storage_location"),
                        "stock_count_session_source_item": line.name,
                    }
                )
            else:
                row.update(
                    {
                        "t_warehouse": warehouse,
                        "to_storage_location": line.get("storage_location"),
                        "stock_count_session_target_item": line.name,
                    }
                )
            add(purpose, warehouse, row)
    return result


def _bundle_for_row(entry: Document, row: Document, line: Document, purpose: str) -> None:
    """Attach a draft native SABB with the exact observed Batch/Serial."""
    from erpnext.stock.serial_batch_bundle import SerialBatchCreation

    serial = str(line.get("serial_no") or "")
    batch = str(line.get("batch_no") or "")
    if not serial and not batch:
        return
    if batch:
        batch_item = frappe.db.get_value("Batch", batch, "item", for_update=True, wait=False)
        if batch_item != line.get("item_code"):
            frappe.throw(_("Observed Batch requires an existing master for the same Item."))
    inward = purpose == "Material Receipt"
    qty = float(row.get("qty") or 0)
    args = {
        "item_code": str(line.get("item_code")),
        "company": str(entry.get("company")),
        "warehouse": str(row.get("t_warehouse") if inward else row.get("s_warehouse")),
        "posting_date": entry.get("posting_date"),
        "posting_time": entry.get("posting_time"),
        "voucher_type": "Stock Entry",
        "voucher_no": entry.name,
        "voucher_detail_no": row.name,
        "type_of_transaction": "Inward" if inward else "Outward",
        "actual_qty": qty if inward else -qty,
        "qty": qty,
        "do_not_submit": True,
        "use_serial_batch_fields": bool(inward and serial),
    }
    bundle = SerialBatchCreation(args).make_serial_and_batch_bundle(
        serial_nos=[serial] if serial else None,
        batch_nos={batch: qty} if batch else None,
    )
    if not bundle or not bundle.get("name"):
        frappe.throw(_("Native Serial and Batch Bundle could not be created for Count correction."))
    row.set("serial_and_batch_bundle", bundle.name)


def _submit_prepared_candidate(
    doc: Document, entry: Document, stamp: Any, approved_entry: dict[str, Any]
) -> Document:
    """Attach approved identity bundles and natively submit this exact Draft."""
    from frappe.model.workflow import apply_workflow

    if entry.docstatus != 0 or entry.get("workflow_state") != "Stock Entry Draft":
        frappe.throw(_("Count correction candidate is no longer an exact native Draft."))
    if entry.get("posting_date") != stamp.date() or str(entry.get("posting_time")) != str(stamp.time()):
        frappe.throw(_("Count candidate execution timestamp changed after validation."))
    lines = {str(row.name): row for row in _current_lines(doc)}
    for row in entry.get("items") or []:
        source = lines.get(str(row.get("stock_count_session_source_item") or ""))
        target = lines.get(str(row.get("stock_count_session_target_item") or ""))
        if not source and not target:
            frappe.throw(_("Native Count correction lost its signed line linkage."))
        linked_line = source if source is not None else target
        assert linked_line is not None
        _bundle_for_row(entry, row, linked_line, str(entry.get("purpose")))
    with _candidate_write_proof(doc, entry, "bundle"):
        entry.save()
    current_entry = _candidate_projection(doc, [entry])["entries"][0]
    for row in current_entry["rows"]:
        row.pop("serial_master_present", None)
    for row in approved_entry["rows"]:
        row.pop("serial_master_present", None)
    if current_entry != approved_entry:
        frappe.throw(_("Native Bundle creation changed approved Count accounting inputs."))
    proof = {
        "document": entry,
        "session": doc.name,
        "revision": int(doc.get("evidence_revision") or 0),
        "digest": str(doc.get("approved_digest") or ""),
        "phase": "before_submit",
        "actor": str(frappe.session.user or ""),
        "candidate_digest": str(doc.get("accounting_candidate_digest") or ""),
        "guarded": False,
        "consumed": False,
        "items": _count_effect_item_links(entry),
    }
    previous = getattr(frappe.local, "_stock_count_effect_proof", None)
    frappe.local._stock_count_effect_proof = proof
    try:
        entry = cast(Document, apply_workflow(entry, "Submit Stock Entry"))
        if proof["consumed"] or not proof["guarded"] or entry.docstatus != 1:
            frappe.throw(_("Native Count correction did not complete its protected submit."))
        _verify_native_entry(entry, bool(doc.get("accounting_review_required")), doc, approved_entry)
        proof["consumed"] = True
    finally:
        frappe.local._stock_count_effect_proof = previous
    return entry


def _verify_native_entry(
    entry: Document,
    accounting_required: bool,
    doc: Document,
    approved_entry: dict[str, Any] | None = None,
) -> None:
    """Check submitted native SLE and GL effects against linked correction detail rows."""
    from decimal import Decimal

    sle = frappe.db.get_values(
        "Stock Ledger Entry",
        {"voucher_type": "Stock Entry", "voucher_no": entry.name, "docstatus": 1, "is_cancelled": 0},
        [
            "name",
            "voucher_detail_no",
            "item_code",
            "warehouse",
            "storage_location",
            "actual_qty",
            "valuation_rate",
            "stock_value_difference",
            "serial_and_batch_bundle",
        ],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    actual = sorted(
        (
            str(row.voucher_detail_no),
            str(row.item_code),
            str(row.warehouse),
            str(row.storage_location or ""),
            Decimal(str(row.actual_qty)),
        )
        for row in sle
    )
    expected = []
    for row in entry.get("items") or []:
        qty = Decimal(str(row.get("transfer_qty") or row.get("qty") or 0))
        if row.get("s_warehouse"):
            expected.append(
                (
                    str(row.name),
                    str(row.item_code),
                    str(row.s_warehouse),
                    str(row.get("storage_location") or ""),
                    -qty,
                )
            )
        if row.get("t_warehouse"):
            expected.append(
                (
                    str(row.name),
                    str(row.item_code),
                    str(row.t_warehouse),
                    str(row.get("to_storage_location") or ""),
                    qty,
                )
            )
    if actual != sorted(expected):
        frappe.throw(
            _("Native Stock Ledger Entry does not match the approved Count locations and quantities.")
        )
    if approved_entry is not None:
        approved_rows = {str(row["name"]): row for row in approved_entry.get("rows", [])}
        value_precision = int(frappe.get_precision("Stock Ledger Entry", "stock_value_difference") or 2)
        quantum = Decimal(1).scaleb(-value_precision)
        for ledger_row in sle:
            projected = approved_rows.get(str(ledger_row.voucher_detail_no))
            if projected is None:
                frappe.throw(_("Native Count valuation has no approved Stock Entry detail projection."))
            assert projected is not None
            rates = projected.get("numbers", {})
            projected_rate = Decimal(rates.get("valuation_rate") or "0")
            if projected_rate == 0:
                projected_rate = Decimal(rates.get("incoming_rate") or "0")
            expected_value = (Decimal(str(ledger_row.actual_qty)) * projected_rate).quantize(quantum)
            if Decimal(str(ledger_row.stock_value_difference)).quantize(quantum) != expected_value:
                frappe.throw(_("Native Stock Ledger Entry value differs from approved Count valuation."))
    lines = {str(line.name): line for line in _current_lines(doc)}
    details = {str(row.name): row for row in entry.get("items") or []}
    bundles = sorted({str(row.serial_and_batch_bundle) for row in sle if row.serial_and_batch_bundle})
    bundle_entries = (
        frappe.db.get_values(
            "Serial and Batch Entry",
            {"parent": ("in", bundles), "parenttype": "Serial and Batch Bundle"},
            ["parent", "serial_no", "batch_no", "qty"],
            as_dict=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        if bundles
        else []
    )
    by_bundle: dict[str, list[Any]] = {}
    for child in bundle_entries:
        by_bundle.setdefault(str(child.parent), []).append(child)
    for leg in sle:
        detail = details.get(str(leg.voucher_detail_no))
        if detail is None:
            frappe.throw(_("Native Count ledger leg has no correction detail."))
        assert detail is not None
        line_ref = (
            detail.get("stock_count_session_target_item")
            if Decimal(str(leg.actual_qty)) > 0
            else detail.get("stock_count_session_source_item")
        )
        line = lines.get(str(line_ref or ""))
        if line is None:
            frappe.throw(_("Native Count ledger leg has no approved identity line."))
        assert line is not None
        identity = (str(line.get("serial_no") or ""), str(line.get("batch_no") or ""))
        bundle = str(leg.serial_and_batch_bundle or "")
        children = by_bundle.get(bundle, []) if bundle else []
        if bool(identity[0] or identity[1]) != bool(bundle):
            frappe.throw(_("Native Count ledger Batch or Serial Bundle presence differs from approval."))
        if children:
            if any(
                (str(child.serial_no or ""), str(child.batch_no or "")) != identity for child in children
            ) or sum((Decimal(str(child.qty)) for child in children), Decimal(0)) != Decimal(
                str(leg.actual_qty)
            ):
                frappe.throw(_("Native Count ledger Batch or Serial differs from the approved line."))
        elif bundle:
            frappe.throw(_("Native Count ledger Bundle has no matching identity entries."))
    dimensions = frappe.db.get_values(
        "Accounting Dimension",
        {"disabled": 0},
        ["fieldname"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="fieldname",
    )
    dimension_names = sorted({str(row.fieldname) for row in dimensions if row.fieldname})
    gl_fields = [
        "name",
        "account",
        "account_currency",
        "company",
        "cost_center",
        "project",
        "debit",
        "credit",
        *dimension_names,
    ]
    gl = frappe.db.get_values(
        "GL Entry",
        {"voucher_type": "Stock Entry", "voucher_no": entry.name, "docstatus": 1, "is_cancelled": 0},
        gl_fields,
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    if accounting_required:
        if sum(Decimal(str(row.debit or 0)) - Decimal(str(row.credit or 0)) for row in gl):
            frappe.throw(_("Native Count correction GL must balance."))
        # This native method reads the already posted SLEs. It verifies actual GL
        # without predicting valuation or creating a second posting engine.
        from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry

        expected_gl = cast(StockEntry, entry).get_gl_entries(
            cast(StockEntry, entry).get_inventory_account_map()
        )

        def totals(rows: list[Any]) -> dict[tuple[str, ...], Decimal]:
            result: dict[tuple[str, ...], Decimal] = {}
            for row in rows:
                if row.get("company") != entry.get("company"):
                    frappe.throw(_("Native Count correction GL has a different Company."))
                key = tuple(
                    str(row.get(field) or "")
                    for field in ("account", "account_currency", "cost_center", "project", *dimension_names)
                )
                amount = Decimal(_native_number(row.get("debit"), "GL Entry", "debit")) - Decimal(
                    _native_number(row.get("credit"), "GL Entry", "credit")
                )
                result[key] = result.get(key, Decimal(0)) + amount
            return {key: amount for key, amount in result.items() if amount}

        if totals(gl) != totals(expected_gl):
            frappe.throw(_("Native Count correction GL differs from its posted SLE and account inputs."))
    elif gl:
        frappe.throw(_("Native Count correction posted GL outside the approved accounting route."))


def _verify_native_cancellation(entry: Document) -> None:
    """Require native cancellation to remove every active ledger effect."""
    for doctype in ("Stock Ledger Entry", "GL Entry"):
        active = frappe.db.exists(
            doctype,
            {
                "voucher_type": "Stock Entry",
                "voucher_no": entry.name,
                "docstatus": 1,
                "is_cancelled": 0,
            },
        )
        if active:
            frappe.throw(_("Native Count correction cancellation left an active ledger effect."))


def _verify_final_location_balances(doc: Document) -> None:
    """Check native SABB provenance and exact final identity balances before Close."""
    from collections import defaultdict
    from decimal import Decimal

    grouped: dict[tuple[str, str, str], list[Document]] = defaultdict(list)
    for line in _current_lines(doc):
        grouped[
            (
                str(line.get("item_code")),
                str(line.get("warehouse")),
                str(line.get("storage_location")),
            )
        ].append(line)
    cutoff = now()
    for (item_code, warehouse, location), lines in grouped.items():
        snapshot = snapshot_location(
            company=str(doc.get("company")),
            item_code=item_code,
            warehouse=warehouse,
            storage_location=location,
            cutoff=cutoff,
            locking_read=True,
        )
        expected_total = sum((Decimal(str(line.get("counted_qty") or 0)) for line in lines), Decimal(0))
        if snapshot.quantity != expected_total:
            frappe.throw(_("Native Count correction did not produce the approved Location balance."))
        if any(line.get("serial_no") or line.get("batch_no") for line in lines):
            expected = sorted(
                (
                    str(line.get("serial_no") or ""),
                    str(line.get("batch_no") or ""),
                    Decimal(str(line.get("counted_qty") or 0)),
                )
                for line in lines
                if Decimal(str(line.get("counted_qty") or 0))
            )
            actual = sorted((serial, batch, qty) for serial, batch, qty in snapshot.identities if qty)
            if actual != expected:
                frappe.throw(_("Native Count correction changed a different Batch or Serial balance."))
        elif snapshot.identities:
            frappe.throw(_("Native Count correction has an unexpected Batch or Serial Bundle."))


def _cancellation_gl_source(doc: Document) -> tuple[bool, str, tuple[str, ...]]:
    """Digest actual, current original GL and linked native correction identity."""
    names = tuple(
        str(name)
        for name in frappe.db.get_values(
            "Stock Entry",
            {
                "stock_count_session": doc.name,
                "stock_count_evidence_revision": doc.get("evidence_revision"),
                "docstatus": 1,
            },
            "name",
            pluck=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
    )
    if bool(names) != bool(doc.get("has_variance")):
        frappe.throw(_("Submitted Count correction links are incomplete."))
    dimensions = frappe.db.get_values(
        "Accounting Dimension",
        {"disabled": 0},
        ["name", "fieldname", "document_type"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    dimension_names = sorted({str(row.fieldname) for row in dimensions if row.fieldname})
    fields = [
        "name",
        "voucher_type",
        "voucher_no",
        "voucher_detail_no",
        "company",
        "posting_date",
        "account",
        "account_currency",
        "debit",
        "credit",
        "cost_center",
        "project",
        *dimension_names,
    ]
    gl = (
        frappe.db.get_values(
            "GL Entry",
            {
                "voucher_type": "Stock Entry",
                "voucher_no": ("in", names),
                "docstatus": 1,
                "is_cancelled": 0,
            },
            fields,
            as_dict=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        if names
        else []
    )
    payload = {
        "session": doc.name,
        "revision": int(doc.get("evidence_revision") or 0),
        "entries": names,
        "dimensions": [(str(row.fieldname), str(row.document_type)) for row in dimensions],
        "gl": [tuple(str(row.get(field) or "") for field in fields) for row in gl],
    }
    return (
        bool(gl),
        sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        names,
    )


_CANCEL_REASON_FIELDS = {
    "pending_reason_action",
    "pending_reason_actor",
    "pending_reason_state",
    "pending_reason_revision",
    "pending_reason_digest",
    "pending_reason_text",
    "pending_reason_at",
}


def _consume_cancellation_reason(doc: Document, action: str, source: str, digest: str) -> str:
    if (
        doc.get("pending_reason_action") != action
        or doc.get("pending_reason_actor") != frappe.session.user
        or doc.get("pending_reason_state") != source
        or int(doc.get("pending_reason_revision") or 0) != int(doc.get("evidence_revision") or 0)
        or doc.get("pending_reason_digest") != digest
        or not str(doc.get("pending_reason_text") or "").strip()
    ):
        frappe.throw(_("Count cancellation reason is missing, stale or belongs to another actor."))
    reason = str(doc.get("pending_reason_text"))
    for field in _CANCEL_REASON_FIELDS:
        doc.set(field, None)
    return reason


def request_count_cancellation_accounting_review(doc: Document) -> None:
    _lock_session(doc, {"Closed"})
    user, _employee = _actor(doc, "Stock Manager")
    if doc.docstatus != 1 or doc.get("workflow_state") != "Cancellation Pending Accounting":
        frappe.throw(_("Cancellation accounting request requires a submitted Closed Count."))
    has_gl, digest, _names = _cancellation_gl_source(doc)
    if not has_gl:
        frappe.throw(_("Count cancellation has no current GL; use the direct Cancel action."))
    reason = _consume_cancellation_reason(
        doc, "Request Count Cancellation Accounting Review", "Closed", digest
    )
    doc.set("cancel_accounting_required", 1)
    doc.set("cancel_request_user", user)
    doc.set("cancel_request_at", now())
    doc.set("cancel_reason", reason)
    doc.set("cancel_gl_digest", digest)
    for field in (
        "cancel_accounts_user",
        "cancel_accounts_employee",
        "cancel_accounts_at",
        "cancel_accounts_digest",
    ):
        doc.set(field, None)
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "cancel_accounting_required",
            "cancel_request_user",
            "cancel_request_at",
            "cancel_reason",
            "cancel_gl_digest",
            "cancel_accounts_user",
            "cancel_accounts_employee",
            "cancel_accounts_at",
            "cancel_accounts_digest",
        }
        | _CANCEL_REASON_FIELDS,
    )


def approve_count_cancellation(doc: Document) -> None:
    _lock_session(doc, {"Cancellation Pending Accounting"})
    user, employee = _actor(doc, "Accounts Manager")
    if doc.docstatus != 1 or doc.get("workflow_state") != "Cancellation Approved":
        frappe.throw(_("Count cancellation is not pending Accounts review."))
    if user in {
        doc.get("cancel_request_user"),
        doc.get("maker_user"),
        doc.get("checker_user"),
        doc.get("stock_approver_user"),
    }:
        frappe.throw(_("Cancellation Accounts approver must differ from earlier Count actors."))
    has_gl, digest, _names = _cancellation_gl_source(doc)
    if not has_gl or digest != doc.get("cancel_gl_digest"):
        frappe.throw(_("Count cancellation GL source changed after the request."))
    doc.set("cancel_accounts_user", user)
    doc.set("cancel_accounts_employee", employee)
    doc.set("cancel_accounts_at", now())
    doc.set("cancel_accounts_digest", digest)
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "cancel_accounts_user",
            "cancel_accounts_employee",
            "cancel_accounts_at",
            "cancel_accounts_digest",
        },
    )
    authorize_account_submit_transition(doc, "Approve Count Cancellation")


def return_count_cancellation_review(doc: Document) -> None:
    source = frappe.db.get_value(_PARENT, doc.name, "workflow_state", for_update=True, wait=False)
    if source not in {"Cancellation Pending Accounting", "Cancellation Approved"}:
        frappe.throw(_("Count cancellation is not in Accounts review."))
    _lock_session(doc, {str(source)})
    user, _employee = _actor(doc, "Accounts Manager")
    if doc.docstatus != 1 or doc.get("workflow_state") != "Closed":
        frappe.throw(_("Count cancellation return must restore Closed state."))
    action = (
        "Return Count Cancellation Review"
        if source == "Cancellation Pending Accounting"
        else "Return Approved Count Cancellation"
    )
    _has_gl, digest, _names = _cancellation_gl_source(doc)
    reason = _consume_cancellation_reason(doc, action, str(source), digest)
    _insert_count_evidence(
        cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Stock Count Evidence Event",
                    "session": doc.name,
                    "event_type": "Returned",
                    "source_action": action,
                    "from_revision": doc.get("evidence_revision"),
                    "reason": reason,
                    "actor_user": user,
                    "event_at": now(),
                    "prior_snapshot_digest": doc.get("snapshot_digest"),
                }
            ),
        )
    )
    for field in (
        "cancel_gl_digest",
        "cancel_accounts_user",
        "cancel_accounts_employee",
        "cancel_accounts_at",
        "cancel_accounts_digest",
    ):
        doc.set(field, None)
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "cancel_gl_digest",
            "cancel_accounts_user",
            "cancel_accounts_employee",
            "cancel_accounts_at",
            "cancel_accounts_digest",
        }
        | _CANCEL_REASON_FIELDS,
    )
    authorize_account_submit_transition(doc, action)


def _c_level_recipients(doc: Document) -> tuple[str, ...]:
    from connect_diagnostics_core.api.erpnext.stock_count_session import session_has_permission

    assignments = frappe.get_all(
        "Has Role", {"role": "C-Level Approver", "parenttype": "User"}, pluck="parent"
    )
    users = (
        frappe.db.get_values(
            "User",
            {"name": ("in", sorted(set(assignments))), "enabled": 1},
            "name",
            pluck=True,
            order_by="name",
        )
        if assignments
        else []
    )
    recipients = tuple(str(user) for user in users if session_has_permission(doc, "read", str(user)))
    if not recipients:
        frappe.throw(_("Count variance requires an enabled, in-scope C-Level recipient."))
    return recipients


def _send_variance_alerts(doc: Document, recipients: tuple[str, ...]) -> None:
    for user in recipients:
        key = sha256(f"{doc.name}/{doc.get('evidence_revision')}/{user}".encode()).hexdigest()
        if frappe.db.exists("Stock Count Notification Receipt", {"dedupe_key": key}):
            frappe.throw(_("Count variance notification was already delivered for this revision."))
        log = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "type": "Alert",
                    "for_user": user,
                    "from_user": str(frappe.session.user),
                    "document_type": "Stock Count Session",
                    "document_name": doc.name,
                    "subject": f"Stock count variance: {doc.name}",
                    "email_content": f"Stock Count Session {doc.name} revision {doc.get('evidence_revision')} has a reviewed stock difference.",
                }
            ),
        )
        log.insert(ignore_permissions=True)
        receipt = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Stock Count Notification Receipt",
                    "dedupe_key": key,
                    "session": doc.name,
                    "evidence_revision": doc.get("evidence_revision"),
                    "recipient_user": user,
                    "notification_log": log.name,
                    "created_at": now(),
                }
            ),
        )
        _insert_count_evidence(receipt)


def close_count(doc: Document) -> None:
    """Post native corrections, verify effects, alert C-Level and close atomically."""
    _lock_session(doc, {"Approved"})
    user, _employee = _actor(doc, "Stock Manager")
    if user != doc.get("checker_user") or doc.get("workflow_state") != "Closed":
        frappe.throw(_("Only the independent Count checker may close an approved Session."))
    if doc.get("evidence_invalidated") or _evidence_digest(doc) != doc.get("approved_digest"):
        frappe.throw(_("Count evidence changed after approval; restart the full revision."))
    has_variance = _verify_complete(doc)
    if has_variance != bool(doc.get("has_variance")):
        frappe.throw(_("Count variance changed after approval."))
    required, settings_digest = _accounting_settings(doc)
    candidates = _prepared_candidates(doc)
    if (
        required != bool(doc.get("accounting_review_required"))
        or settings_digest != doc.get("accounting_settings_digest")
        or (required and doc.get("accounting_reviewed_digest") != doc.get("accounting_candidate_digest"))
        or _candidate_digest(doc, candidates) != doc.get("accounting_candidate_digest")
    ):
        frappe.throw(_("Count accounting approval is missing or current settings changed."))
    _current_baseline_is_unchanged(doc)
    recipients = _c_level_recipients(doc) if has_variance else ()
    effects = _correction_rows(doc) if has_variance else {}
    action = frappe.db.get_value(_PARENT, doc.name, "workflow_state", for_update=True, wait=False)
    if (
        action != "Approved"
        or bool(candidates) != bool(effects)
        or (has_variance and not effects)
        or (not has_variance and effects)
    ):
        frappe.throw(_("Count close action does not match current approved variance."))
    approved_projection = _candidate_projection(doc, candidates)
    digest = sha256(
        json.dumps(approved_projection, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != doc.get("accounting_candidate_digest"):
        frappe.throw(_("Native Count candidate inputs changed before posting; renew approval."))
    by_name = {str(row["name"]): row for row in approved_projection["entries"]}
    for entry in candidates:
        approved_entry = by_name.get(str(entry.name))
        if approved_entry is None:
            frappe.throw(_("Approved Count candidate disappeared before native submit."))
        assert approved_entry is not None
        posting_stamp = _count_effective_timestamp(doc)
        if _candidate_posting_stamp(entry) != posting_stamp:
            frappe.throw(_("Count correction posting timestamp differs from the frozen scope cutoff."))
        entry = _submit_prepared_candidate(doc, entry, posting_stamp, approved_entry)
    stamp = _count_effective_timestamp(doc)
    if has_variance:
        _verify_final_location_balances(doc)
    if has_variance:
        _send_variance_alerts(doc, recipients)
    doc.set("cancel_accounting_required", int(_cancellation_gl_source(doc)[0]))
    doc.set("posting_policy", _COUNT_POSTING_POLICY)
    doc.set("posting_date", stamp.date())
    doc.set("posting_time", stamp.time())
    doc.set("posted_at", stamp)
    doc.set("closed_at", now())
    for scope_row in doc.get("scope") or []:
        scope_row.freeze_active = 0
        scope_row.lease_state = "Released"
        scope_row.released_at = doc.get("closed_at")
    _authorize_transition_save(
        doc,
        {
            "workflow_state",
            "posting_policy",
            "posting_date",
            "posting_time",
            "posted_at",
            "closed_at",
            "scope",
            "cancel_accounting_required",
        },
    )
    frappe.local._stock_count_session_transition_proof = {
        "document": doc,
        "phase": "submit",
        "consumed": False,
    }


def cancel_closed_count(doc: Document) -> None:
    """Native Closed → Cancelled action reverses every linked correction in one transaction."""
    _lock_session(doc, {"Closed", "Cancellation Approved"})
    _actor(doc, "Stock Manager")
    if doc.get("workflow_state") != "Cancelled" or doc.docstatus != 1:
        frappe.throw(_("Only a submitted Closed Count may use the native Cancel action."))
    source = frappe.db.get_value(_PARENT, doc.name, "workflow_state", for_update=True, wait=False)
    has_gl, digest, names = _cancellation_gl_source(doc)
    if source == "Closed" and has_gl:
        frappe.throw(_("Count correction GL requires independent cancellation accounting approval."))
    if source == "Cancellation Approved" and (
        not has_gl
        or digest != doc.get("cancel_gl_digest")
        or digest != doc.get("cancel_accounts_digest")
        or not doc.get("cancel_accounts_user")
        or doc.get("cancel_accounts_user")
        in {
            doc.get("cancel_request_user"),
            doc.get("maker_user"),
            doc.get("checker_user"),
            doc.get("stock_approver_user"),
        }
    ):
        frappe.throw(_("Count cancellation Accounts approval is stale or incomplete."))
    from frappe.model.workflow import apply_workflow

    for name in reversed(names):
        entry = cast(Document, frappe.get_doc("Stock Entry", name, for_update=True))
        proof = {
            "document": entry,
            "session": doc.name,
            "revision": int(doc.get("evidence_revision") or 0),
            "digest": str(doc.get("approved_digest") or ""),
            "phase": "before_cancel",
            "actor": str(frappe.session.user or ""),
            "candidate_digest": str(doc.get("accounting_candidate_digest") or ""),
            "cancel_gl_digest": digest,
            "guarded": False,
            "consumed": False,
            "items": _count_effect_item_links(entry),
        }
        previous = getattr(frappe.local, "_stock_count_effect_proof", None)
        frappe.local._stock_count_effect_proof = proof
        try:
            entry = cast(Document, apply_workflow(entry, "Cancel Stock Entry"))
            if proof["consumed"] or not proof["guarded"] or entry.docstatus != 2:
                frappe.throw(_("Native Count correction did not complete its protected cancellation."))
            _verify_native_cancellation(entry)
            proof["consumed"] = True
        finally:
            frappe.local._stock_count_effect_proof = previous
    doc.set("cancelled_at", now())
    _authorize_transition_save(doc, {"workflow_state", "cancelled_at"})
    frappe.local._stock_count_session_transition_proof = {
        "document": doc,
        "phase": "cancel",
        "consumed": False,
    }
