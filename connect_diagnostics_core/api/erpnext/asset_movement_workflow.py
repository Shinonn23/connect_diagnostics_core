# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe import approval_controls

_CAPABILITY_STACK = "_connect_diagnostics_asset_movement_capabilities"
_SUBMIT_TRANSITION_MARKER = object()
_CANCEL_TRANSITION_MARKER = object()
_SUBMIT_MARKER_FIELD = "_connect_diagnostics_asset_movement_submit_transition"
_CANCEL_MARKER_FIELD = "_connect_diagnostics_asset_movement_cancel_transition"

STATE_DRAFT = "Asset Movement Draft"
STATE_PENDING_REVIEW = "Asset Movement Pending Review"
STATE_PENDING_APPROVAL = "Asset Movement Pending Approval"
STATE_APPROVED = "Asset Movement Approved"
STATE_SUBMITTED = "Asset Movement Submitted"
STATE_REJECTED = "Asset Movement Rejected"
STATE_CANCELLED = "Asset Movement Cancelled"
MAKER_ROLE = "Stock User"
REVIEWER_ROLE = "Stock Manager"
APPROVER_ROLE = "C-Level Approver"

_CRITICAL_FIELDS = (
    "asset",
    "company",
    "purpose",
    "transaction_date",
    "reference_doctype",
    "reference_name",
    "material_request",
    "assets",
)
_CRITICAL_ROW_FIELDS = (
    "asset",
    "company",
    "source_location",
    "target_location",
    "from_employee",
    "to_employee",
)


@dataclass
class _NativeCapability:
    asset_name: str
    kind: str
    consumed: bool = False


def _capability_stack() -> list[_NativeCapability]:
    stack = getattr(frappe.local, _CAPABILITY_STACK, None)
    if stack is None:
        stack = []
        setattr(frappe.local, _CAPABILITY_STACK, stack)
    return stack


@contextmanager
def native_asset_movement_capability(asset_name: str, kind: str) -> Iterator[None]:
    """Scope an opaque capability to a synchronous native Asset operation."""
    capability = _NativeCapability(asset_name=asset_name, kind=kind)
    stack = _capability_stack()
    stack.append(capability)
    try:
        yield None
    finally:
        for index, current in enumerate(stack):
            if current is capability:
                stack.pop(index)
                break
        if not stack and hasattr(frappe.local, _CAPABILITY_STACK):
            delattr(frappe.local, _CAPABILITY_STACK)


def _top_capability(kind: str) -> _NativeCapability | None:
    stack = getattr(frappe.local, _CAPABILITY_STACK, None)
    if not stack:
        return None
    capability = stack[-1]
    return capability if capability.kind == kind else None


def _asset_value(asset: Any, fieldname: str) -> Any:
    if hasattr(asset, "get"):
        return asset.get(fieldname)
    return getattr(asset, fieldname, None)


def _movement_value(movement: Any, fieldname: str) -> Any:
    if hasattr(movement, "get"):
        return movement.get(fieldname)
    return getattr(movement, fieldname, None)


def _row_value(row: Any, fieldname: str) -> Any:
    if hasattr(row, "get"):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def _movement_assets(movement: Any) -> list[Any]:
    rows = _movement_value(movement, "assets")
    return list(rows or [])


