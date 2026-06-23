from __future__ import annotations

import re
from typing import Any

import frappe
from frappe import _

_ABBR_RE = re.compile(r"^[A-Z]{2}$")


def validate(doc: Any, method: str | None = None) -> None:
    if not doc.abbr:
        return
    if not _ABBR_RE.match(doc.abbr):
        frappe.throw(_("Supplier Abbreviation must be exactly 2 uppercase letters (e.g. AD, ZY)."))
