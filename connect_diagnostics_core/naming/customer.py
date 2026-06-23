from __future__ import annotations

from typing import Any

import frappe

# Customer groups that map to prefix 4H (hospitals / government agencies)
_HOSPITAL_GOV_GROUPS: frozenset[str] = frozenset()

CUSTOMER_SERIES_MAP = {
    "Individual": "2S.###",
}
DEFAULT_COMPANY_SERIES = "4A.###"
HOSPITAL_GOV_SERIES = "4H.###"


def _is_hospital_or_gov(customer_group: str | None) -> bool:
    if not customer_group:
        return False
    upper = customer_group.upper()
    return "HOSP" in upper or upper.startswith("GOV")


def set_naming_series(doc: Any, method: str | None = None) -> None:
    """before_naming hook: auto-select Customer naming series from customer_type/group."""
    if doc.get("naming_series") and doc.naming_series in ("2S.###", "4A.###", "4H.###"):
        return

    if doc.customer_type == "Individual":
        doc.naming_series = "2S.###"
    elif _is_hospital_or_gov(doc.customer_group):
        doc.naming_series = "4H.###"
    else:
        doc.naming_series = "4A.###"