def validate_native_asset_receipt(movement: Any, asset: Any) -> None:
    """Validate and consume the capability for ERPNext's native Receipt movement."""
    capability = _top_capability("submit")
    if capability is None or capability.consumed:
        frappe.throw(_("Only the native Asset submit operation may create this Receipt movement."))
    assert capability is not None
    asset_name = _asset_value(asset, "name")
    if capability.asset_name != asset_name:
        frappe.throw(_("The native Receipt movement does not match its Asset."))
    rows = _movement_assets(movement)
    if len(rows) != 1 or _row_value(rows[0], "asset") != asset_name:
        frappe.throw(_("The native Asset Receipt must contain exactly one matching Asset row."))
    row = rows[0]
    expected_reference_doctype = (
        "Purchase Receipt" if _asset_value(asset, "purchase_receipt") else "Purchase Invoice"
    )
    expected_reference_name = _asset_value(asset, "purchase_receipt") or _asset_value(
        asset, "purchase_invoice"
    )
    expected = {
        "company": _asset_value(asset, "company"),
        "purpose": "Receipt",
        "reference_doctype": expected_reference_doctype,
        "reference_name": expected_reference_name,
    }
    actual = {
        "company": _movement_value(movement, "company"),
        "purpose": _movement_value(movement, "purpose"),
        "reference_doctype": _movement_value(movement, "reference_doctype"),
        "reference_name": _movement_value(movement, "reference_name"),
    }
    if actual != expected or _row_value(row, "target_location") != _asset_value(asset, "location"):
        frappe.throw(_("The native Asset Receipt shape is invalid."))
    if _row_value(row, "to_employee") != _asset_value(asset, "custodian"):
        frappe.throw(_("The native Asset Receipt custodian is invalid."))
    capability.consumed = True


def validate_native_asset_cancel(movement: Any, asset_name: str) -> None:
    """Ensure a native cancellation is scoped to the Asset being cancelled."""
    capability = _top_capability("cancel")
    if capability is None or capability.asset_name != asset_name:
        frappe.throw(_("Only the native Asset cancellation operation may cancel this movement."))
    assert capability is not None
    if not any(_row_value(row, "asset") == asset_name for row in _movement_assets(movement)):
        frappe.throw(_("The native Asset cancellation does not contain its Asset."))


def lock_asset_rows(asset_names: Sequence[str]) -> tuple[str, ...]:
    """Lock distinct Assets in deterministic order for a transaction boundary."""
    ordered_names = tuple(sorted({name for name in asset_names if name}))
    for asset_name in ordered_names:
        frappe.db.get_value("Asset", asset_name, "name", for_update=True)
    return ordered_names


def _roles(user: str | None = None) -> set[str]:
    return set(frappe.get_roles(user or frappe.session.user))


def _require_role(role: str) -> None:
    if role not in _roles():
        frappe.throw(_("The current user must have the {0} role.").format(role))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _set_value(doc: Any, fieldname: str, value: Any) -> None:
    setter = getattr(doc, "set", None)
    if callable(setter):
        setter(fieldname, value)
    else:
        doc[fieldname] = value


def authorize_submit_transition(doc: Document) -> None:
    """Authorize one native Workflow Submit transition by object identity."""
    setattr(doc, _SUBMIT_MARKER_FIELD, _SUBMIT_TRANSITION_MARKER)


def authorize_cancel_transition(doc: Document) -> None:
    """Authorize one native Workflow Cancel transition by object identity."""
    setattr(doc, _CANCEL_MARKER_FIELD, _CANCEL_TRANSITION_MARKER)


def _consume_transition_marker(doc: Document, fieldname: str, marker: object) -> None:
    if getattr(doc, fieldname, None) is not marker:
        frappe.throw(_("Asset Movement must use the approved native workflow transition."))
    setattr(doc, fieldname, None)


def _critical_row(row: Any) -> tuple[Any, ...]:
    return tuple(_row_value(row, field) for field in _CRITICAL_ROW_FIELDS)


def critical_payload(doc: Document) -> dict[str, Any]:
    """Build approval evidence from server-read fields and ordered custody rows."""
    payload: dict[str, Any] = {field: doc.get(field) for field in _CRITICAL_FIELDS if field != "assets"}
    payload["assets"] = [_critical_row(row) for row in _movement_assets(doc)]
    return payload


def critical_digest(doc: Document) -> str:
    return approval_controls.critical_digest(critical_payload(doc))


def _set_snapshot(doc: Document, prefix: str, snapshot: approval_controls.SignedApprovalSnapshot) -> None:
    _set_value(doc, f"{prefix}_by", snapshot.employee)
    _set_value(doc, f"{prefix}_at", snapshot.acted_at)
    _set_value(doc, f"{prefix}_signature", snapshot.signature)


