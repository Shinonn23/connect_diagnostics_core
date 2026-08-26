# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Clear unposted ERPNext core TDS values before the Thai TDS guard is enabled.

Submitted documents with explicit TDS evidence stop the migration.  The patch
does not guess from ordinary GL entries: only Tax Withholding Entry rows,
``is_tax_withholding_account`` rows, or the core TDS GL remark are treated as
evidence that an old document needs accounting review.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

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
TDS_LEDGER_CHILDREN = {
    "Purchase Invoice": ("Purchase Taxes and Charges",),
    "Sales Invoice": ("Sales Taxes and Charges",),
    "Journal Entry": ("Journal Entry Account",),
}


def execute() -> None:
    candidates = _find_candidates()
    protected = [
        candidate
        for candidate in candidates
        if candidate.get("docstatus") == 1 and _has_ledger_evidence(candidate)
    ]
    if protected:
        _raise_for_protected_documents(protected)

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


def _has_ledger_evidence(candidate: dict[str, Any]) -> bool:
    doctype = str(candidate["doctype"])
    name = str(candidate["name"])

    if _has_submitted_tds_entry(doctype, name):
        return True
    for child_doctype in TDS_LEDGER_CHILDREN.get(doctype, ()):
        if frappe.db.exists("DocType", child_doctype) and frappe.db.exists(
            child_doctype,
            {
                "parent": name,
                "parenttype": doctype,
                "is_tax_withholding_account": 1,
            },
        ):
            return True
    return bool(
        frappe.get_all(
            "GL Entry",
            filters={
                "voucher_type": doctype,
                "voucher_no": name,
                "remarks": "TDS Deducted",
            },
            pluck="name",
            limit_page_length=1,
        )
    )


def _has_submitted_tds_entry(doctype: str, name: str) -> bool:
    if not frappe.db.exists("DocType", TDS_ENTRY_DOCTYPE):
        return False
    return bool(
        frappe.get_all(
            TDS_ENTRY_DOCTYPE,
            filters={
                "parent": name,
                "parenttype": doctype,
                "parentfield": TDS_ENTRY_FIELD,
            },
            pluck="name",
            limit_page_length=1,
        )
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


def _raise_for_protected_documents(protected: list[dict[str, Any]]) -> None:
    references = ", ".join(f"{row['doctype']}: {row['name']}" for row in protected[:20])
    if len(protected) > 20:
        references += f", and {len(protected) - 20} more"
    frappe.throw(
        _(
            "Migration stopped: submitted documents contain legacy ERPNext TDS evidence. "
            "Move them to Thai Withholding Tax Type before enabling the Thai Desk Guard. "
            "Documents: {0}"
        ).format(references),
        title=_("Legacy TDS data requires review"),
    )


def _is_set(value: object) -> bool:
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "0", "false", "no"}:
        return False
    return True
