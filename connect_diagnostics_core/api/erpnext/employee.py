# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

BUDDHIST_ERA_YEAR_OFFSET = 543
NATIONAL_ID_LENGTH = 13
_NON_DIGIT_RE = re.compile(r"\D")
_NATIONAL_ID_CHECKSUM_WEIGHTS = range(13, 1, -1)


def _get_series_date(doc: Any):
    if doc:
        from connect_diagnostics_core.setup.document_naming import _document_date

        return _document_date(doc)

    return getdate()


def parse_buddhist_era_naming_series_variable(doc: Any, variable: str) -> str | None:
    series_date = _get_series_date(doc)
    buddhist_year = series_date.year + BUDDHIST_ERA_YEAR_OFFSET

    if variable == "YYYY-BE":
        return str(buddhist_year)

    if variable in ("YY-BE", "YYBE"):
        return f"{buddhist_year % 100:02d}"

    return None


def clean_national_id(value: str) -> str:
    """Strip everything but digits from a national ID (e.g. dashes, spaces)."""
    return _NON_DIGIT_RE.sub("", value or "")


def format_national_id_display(digits: str) -> str:
    """Format a 13-digit Thai national ID as X-XXXX-XXXXX-XX-X."""
    return f"{digits[0]}-{digits[1:5]}-{digits[5:10]}-{digits[10:12]}-{digits[12]}"


def has_valid_national_id_checksum(digits: str) -> bool:
    """Verify a 13-digit Thai national ID's check digit (digit 13, mod-11 over digits 1-12)."""
    weighted_sum = sum(
        int(digit) * weight for digit, weight in zip(digits[:12], _NATIONAL_ID_CHECKSUM_WEIGHTS, strict=True)
    )
    check_digit = (11 - weighted_sum % 11) % 10
    return check_digit == int(digits[12])


def normalize_national_id(doc: Document, method: str | None = None) -> None:
    raw: str = cast(str, doc.get("national_id") or "")

    if not raw:
        doc.set("national_id_display", "")
        return

    cleaned = clean_national_id(raw)
    if len(cleaned) != NATIONAL_ID_LENGTH:
        frappe.throw(_("National ID must be a 13-digit number."))
    if not has_valid_national_id_checksum(cleaned):
        frappe.throw(_("National ID checksum is invalid."))

    doc.set("national_id", cleaned)
    doc.set("national_id_display", format_national_id_display(cleaned))