def capture_maker(doc: Document) -> None:
    """Record the server-resolved maker when the document enters review."""
    _require_role(MAKER_ROLE)
    reset_approval(doc)
    maker = approval_controls.resolve_user(frappe.session.user)
    _set_value(doc, "approval_maker_user", maker)
    _set_value(doc, "approval_critical_digest", critical_digest(doc))


def capture_review(doc: Document) -> None:
    _require_role(REVIEWER_ROLE)
    maker = _text(doc.get("approval_maker_user"))
    if not maker:
        frappe.throw(_("Asset Movement must have a maker before review."))
    snapshot = approval_controls.capture_signed_approval_actor(doc, maker)
    _set_snapshot(doc, "checked", snapshot)
    _set_value(doc, "approval_reviewer_user", snapshot.user)
    _set_value(doc, "approval_critical_digest", critical_digest(doc))


def capture_approval(doc: Document) -> None:
    _require_role(APPROVER_ROLE)
    maker = _text(doc.get("approval_maker_user"))
    reviewer = _text(doc.get("approval_reviewer_user"))
    if not maker or not reviewer:
        frappe.throw(_("Asset Movement must have maker and reviewer evidence before approval."))
    snapshot = approval_controls.capture_signed_approval_actor(doc, maker, (reviewer,))
    _set_snapshot(doc, "authorized", snapshot)
    _set_value(doc, "approval_approver_user", snapshot.user)


