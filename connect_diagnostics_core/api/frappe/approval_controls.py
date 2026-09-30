# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from math import isfinite
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


@dataclass(frozen=True)
class SignedApprovalSnapshot:
    user: str
    employee: str
    employee_name: str
    acted_at: datetime
    signature: str


@dataclass(frozen=True)
class _ApprovalGrant:
    doc: Document
    doctype: str
    name: str
    route: str
    action: str


_APPROVAL_GRANTS_KEY = "_connect_diagnostics_approval_field_grants"


def _approval_grants() -> list[_ApprovalGrant]:
    grants = getattr(frappe.local, _APPROVAL_GRANTS_KEY, None)
    if grants is None:
        grants = []
        setattr(frappe.local, _APPROVAL_GRANTS_KEY, grants)
    return grants


def require_interactive_actor(
    doc: Document,
    roles: Iterable[str],
    maker_identity: str,
    previous_identities: Iterable[str] = (),
    permission: str = "write",
) -> SignedApprovalSnapshot:
    """Validate and capture the live interactive business actor."""
    user = str(frappe.session.user or "")
    if user in {"", "Guest", "Administrator"} or getattr(frappe.local, "request", None) is None:
        _fail("Approval requires an interactive business User request.")
    allowed_roles = {role for role in roles if role}
    if not allowed_roles or not set(frappe.get_roles(user)).intersection(allowed_roles):
        _fail("You do not have the role required for this approval action.")
    return capture_signed_approval_actor(doc, maker_identity, previous_identities, permission)


def require_interactive_user(
    doc: Document,
    roles: Iterable[str],
    permission: str = "write",
) -> str:
    """Validate a current interactive User for a non-approval Workflow action."""
    user = str(frappe.session.user or "")
    if user in {"", "Guest", "Administrator"} or getattr(frappe.local, "request", None) is None:
        _fail("Workflow action requires an interactive business User request.")
    allowed_roles = {role for role in roles if role}
    if not allowed_roles or not set(frappe.get_roles(user)).intersection(allowed_roles):
        _fail("You do not have the role required for this Workflow action.")
    require_permission(doc, permission)
    return resolve_user(user)


def _mint_approval_field_grant(doc: Document, route: str, action: str) -> None:
    if not isinstance(doc, Document):
        _fail("Approval field grants require a document object.")
    if not route.strip() or not action.strip():
        _fail("Approval route and action are required.")
    grant = _ApprovalGrant(doc, doc.doctype, str(doc.name or ""), route, action)
    _approval_grants().append(grant)


def authorize_workflow_field_write(
    doc: Document,
    route: str,
    action: str,
    roles: Iterable[str],
    permission: str = "write",
) -> str:
    """Authorize one evidence write for a non-approval Workflow action."""
    user = require_interactive_user(doc, roles, permission)
    _mint_approval_field_grant(doc, route, action)
    return user


def authorize_approval_field_write(
    doc: Document,
    route: str,
    action: str,
    roles: Iterable[str],
    maker_identity: str,
    previous_identities: Iterable[str] = (),
    permission: str = "write",
) -> SignedApprovalSnapshot:
    """Capture a protected actor and mint one field-write grant for adapter validation."""
    snapshot = require_interactive_actor(
        doc,
        roles,
        maker_identity,
        previous_identities,
        permission,
    )
    _mint_approval_field_grant(doc, route, action)
    return snapshot


def consume_approval_field_grant(doc: Document, route: str, action: str) -> None:
    """Consume the exact grant; grants cannot cross documents, actions, or requests."""
    grants = _approval_grants()
    for index, grant in enumerate(grants):
        if (
            grant.doc is doc
            and grant.doctype == doc.doctype
            and grant.name == str(doc.name or "")
            and grant.route == route
            and grant.action == action
        ):
            grants.pop(index)
            if not grants:
                delattr(frappe.local, _APPROVAL_GRANTS_KEY)
            return
    _fail("Approval field write is not authorized for this transition.")


def _fail(message: str) -> None:
    frappe.throw(_(message))


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            _fail("Approval evidence contains a non-finite number.")
        return value
    if isinstance(value, (Decimal, date, datetime, time)):
        kind = type(value).__name__
        serialized = str(value) if isinstance(value, Decimal) else value.isoformat()
        return {"__approval_type__": kind, "value": serialized}
    if isinstance(value, Document):
        _fail("Approval evidence cannot contain a document.")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("Approval evidence mapping keys must be strings.")
            result[key] = _canonical_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        _fail("Approval evidence cannot contain a set.")
    _fail("Approval evidence contains an unsupported value.")


