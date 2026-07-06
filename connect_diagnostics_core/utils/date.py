# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date, datetime

from frappe.utils import getdate


def format_date(value: str | date | datetime | None) -> str:
    """Render a date as DD-MM-YYYY (Gregorian).

    Single source of truth for date formatting in print formats, exposed as a
    Jinja method (see hooks.py). Returns an empty string when there is no date
    so templates can call it directly without guarding for missing values.

    To switch every print format to the Buddhist era, change ``d.year`` below
    to ``d.year + 543`` — no template edits are needed.
    """
    if not value:
        return ""
    d = getdate(value)
    if d is None:
        return ""
    return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"
