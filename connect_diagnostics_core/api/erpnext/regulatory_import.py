# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Read-only preflight validation for standard Frappe Data Import regulatory rows."""

from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe import _

from connect_diagnostics_core.api.erpnext.regulatory import normalize_registration_number


@frappe.whitelist()
def validate_regulatory_import_rows(rows_json: str) -> dict[str, Any]:
    """Validate imported registration/header rows without writing master data."""
    if not frappe.has_permission("Medical Device Product Registration", "create"):
        frappe.throw(_("Not permitted to validate regulatory imports."), frappe.PermissionError)
    rows = cast(list[dict[str, Any]], json.loads(rows_json))
    seen: dict[str, int] = {}
    errors: list[dict[str, str | int]] = []
    for index, row in enumerate(rows, start=1):
        registration_number = cast(str, row.get("registration_number") or "").strip()
        if not registration_number:
            errors.append({"row": index, "field": "registration_number", "message": "Registration Number is required."})
            continue
        normalized = normalize_registration_number(registration_number)
        if not normalized:
            errors.append({"row": index, "field": "registration_number", "message": "Registration Number has no searchable characters."})
            continue
        if normalized in seen:
            errors.append(
                {"row": index, "field": "registration_number", "message": f"Duplicates row {seen[normalized]} after normalization."}
            )
        seen[normalized] = index
    return {"data": {"valid": not errors, "errors": errors}, "message": _("Regulatory import preflight completed.")}
