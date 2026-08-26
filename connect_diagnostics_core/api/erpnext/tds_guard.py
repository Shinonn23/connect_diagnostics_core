# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side guard for ERPNext's core TDS fields and masters."""

from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.setup.tds import (
    TDS_FIELDS,
    TDS_LAYOUT_FIELDS,
    get_disabled_message,
)

SETUP_FLAGS = ("in_patch", "in_install", "in_migrate")
TDS_CHILD_CATEGORY_FIELDS = frozenset({"tax_withholding_category"})


def block_tds(doc: Document, method: str) -> None:
    """Reject TDS values on normal saves, API requests, and data imports."""
    del method
    if _is_setup_context() or _is_administrator():
        return
    if not _has_tds_value(doc):
        return
    frappe.throw(get_disabled_message(), title=_("Tax withholding is disabled"))


def block_doctype(doc: Document, method: str) -> None:
    """Prevent creation or modification of core TDS masters."""
    del method
    if _is_setup_context():
        return
    frappe.throw(get_disabled_message(), title=_("Tax withholding is disabled"))


def _has_tds_value(doc: Document) -> bool:
    fieldnames = TDS_FIELDS.get(doc.doctype, ())
    for fieldname in fieldnames:
        if fieldname in TDS_LAYOUT_FIELDS:
            continue
        if _is_set(doc.get(fieldname)):
            # Invoice Item.apply_tds defaults to 1 and is read-only in ERPNext
            # v16. Its value alone must not break ordinary invoice creation.
            if doc.doctype in {"Purchase Invoice Item", "Sales Invoice Item"} and fieldname == "apply_tds":
                continue
            return True

    for row in _iter_child_rows(doc):
        if any(_is_set(row.get(fieldname)) for fieldname in TDS_CHILD_CATEGORY_FIELDS):
            return True
    return False


def _iter_child_rows(doc: Document) -> Iterable[Document]:
    for fieldname in ("items", "taxes", "accounts"):
        rows = doc.get(fieldname) or []
        for row in rows:
            if isinstance(row, Document):
                yield row
            elif isinstance(row, dict):
                yield frappe._dict(row)


def _is_set(value: object) -> bool:
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "0", "false", "no"}:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _is_setup_context() -> bool:
    return any(bool(getattr(frappe.flags, flag, False)) for flag in SETUP_FLAGS)


def _is_administrator() -> bool:
    return frappe.session.user == "Administrator"
