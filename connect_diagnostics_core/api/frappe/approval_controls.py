# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared separation-of-duties and approval digest controls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        frappe.throw(_("Approval values must contain only finite numbers."))
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _normalize_approval_value(value: Any) -> Any:
    """Normalize Frappe values without collapsing distinct business value types."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float, Decimal)):
        return {"$number": _canonical_decimal(Decimal(str(value)))}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat(timespec="microseconds")}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, time):
        return {"$time": value.isoformat(timespec="microseconds")}
    if isinstance(value, timedelta):
        microseconds = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
        return {"$time_microseconds": str(microseconds)}
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_approval_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_approval_value(item) for item in value]
    frappe.throw(_("Approval values contain an unsupported value type."))


def critical_digest(payload: Mapping[str, Any]) -> str:
    """Return a type-aware, representation-stable digest for an approval payload."""
    normalized = _normalize_approval_value(payload)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def require_distinct_actors(maker: str | None, actor: str | None, previous: Iterable[str] = ()) -> None:
    """Reject a workflow action when the actor is the maker or prior protected actor."""
    actor = resolve_user(actor or frappe.session.user)
    protected = {resolve_user(value) for value in previous if value and value.strip()}
    maker = resolve_user(maker) if maker else None
    if not actor or (maker and actor == maker) or actor in protected:
        frappe.throw(_("Approval actions must be performed by distinct users."))


def resolve_user(identity: str | None) -> str:
    """Resolve User or Employee identifiers to the canonical User identity."""
    value = (identity or "").strip()
    if not value:
        return ""
    if frappe.db.exists("User", value):
        return value
    return str(frappe.db.get_value("Employee", value, "user_id") or value)


def require_permission(doc: Document, permission: str = "write") -> None:
    """Fail closed when the current actor no longer has document permission."""
    if not frappe.has_permission(doc.doctype, ptype=permission, doc=doc):
        frappe.throw(
            _("You do not have permission to perform this approval action."),
            frappe.PermissionError,
        )
