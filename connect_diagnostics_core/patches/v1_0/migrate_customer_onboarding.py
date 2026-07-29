# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.api.erpnext.customer import build_readiness_values
from connect_diagnostics_core.setup import customer, customer_onboarding


def execute() -> None:
    """Backfill the retained CD-only Customer onboarding fields."""
    create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True)
    _backfill_customers()
    customer_onboarding.ensure_configuration()
    frappe.clear_cache()


def _backfill_customers() -> None:
    customers = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Customer",
            fields=[
                "name",
                "customer_name",
                "customer_group",
                "territory",
                "tax_id",
                "branch_code",
                "email_id",
                "disabled",
                "no_delivery_required",
                "no_delivery_reason",
            ],
            order_by="name asc",
        ),
    )
    if not customers:
        return

    customer_names = [cast(str, row["name"]) for row in customers]
    addresses_by_customer, contacts_by_customer = _linked_customer_records(customer_names)
    updates: dict[str, dict[str, Any]] = {}
    for customer_row in customers:
        customer_name = cast(str, customer_row["name"])
        readiness = build_readiness_values(
            customer={**customer_row, "customer_code": customer_name},
            addresses=addresses_by_customer.get(customer_name, []),
            contacts=contacts_by_customer.get(customer_name, []),
        )
        updates[customer_name] = {
            "customer_code": customer_name,
            "customer_onboarding_state": (
                customer_onboarding.CUSTOMER_ACTIVE_STATE
                if not int(customer_row.get("disabled") or 0)
                else customer_onboarding.CUSTOMER_REQUEST_STATE
            ),
            **readiness,
        }
    frappe.db.bulk_update("Customer", updates, update_modified=False)


def _linked_customer_records(
    customer_names: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    links = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": ["in", customer_names],
                "parenttype": ["in", ["Address", "Contact"]],
            },
            fields=["parent", "parenttype", "link_name"],
        ),
    )
    address_names = [cast(str, row["parent"]) for row in links if row.get("parenttype") == "Address"]
    contact_names = [cast(str, row["parent"]) for row in links if row.get("parenttype") == "Contact"]
    addresses = _records_by_name(
        "Address",
        address_names,
        [
            "name",
            "address_type",
            "address_line1",
            "city",
            "county",
            "state",
            "pincode",
            "country",
            "tax_id",
            "branch_code",
            "is_primary_address",
            "is_shipping_address",
            "disabled",
        ],
    )
    contacts = _records_by_name(
        "Contact",
        contact_names,
        ["name", "full_name", "first_name", "mobile_no", "phone", "email_id", "is_primary_contact"],
    )
    addresses_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contacts_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        customer_name = cast(str, link["link_name"])
        parent_name = cast(str, link["parent"])
        if link.get("parenttype") == "Address" and parent_name in addresses:
            addresses_by_customer[customer_name].append(addresses[parent_name])
        if link.get("parenttype") == "Contact" and parent_name in contacts:
            contacts_by_customer[customer_name].append(contacts[parent_name])
    return addresses_by_customer, contacts_by_customer


def _records_by_name(doctype: str, names: list[str], fields: list[str]) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    records = cast(
        list[dict[str, Any]],
        frappe.get_all(doctype, filters={"name": ["in", names]}, fields=fields),
    )
    return {cast(str, record["name"]): record for record in records}
