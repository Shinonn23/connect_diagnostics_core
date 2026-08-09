# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from frappe.utils import getdate

BUDDHIST_ERA_YEAR_OFFSET = 543


def _get_series_date(doc: Any):
    if doc:
        for fieldname in ("posting_date", "transaction_date", "date", "date_of_joining"):
            value = doc.get(fieldname) if hasattr(doc, "get") else getattr(doc, fieldname, None)
            if value:
                return getdate(value)

    return getdate()


def parse_buddhist_era_naming_series_variable(doc: Any, variable: str) -> str | None:
    series_date = _get_series_date(doc)
    buddhist_year = series_date.year + BUDDHIST_ERA_YEAR_OFFSET

    if variable == "YYYY-BE":
        return str(buddhist_year)

    if variable == "YY-BE":
        return f"{buddhist_year % 100:02d}"

    return None
