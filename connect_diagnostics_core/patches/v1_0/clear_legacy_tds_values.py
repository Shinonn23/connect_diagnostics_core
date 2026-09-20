# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Force-clear ERPNext core TDS values before the Thai TDS guard is enabled.

This patch intentionally clears legacy TDS values from all matching documents,
including submitted documents.  It does not migrate the old TDS evidence to a
Thai Withholding Tax Type.
"""

from __future__ import annotations

from typing import Any

import frappe

from connect_diagnostics_core.setup.tds import TDS_FIELDS, TDS_LAYOUT_FIELDS

SCANNED_DOCTYPES = (
    "Customer",
    "Supplier",
    "Purchase Invoice",
    "Sales Invoice",
    "Payment Entry",
    "Journal Entry",
    "Item",
    "Lower Deduction Certificate",
)
TDS_ENTRY_DOCTYPE = "Tax Withholding Entry"
TDS_ENTRY_FIELD = "tax_withholding_entries"


def execute() -> None:
    candidates = _find_candidates()
    submitted_count = sum(candidate.get("docstatus") == 1 for candidate in candidates)
    if submitted_count:
        frappe.logger(__name__).warning(
            "Force-clearing legacy core TDS values from %s submitted document(s).",
            submitted_count,
        )

    cleared = 0
    for candidate in candidates:
        _clear_candidate(candidate)
        cleared += 1

    frappe.logger(__name__).info("Cleared legacy core TDS values from %s document(s).", cleared)
    frappe.db.commit()


def _find_candidates() -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for doctype in SCANNED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        fields = [
            fieldname
            for fieldname in TDS_FIELDS.get(doctype, ())
            if (
                fieldname not in TDS_LAYOUT_FIELDS
                and fieldname != "tax_withholding_entries"
                and meta.has_field(fieldname)
            )
        ]
        if fields:
            rows = frappe.get_all(
                doctype,
                or_filters=[[fieldname, "is", "set"] for fieldname in fields],
                fields=["name", "docstatus", *fields],
                limit_page_length=0,
            )
            for row in rows:
                candidate = dict(row)
                candidate["doctype"] = doctype
                candidates[(doctype, str(row["name"]))] = candidate

        for name in _get_tds_entry_parents(doctype):
            if (doctype, name) in candidates:
                continue
            values = frappe.db.get_value(doctype, name, ["name", "docstatus", *fields], as_dict=True)
            if values:
                candidate = dict(values)
                candidate["doctype"] = doctype
                candidates[(doctype, name)] = candidate
    return list(candidates.values())


def _get_tds_entry_parents(doctype: str) -> list[str]:
    if not frappe.db.exists("DocType", TDS_ENTRY_DOCTYPE):
        return []
    return frappe.get_all(
        TDS_ENTRY_DOCTYPE,
        filters={"parenttype": doctype, "parentfield": TDS_ENTRY_FIELD},
        pluck="parent",
        limit_page_length=0,
    )


def _clear_candidate(candidate: dict[str, Any]) -> None:
    doctype = str(candidate["doctype"])
    name = str(candidate["name"])
    meta = frappe.get_meta(doctype)
    for fieldname in TDS_FIELDS.get(doctype, ()):
        if fieldname == "tax_withholding_entries" or fieldname not in candidate:
            continue
        if not meta.has_field(fieldname) or not _is_set(candidate.get(fieldname)):
            continue
        frappe.db.set_value(
            doctype,
            name,
            fieldname,
            0 if meta.get_field(fieldname).fieldtype == "Check" else "",
            update_modified=False,
        )

    if frappe.db.exists("DocType", TDS_ENTRY_DOCTYPE):
        frappe.db.delete(
            TDS_ENTRY_DOCTYPE,
            {"parent": name, "parenttype": doctype, "parentfield": TDS_ENTRY_FIELD},
        )


def _is_set(value: object) -> bool:
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "0", "false", "no"}:
        return False
    return True