def reset_approval(doc: Document) -> None:
    for field in (
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_approver_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        _set_value(doc, field, None)


def _persisted_state(doc: Document) -> dict[str, Any] | None:
    fields = [
        "workflow_state",
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_approver_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ]
    row = frappe.db.get_value(doc.doctype, doc.name, fields, as_dict=True, for_update=True)
    return dict(row) if row else None


def _require_snapshot(doc: Document | dict[str, Any], prefix: str, user: str) -> None:
    values = [doc.get(f"{prefix}_by"), doc.get(f"{prefix}_at"), doc.get(f"{prefix}_signature")]
    if not all(values):
        frappe.throw(_("Asset Movement approval evidence is incomplete."))
    employee_user = frappe.db.get_value("Employee", values[0], "user_id")
    if not employee_user or approval_controls.resolve_user(str(employee_user)) != user:
        frappe.throw(_("Asset Movement approval evidence does not match its actor."))


def validate_critical_unchanged(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if previous and previous.get("workflow_state") in {
        STATE_PENDING_REVIEW,
        STATE_PENDING_APPROVAL,
        STATE_APPROVED,
    }:
        if critical_digest(previous) != critical_digest(doc):
            frappe.throw(_("Approval-critical Asset Movement fields cannot change after review."))


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    validate_critical_unchanged(doc)
    state = _text(doc.get("workflow_state"))
    if state in {STATE_PENDING_REVIEW, STATE_PENDING_APPROVAL, STATE_APPROVED}:
        if not _text(doc.get("approval_maker_user")) or not _text(doc.get("approval_critical_digest")):
            frappe.throw(_("Asset Movement approval evidence is incomplete."))
        if doc.get("approval_critical_digest") != critical_digest(doc):
            frappe.throw(_("Asset Movement approval evidence is stale."))
        if state in {STATE_PENDING_APPROVAL, STATE_APPROVED}:
            reviewer = _text(doc.get("approval_reviewer_user"))
            if not reviewer:
                frappe.throw(_("Asset Movement review evidence is incomplete."))
            _require_snapshot(doc, "checked", reviewer)
        if state == STATE_APPROVED:
            approver = _text(doc.get("approval_approver_user"))
            if not approver:
                frappe.throw(_("Asset Movement approval evidence is incomplete."))
            _require_snapshot(doc, "authorized", approver)
            approval_controls.require_distinct_actors(
                _text(doc.get("approval_maker_user")), approver, (_text(doc.get("approval_reviewer_user")),)
            )


def lock_assets_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    if getattr(doc, "_action", None) == "submit":
        lock_asset_rows([_row_value(row, "asset") for row in _movement_assets(doc)])


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    capability = _top_capability("submit")
    if capability is not None:
        asset = frappe.get_doc("Asset", capability.asset_name)
        validate_native_asset_receipt(doc, asset)
        _set_value(doc, "workflow_state", STATE_SUBMITTED)
        return
    if doc.get("workflow_state") != STATE_SUBMITTED:
        frappe.throw(_("Asset Movement must be approved before submission."))
    _consume_transition_marker(doc, _SUBMIT_MARKER_FIELD, _SUBMIT_TRANSITION_MARKER)
    _require_role(REVIEWER_ROLE)
    approval_controls.require_permission(doc, "submit")
    persisted = _persisted_state(doc)
    if not persisted or persisted.get("workflow_state") != STATE_APPROVED:
        frappe.throw(_("Asset Movement approval is not current."))
    assert persisted is not None
    if persisted.get("approval_critical_digest") != critical_digest(doc):
        frappe.throw(_("Asset Movement approval is stale and requires re-approval."))
    maker = _text(persisted.get("approval_maker_user"))
    reviewer = _text(persisted.get("approval_reviewer_user"))
    approver = _text(persisted.get("approval_approver_user"))
    if not maker or not reviewer or not approver:
        frappe.throw(_("Asset Movement approval actors are incomplete."))
    _require_snapshot(persisted, "checked", reviewer)
    _require_snapshot(persisted, "authorized", approver)
    approval_controls.require_distinct_actors(maker, approver, (reviewer,))


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    capability = _top_capability("cancel")
    if capability is not None:
        validate_native_asset_cancel(doc, capability.asset_name)
        lock_asset_rows([_row_value(row, "asset") for row in _movement_assets(doc)])
        _set_value(doc, "workflow_state", STATE_CANCELLED)
        return
    if doc.get("workflow_state") != STATE_CANCELLED:
        frappe.throw(_("Asset Movement cancellation must use the approved workflow transition."))
    _consume_transition_marker(doc, _CANCEL_MARKER_FIELD, _CANCEL_TRANSITION_MARKER)
    _require_role(REVIEWER_ROLE)
    approval_controls.require_permission(doc, "cancel")
    persisted = _persisted_state(doc)
    if not persisted or persisted.get("workflow_state") != STATE_SUBMITTED:
        frappe.throw(_("Asset Movement cancellation is not current."))


class AssetMovementNativeMixin:
    """Inactive extension preserving ERPNext's native Asset movement lifecycle."""

    def make_asset_movement(self: Document) -> Any:
        asset_name = str(self.get("name"))
        with native_asset_movement_capability(asset_name, "submit"):
            return cast(Any, super()).make_asset_movement()  # ty: ignore[invalid-super-argument] - Frappe injects the runtime controller superclass

    def cancel_movement_entries(self: Document) -> Any:
        asset_name = str(self.get("name"))
        with native_asset_movement_capability(asset_name, "cancel"):
            return cast(Any, super()).cancel_movement_entries()  # ty: ignore[invalid-super-argument] - Frappe injects the runtime controller superclass


class AssetMovementWorkflowMixin:
    """Preserve core Workflow validation except inside an authenticated native Asset operation."""

    def validate_workflow(self: Document) -> Any:
        action = getattr(self, "_action", None)
        if action == "submit" and _top_capability("submit") is not None:
            self.set("workflow_state", STATE_SUBMITTED)
            return None
        if action == "cancel" and _top_capability("cancel") is not None:
            self.set("workflow_state", STATE_CANCELLED)
            return None
        return cast(Any, super()).validate_workflow()  # ty: ignore[invalid-super-argument] - Frappe injects the runtime controller superclass
