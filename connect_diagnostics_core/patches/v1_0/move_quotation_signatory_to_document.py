# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Move the Quotation signatory and validity wording onto the Quotation.

The printed signatory used to be resolved through Customer -> Sales Team -> Sales
Person -> Employee, and the custom validity wording was a Customer scalar applied
to every quotation for that Customer. Both are properties of one offer, so they
become fields on Quotation. Managing Director quotations print an empty name by
design, so the Company and Quotation authorized-signatory Employee links are
retired outright.

Existing Quotations are backfilled through the retiring chain so that reprinting
one produces the same document as before.

Idempotent: the backfills only fill blank targets, and deleting a Custom Field
that is already gone is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

from connect_diagnostics_core.setup import quotation as quotation_setup

RETIRED_FIELDS = {
    "Company": ["quotation_authorized_signatory_employee"],
    "Quotation": ["quotation_authorized_signatory_employee"],
    "Customer": ["override_quotation_validity_text", "quotation_custom_validity_text"],
}

CUSTOMER_VALIDITY_FIELDS = ("override_quotation_validity_text", "quotation_custom_validity_text")


def execute() -> None:
    """Create the new Quotation fields, backfill them, then drop the retired ones."""
    create_custom_fields(quotation_setup.CUSTOM_FIELDS, ignore_validate=True)

    _backfill_sales_representative()
    _backfill_validity_text()

    delete_custom_fields(RETIRED_FIELDS, bypass_hooks=True)
    frappe.clear_cache()


def _backfill_sales_representative() -> None:
    """Fill the new field from the Customer Sales Team the print used to read."""
    quotations = _quotations_missing("sales_representative_employee")
    if not quotations:
        return

    customers = {row["party_name"] for row in quotations}
    sales_person_by_customer = _first_sales_person_by_customer(customers)
    if not sales_person_by_customer:
        return

    employee_by_sales_person = _employee_by_sales_person(set(sales_person_by_customer.values()))

    updates: dict[str, dict[str, Any]] = {}
    for row in quotations:
        sales_person = sales_person_by_customer.get(row["party_name"], "")
        employee = employee_by_sales_person.get(sales_person, "")
        if employee:
            updates[row["name"]] = {"sales_representative_employee": employee}

    if updates:
        frappe.db.bulk_update("Quotation", updates, update_modified=False)


def _backfill_validity_text() -> None:
    """Copy the Customer-level validity override onto its Quotations."""
    if not _customer_has_validity_fields():
        return

    quotations = _quotations_missing("quotation_custom_validity_text")
    if not quotations:
        return

    overrides = _customer_validity_overrides({row["party_name"] for row in quotations})
    if not overrides:
        return

    updates: dict[str, dict[str, Any]] = {}
    for row in quotations:
        override = overrides.get(row["party_name"])
        if override:
            updates[row["name"]] = dict(override)

    if updates:
        frappe.db.bulk_update("Quotation", updates, update_modified=False)


def _quotations_missing(fieldname: str) -> list[dict[str, str]]:
    """Return Customer quotations whose target field is still empty."""
    return cast(
        list[dict[str, str]],
        frappe.get_all(
            "Quotation",
            filters={
                "quotation_to": "Customer",
                "party_name": ("is", "set"),
                fieldname: ("in", ("", None)),
            },
            fields=["name", "party_name"],
        ),
    )


def _first_sales_person_by_customer(customers: set[str]) -> dict[str, str]:
    """Return each Customer's first Sales Team row, the one the print format used."""
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Sales Team",
            filters={"parenttype": "Customer", "parent": ("in", list(customers))},
            fields=["parent", "sales_person"],
            order_by="parent asc, idx asc",
        ),
    )
    first: dict[str, str] = {}
    for row in rows:
        customer = str(row.get("parent") or "")
        sales_person = str(row.get("sales_person") or "")
        if customer and sales_person and customer not in first:
            first[customer] = sales_person
    return first


def _employee_by_sales_person(sales_people: set[str]) -> dict[str, str]:
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Sales Person",
            filters={"name": ("in", list(sales_people)), "employee": ("is", "set")},
            fields=["name", "employee"],
        ),
    )
    return {str(row["name"]): str(row["employee"]) for row in rows}


def _customer_validity_overrides(customers: set[str]) -> dict[str, dict[str, Any]]:
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Customer",
            filters={"name": ("in", list(customers)), "override_quotation_validity_text": 1},
            fields=["name", *CUSTOMER_VALIDITY_FIELDS],
        ),
    )
    overrides: dict[str, dict[str, Any]] = {}
    for row in rows:
        custom_text = str(row.get("quotation_custom_validity_text") or "").strip()
        if custom_text:
            overrides[str(row["name"])] = {
                "override_quotation_validity_text": 1,
                "quotation_custom_validity_text": custom_text,
            }
    return overrides


def _customer_has_validity_fields() -> bool:
    """Report whether this site still carries the retiring Customer fields."""
    customer_meta = frappe.get_meta("Customer")
    return all(customer_meta.has_field(fieldname) for fieldname in CUSTOMER_VALIDITY_FIELDS)
