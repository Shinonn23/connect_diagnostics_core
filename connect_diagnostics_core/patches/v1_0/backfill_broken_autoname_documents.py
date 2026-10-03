# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rename documents whose name kept the literal, unsubstituted {YY-BE}{MM-DOC}
tokens.

Frappe's braced-autoname regex (BRACED_PARAMS_PATTERN in frappe.model.naming)
never matches a "-" inside {...}, so every AUTONAME_PREFIXES DocType named via
`format:{prefix}{YY-BE}{MM-DOC}{####}` got the token text left in its name
instead of the resolved year/month (see setup/document_naming.py's
AUTONAME_YEAR_TOKEN/AUTONAME_DATE_TOKEN fix). This backfills existing documents
to the name they should have received, reusing the already-allocated sequence
digits and only recomputing the year/month tokens from each document's own
date.
"""

from __future__ import annotations

import re

import frappe

from connect_diagnostics_core.api.erpnext.employee import parse_buddhist_era_naming_series_variable
from connect_diagnostics_core.setup.document_naming import (
    AUTONAME_DATE_TOKEN,
    AUTONAME_PREFIXES,
    AUTONAME_YEAR_TOKEN,
    parse_document_month,
)

BROKEN_TOKEN_SUFFIX = "{YY-BE}{MM-DOC}"


def execute() -> None:
    renamed = 0
    for doctype, prefix in AUTONAME_PREFIXES.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        broken_names = frappe.get_all(
            doctype,
            filters=[["name", "like", f"{prefix}{BROKEN_TOKEN_SUFFIX}%"]],
            pluck="name",
        )
        for old_name in broken_names:
            if _rename_broken_document(doctype, prefix, old_name):
                renamed += 1
    frappe.db.commit()
    frappe.logger(__name__).info(f"backfill_broken_autoname_documents: renamed {renamed} document(s)")


def _rename_broken_document(doctype: str, prefix: str, old_name: str) -> bool:
    pattern = re.escape(f"{prefix}{BROKEN_TOKEN_SUFFIX}") + r"(\d+)$"
    match = re.match(pattern, old_name)
    if not match:
        return False

    digits = match.group(1)
    doc = frappe.get_doc(doctype, old_name)
    year_token = parse_buddhist_era_naming_series_variable(doc, AUTONAME_YEAR_TOKEN)
    month_token = parse_document_month(doc, AUTONAME_DATE_TOKEN)
    if not year_token or not month_token:
        frappe.log_error(
            title="backfill_broken_autoname_documents",
            message=f"Could not resolve naming tokens for {doctype} {old_name}",
        )
        return False

    new_name = f"{prefix}{year_token}{month_token}{digits}"
    if new_name == old_name or frappe.db.exists(doctype, new_name):
        return False

    frappe.rename_doc(doctype, old_name, new_name, force=True)
    return True