def critical_digest(payload: Mapping[str, Any]) -> str:
    """Return the deterministic digest for a server-built approval payload."""
    if not isinstance(payload, Mapping):
        _fail("Approval evidence must be a mapping.")
    canonical = _canonical_value(payload)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _enabled_user(name: str) -> bool:
    return bool(frappe.db.get_value("User", name, "enabled"))


def _employee_for_identity(identity: str) -> dict[str, Any] | None:
    row = frappe.db.get_value(
        "Employee",
        {"name": identity, "status": "Active"},
        ["name", "user_id"],
        as_dict=True,
    )
    return dict(row) if row else None


def _active_employees(user: str, *, limit: int = 2) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in frappe.get_all(
            "Employee",
            filters={"user_id": user, "status": "Active"},
            fields=["name", "employee_name", "user_id", "approval_signature"],
            limit=limit,
        )
    ]


def resolve_user(identity: str) -> str:
    """Resolve an enabled User or active linked Employee to its canonical User."""
    if not isinstance(identity, str) or not identity.strip():
        _fail("Approval identity is required.")
    identity = identity.strip()
    user_exists = bool(frappe.db.exists("User", identity))
    employee = _employee_for_identity(identity)
    raw_user_result = identity if user_exists else None
    user_result = identity if user_exists and _enabled_user(identity) else None
    employee_result = str(employee["user_id"]).strip() if employee and employee.get("user_id") else None
    if employee and not employee_result:
        _fail("Approval identity is not linked to a User.")
    if raw_user_result and employee_result and raw_user_result != employee_result:
        _fail("Approval identity resolves to different Users.")
    result = user_result or employee_result
    if not result:
        _fail("Approval identity is unresolved or disabled.")
    assert result is not None
    if not _enabled_user(result):
        _fail("Approval User is disabled.")
    if len(_active_employees(result)) > 1:
        _fail("Approval identity has multiple active Employees.")
    return result


def require_permission(doc: Document, permission: str) -> None:
    """Require the current session user to hold the requested document permission."""
    allowed = frappe.has_permission(doc.doctype, ptype=permission, doc=doc, user=frappe.session.user)
    if not allowed:
        raise frappe.PermissionError(_("You do not have permission to approve this document."))


def require_distinct_actors(
    maker_identity: str,
    actor_identity: str,
    previous_identities: Iterable[str],
) -> None:
    """Require maker, current actor, and prior protected actors to be distinct."""
    if not isinstance(maker_identity, str) or not maker_identity.strip():
        _fail("Maker identity is required.")
    if not isinstance(actor_identity, str) or not actor_identity.strip():
        _fail("Approval actor identity is required.")
    maker = resolve_user(maker_identity)
    actor = resolve_user(actor_identity)
    if maker == actor:
        _fail("The maker and approval actor must be different Users.")
    previous: list[str] = []
    for identity in previous_identities:
        if not isinstance(identity, str) or not identity.strip():
            _fail("Previous approval identities are required.")
        resolved = resolve_user(identity)
        if resolved in previous or resolved == maker:
            _fail("Approval actors must be distinct and cannot include the maker.")
        if resolved == actor:
            _fail("The approval actor has already acted on this document.")
        previous.append(resolved)


def capture_signed_approval_actor(
    doc: Document,
    maker_identity: str,
    previous_identities: Iterable[str] = (),
    permission: str = "write",
) -> SignedApprovalSnapshot:
    """Capture the current, distinct, signed Employee as immutable approval evidence."""
    require_permission(doc, permission)
    user = resolve_user(frappe.session.user)
    require_distinct_actors(maker_identity, user, previous_identities)
    employees = _active_employees(user)
    if len(employees) != 1:
        _fail("Approval requires exactly one active Employee.")
    employee = employees[0]
    signature = str(employee.get("approval_signature") or "")
    if not signature.strip():
        _fail("Approval requires a signed Employee.")
    return SignedApprovalSnapshot(
        user=user,
        employee=str(employee["name"]),
        employee_name=str(employee.get("employee_name") or ""),
        acted_at=frappe.utils.now_datetime(),
        signature=signature,
    )
