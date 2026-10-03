# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Medical-device regulatory master resolution and Item dashboard integration."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

PRODUCT_REGISTRATION = "Medical Device Product Registration"
ACTIVE_STATUS = "Active"


def normalize_registration_number(value: str) -> str:
    """Return a comparison-only representation while retaining the entered value."""
    return "".join(character for character in value.upper().strip() if character.isalnum())


def get_effective_mapping(item_code: str, on_date: date | str | None = None) -> dict[str, str] | None:
    """Resolve exactly one active registration mapping for an Item on a date.

    ``None`` means no active mapping. Multiple effective rows are invalid master
    data and deliberately raise rather than silently selecting one history row.
    """
    effective_date = cast(date, getdate(on_date or today()))
    mapping = get_mapping_at_date(item_code, effective_date)
    if not mapping:
        return None
    if mapping.get("official_status") != ACTIVE_STATUS:
        return None
    expiry_date = getdate(mapping.get("expiry_date") or "")
    return mapping if not expiry_date or expiry_date >= effective_date else None


def get_mapping_at_date(item_code: str, on_date: date | str | None = None) -> dict[str, str] | None:
    """Resolve one mapping by effective dates without deciding its regulatory eligibility."""
    effective_date = cast(date, getdate(on_date or today()))
    rows = frappe.db.sql(
        """
        SELECT
            registered_product.parent AS registration,
            registered_product.newcode,
            registered_product.identifier,
            registered_product.physical_manufacturer,
            registration.expiry_date,
            registration.official_status
        FROM `tabMedical Device Registered Product` AS registered_product
        INNER JOIN `tabMedical Device Product Registration` AS registration
            ON registration.name = registered_product.parent
        WHERE registered_product.parenttype = %(parenttype)s
          AND registered_product.item_code = %(item_code)s
          AND registered_product.line_status = 'Active'
          AND (registered_product.effective_from IS NULL OR registered_product.effective_from = '' OR registered_product.effective_from <= %(on_date)s)
          AND (registered_product.effective_to IS NULL OR registered_product.effective_to = '' OR registered_product.effective_to >= %(on_date)s)
          AND (registration.issue_date IS NULL OR registration.issue_date = '' OR registration.issue_date <= %(on_date)s)
        """,
        {
            "parenttype": PRODUCT_REGISTRATION,
            "item_code": item_code,
            "on_date": effective_date,
        },
        as_dict=True,
    )
    if not rows:
        return None
    if len(rows) != 1:
        frappe.throw(
            _("Item {0} has more than one effective active medical-device registration on {1}.").format(
                frappe.bold(item_code), effective_date
            ),
            title=_("Ambiguous regulatory mapping"),
        )
    return cast(dict[str, str], rows[0])


def refresh_item_coverage(item: Document, on_date: date | str | None = None) -> None:
    """Set Item's read-only coverage fields from the current regulatory master."""
    item_code = cast(str, item.name or "")
    mapping = get_effective_mapping(item_code, on_date) if item_code else None
    values = {
        "current_medical_device_registration": mapping.get("registration", "") if mapping else "",
        "current_newcode": mapping.get("newcode", "") if mapping else "",
        "current_registration_expiry": mapping.get("expiry_date", "") if mapping else "",
        "current_registration_status": mapping.get("official_status", "") if mapping else "",
    }
    item.update(values)


def refresh_item_coverage_for_registration(registration: str) -> None:
    """Refresh every mapped Item after a registration's eligibility changes."""
    item_codes = frappe.get_all(
        "Medical Device Registered Product", filters={"parent": registration}, pluck="item_code"
    )
    refresh_item_coverage_for_items({cast(str, item_code) for item_code in item_codes if item_code})


def refresh_item_coverage_for_items(item_codes: set[str]) -> None:
    """Refresh read-only Item coverage for a known set of Item codes."""
    for item_code in item_codes:
        mapping = get_effective_mapping(item_code)
        frappe.db.set_value(
            "Item",
            item_code,
            {
                "current_medical_device_registration": mapping.get("registration", "") if mapping else "",
                "current_newcode": mapping.get("newcode", "") if mapping else "",
                "current_registration_expiry": mapping.get("expiry_date", "") if mapping else "",
                "current_registration_status": mapping.get("official_status", "") if mapping else "",
            },
            update_modified=False,
        )


def validate_item_classification(item: Document) -> None:
    """Keep classification coherent; mapping enforcement begins with transaction integration."""
    is_medical_device = bool(item.get("is_medical_device"))
    requirement = cast(str, item.get("regulatory_registration_requirement") or "Not Applicable")
    if not is_medical_device and requirement != "Not Applicable":
        frappe.throw(
            _("Registration Requirement must be Not Applicable when Is Medical Device is unchecked.")
        )
    if is_medical_device and requirement == "Not Applicable":
        frappe.throw(_("Medical Device Items must be marked Required or Exempt."))
    if not is_medical_device:
        item.update(
            {
                "medical_device_category": "",
                "regulatory_owner": "",
                "current_medical_device_registration": "",
                "current_newcode": "",
                "current_registration_expiry": "",
                "current_registration_status": "",
            }
        )
        return
    refresh_item_coverage(item)


def get_regulatory_owner(item: Document) -> str | None:
    """Return the Item owner, falling back to the configurable site default."""
    item_owner = cast(str, item.get("regulatory_owner") or "")
    if item_owner:
        return item_owner
    return cast(
        str | None,
        frappe.db.get_single_value("Medical Device Regulatory Settings", "default_regulatory_owner"),
    )


def inject_item_dashboard_connections(data: dict[str, Any]) -> dict[str, Any]:
    """Add Product Registration to the Item form Connections without changing source data."""
    non_standard = data.setdefault("non_standard_fieldnames", {})
    non_standard[PRODUCT_REGISTRATION] = "item_code"
    transactions = data.setdefault("transactions", [])
    for group in transactions:
        if group.get("label") == _("Regulatory"):
            if PRODUCT_REGISTRATION not in group["items"]:
                group["items"].append(PRODUCT_REGISTRATION)
            break
    else:
        transactions.append({"label": _("Regulatory"), "items": [PRODUCT_REGISTRATION]})
    return data
