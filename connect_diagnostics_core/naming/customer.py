# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.naming import revert_series_if_last

MANUAL_CUSTOMER_NAMING_SERIES = "__CUSTOMER-MANUAL-.#####"


def _is_hospital_or_gov(customer_group: str | None) -> bool:
    if not customer_group:
        return False
    upper_customer_group = customer_group.upper()
    return "HOSP" in upper_customer_group or upper_customer_group.startswith("GOV")


def series_for_customer(doc: Any) -> str:
    """Return the retired automatic series for callers retained during deprecation.

    Customer creation no longer uses a naming series; it must use
    :func:`prepare_customer_naming` and the manual Customer Code instead.
    """
    frappe.logger(__name__).warning(
        "series_for_customer is deprecated; Customer Code is now entered manually."
    )
    if getattr(doc, "customer_type", None) == "Individual":
        return "2S.###"
    if _is_hospital_or_gov(getattr(doc, "customer_group", None)):
        return "4H.###"
    return "4A.###"


def normalise_customer_code(value: object) -> str:
    """Return the trimmed manual Customer Code or raise a user-facing error."""
    customer_code = str(value or "").strip()
    if not customer_code:
        frappe.throw(_("Customer Code is required."))
    return customer_code


def prepare_customer_naming(doc: Any, method: str | None = None) -> None:
    """Supply a temporary series so ERPNext can reach the manual autoname hook.

    The standard Customer controller raises before document-event autoname hooks
    when the site's customer master name setting is ``Naming Series`` and the
    field is blank.  This transient series is immediately reverted and cleared
    by :func:`set_customer_code`; it is never stored on the Customer.
    """
    doc.set("customer_code", normalise_customer_code(doc.get("customer_code")))
    doc.set("naming_series", MANUAL_CUSTOMER_NAMING_SERIES)


def set_naming_series(doc: Any, method: str | None = None) -> None:
    """Deprecated hook alias retained for one release cycle."""
    frappe.logger(__name__).warning(
        "set_naming_series is deprecated; use prepare_customer_naming for manual Customer Code naming."
    )
    prepare_customer_naming(doc, method)


def set_customer_code(doc: Any, method: str | None = None) -> None:
    """Use the manually entered Customer Code as the Customer document name."""
    customer_code = normalise_customer_code(doc.get("customer_code"))
    doc.set("customer_code", customer_code)

    # Customer.autoname may have consumed a legacy naming series before this hook
    # runs. Revert only when the generated value is the current series tail.
    naming_series = str(doc.get("naming_series") or "")
    if naming_series and doc.get("name"):
        revert_series_if_last(naming_series, doc.name, doc)
    doc.name = customer_code
    doc.set("naming_series", "")
