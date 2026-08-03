# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

BUDDHIST_ERA_YEAR_OFFSET = 543
IDENTITY_FIELDS = {
    "national_id": "National ID",
    "tax_id": "Tax ID",
}
THAI_IDENTITY_NUMBER_PATTERN = re.compile(r"^[0-9]{13}$")


def _get_series_date(doc: Any) -> date:
    if doc:
        for fieldname in ("posting_date", "transaction_date", "date", "date_of_joining"):
            value = doc.get(fieldname) if hasattr(doc, "get") else getattr(doc, fieldname, None)
            if value:
                return cast(date, getdate(value))

    return cast(date, getdate())


def parse_buddhist_era_naming_series_variable(doc: Any, variable: str) -> str | None:
    series_date = _get_series_date(doc)
    buddhist_year = series_date.year + BUDDHIST_ERA_YEAR_OFFSET

    if variable == "YYYY-BE":
        return str(buddhist_year)

    if variable == "YY-BE":
        return f"{buddhist_year % 100:02d}"

    return None


def normalize_thai_identity_number(value: object) -> str:
    """Canonicalize decimal digits and remove accepted identity separators."""
    without_separators = re.sub(r"[-\s]", "", str(value or ""))
    return "".join(
        str(unicodedata.decimal(character)) if character.isdecimal() else character
        for character in without_separators
    )


def is_valid_thai_identity_number(value: object) -> bool:
    normalized_value = normalize_thai_identity_number(value)
    if not THAI_IDENTITY_NUMBER_PATTERN.fullmatch(normalized_value):
        return False

    checksum_total = sum(int(digit) * (13 - index) for index, digit in enumerate(normalized_value[:12]))
    check_digit = (11 - (checksum_total % 11)) % 10
    return check_digit == int(normalized_value[-1])


def validate_employee_identity(doc: Document, method: str) -> None:
    """Normalize and protect Thai employee identity values."""
    del method

    previous_doc = doc.get_doc_before_save()
    changed_identity_fields = [
        fieldname
        for fieldname in IDENTITY_FIELDS
        if doc.has_value_changed(fieldname)
        and (doc.get(fieldname) or (previous_doc and previous_doc.get(fieldname)))
    ]
    if changed_identity_fields and not frappe.has_permission("Employee", "mask", doc=doc):
        frappe.throw(
            _("Mask permission is required to set or clear employee identity numbers."),
            frappe.PermissionError,
        )

    for fieldname, label in IDENTITY_FIELDS.items():
        normalized_value = normalize_thai_identity_number(doc.get(fieldname))
        doc.set(fieldname, normalized_value or None)
        if not normalized_value:
            continue

        if not THAI_IDENTITY_NUMBER_PATTERN.fullmatch(normalized_value):
            frappe.throw(_("{0} must contain exactly 13 digits.").format(_(label)))
        if not is_valid_thai_identity_number(normalized_value):
            frappe.throw(_("{0} has an invalid checksum.").format(_(label)))

        duplicate = frappe.db.exists(
            "Employee",
            {
                fieldname: normalized_value,
                "name": ["!=", doc.name or ""],
            },
        )
        if duplicate:
            frappe.throw(_("{0} is already assigned to another employee.").format(_(label)))

    if changed_identity_fields:
        doc.flags.ignore_version = True
