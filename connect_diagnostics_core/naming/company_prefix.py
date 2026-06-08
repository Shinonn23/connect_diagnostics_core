# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

ALLOWED_DOCTYPES = {
    "Sales Invoice",
    "Purchase Invoice",
    "Sales Order",
    "Purchase Order",
    "Delivery Note",
    "Purchase Receipt",
    "Payment Entry",
    "Journal Entry",
    "Stock Entry",
    "Material Request",
}


def apply_company_abbr_prefix(doc: Any, method: str | None = None) -> None:
    if not should_apply_company_prefix(doc):
        return

    abbr = frappe.db.get_value("Company", doc.company, "abbr")
    if not abbr:
        return

    prefix = f"{abbr}-"

    if doc.naming_series.startswith(prefix):
        return

    doc.naming_series = f"{prefix}{doc.naming_series}"


def should_apply_company_prefix(doc: Any) -> bool:
    if doc.doctype not in ALLOWED_DOCTYPES:
        return False

    if not getattr(doc, "company", None):
        return False

    if not getattr(doc, "naming_series", None):
        return False

    if getattr(doc, "name", None) and doc.name not in ("New", None):
        return False

    if getattr(doc.meta, "istable", False):
        return False

    return True
