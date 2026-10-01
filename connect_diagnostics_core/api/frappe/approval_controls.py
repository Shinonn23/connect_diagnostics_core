# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared separation-of-duties and approval digest controls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


def critical_digest(payload: Mapping[str, Any]) -> str:
    """Return a stable digest for a server-built approval payload."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def resolve_user(identity: str | None) -> str:
    value = (identity or "").strip()
    if not value:
        return ""
    if frappe.db.exists("User", value):
        return value
    return str(frappe.db.get_value("Employee", value, "user_id") or value)


def require_distinct_actors(maker: str | None, actor: str | None, previous: Iterable[str] = ()) -> None:
    actor = resolve_user(actor or frappe.session.user)
    maker = resolve_user(maker)
    protected = {resolve_user(value) for value in previous if value and value.strip()}
    if not actor or actor == maker or actor in protected:
        frappe.throw(_("Approval actions must be performed by distinct users."))


def require_permission(doc: Document, permission: str = "write") -> None:
    if not frappe.has_permission(doc.doctype, ptype=permission, doc=doc):
        frappe.throw(_("You do not have permission to perform this approval action."), frappe.PermissionError)
