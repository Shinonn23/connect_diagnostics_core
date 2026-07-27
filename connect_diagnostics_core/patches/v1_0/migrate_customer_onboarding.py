# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.api.erpnext.customer import build_readiness_values
from connect_diagnostics_core.config.dksh import DKSH_COMPANY
from connect_diagnostics_core.connect_diagnostics_core.doctype.partner_item_mapping import (
    partner_item_mapping,
)
from connect_diagnostics_core.setup import customer, customer_onboarding, item


def execute() -> None:
    create_custom_fields(customer.CUSTOM_FIELDS, ignore_validate=True)
    create_custom_fields(item.CUSTOM_FIELDS, ignore_validate=True)
    _backfill_customers()
    _backfill_items_and_partner_mappings()
    partner_item_mapping.on_doctype_update()
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
                "has_dksh_code",
                "customer_code_is_dksh_code",
                "dksh_customer_code",
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
        channel, dksh_sap_customer_code = _customer_channel_from_legacy(customer_row)
        readiness = build_readiness_values(
            customer={**customer_row, "customer_code": customer_name},
            addresses=addresses_by_customer.get(customer_name, []),
            contacts=contacts_by_customer.get(customer_name, []),
        )
        updates[customer_name] = {
            "customer_code": customer_name,
            "customer_channel": channel,
            "dksh_sap_customer_code": dksh_sap_customer_code,
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


def _customer_channel_from_legacy(customer_row: dict[str, Any]) -> tuple[str, str | None]:
    if not int(customer_row.get("has_dksh_code") or 0):
        return "CD", None
    if int(customer_row.get("customer_code_is_dksh_code") or 0):
        return "DKSH", None
    return "CD and DKSH", cast(str | None, customer_row.get("dksh_customer_code") or None)


def _backfill_items_and_partner_mappings() -> None:
    items = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Item",
            fields=[
                "name",
                "item_code",
                "stock_uom",
                "has_dksh_code",
                "item_code_is_dksh_code",
                "dksh_item_code",
            ],
            order_by="name asc",
        ),
    )
    if not items:
        return

    item_updates: dict[str, dict[str, str]] = {}
    mapping_candidates: list[tuple[dict[str, Any], str]] = []
    for item_row in items:
        channel, external_item_code = _item_channel_from_legacy(item_row)
        item_updates[cast(str, item_row["name"])] = {"item_channel": channel}
        if external_item_code:
            mapping_candidates.append((item_row, external_item_code))
    frappe.db.bulk_update("Item", item_updates, update_modified=False)

    partner_company = _legacy_dksh_company()

    candidates_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item_row, external_item_code in mapping_candidates:
        candidates_by_code[external_item_code].append(item_row)
    collisions = {
        external_item_code: rows
        for external_item_code, rows in candidates_by_code.items()
        if len({cast(str, row["name"]) for row in rows}) > 1
    }
    if collisions:
        _log_mapping_issues(
            "Skipped legacy Partner Item Mapping codes assigned to multiple Items: "
            + ", ".join(sorted(collisions))
        )

    existing_mappings = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Partner Item Mapping",
            filters={"parenttype": "Item", "partner_company": partner_company},
            fields=["name", "parent", "external_item_code"],
        ),
    )
    existing_by_code = {
        cast(str, row["external_item_code"]): cast(str, row["parent"])
        for row in existing_mappings
        if row.get("external_item_code")
    }
    for item_row, external_item_code in mapping_candidates:
        item_name = cast(str, item_row["name"])
        if external_item_code in collisions:
            continue
        existing_parent = existing_by_code.get(external_item_code)
        if existing_parent and existing_parent != item_name:
            _log_mapping_issues(
                f"Skipped legacy Partner Item Mapping code {external_item_code}; it is already mapped to Item {existing_parent}."
            )
            continue
        if existing_parent == item_name:
            continue

        # This one-time migration preloads every candidate and existing mapping above,
        # so the insert loop performs no nested lookup queries.
        frappe.get_doc(
            {
                "doctype": "Partner Item Mapping",
                "parent": item_name,
                "parenttype": "Item",
                "parentfield": "partner_item_mappings",
                "partner_company": partner_company,
                "external_item_code": external_item_code,
                "uom": item_row.get("stock_uom"),
                "active": 1,
            }
        ).insert(ignore_permissions=True)
        existing_by_code[external_item_code] = item_name


def _item_channel_from_legacy(item_row: dict[str, Any]) -> tuple[str, str | None]:
    if not int(item_row.get("has_dksh_code") or 0):
        return "CD", None
    if int(item_row.get("item_code_is_dksh_code") or 0):
        return "DKSH", cast(str, item_row.get("item_code") or item_row["name"])
    external_item_code = cast(str | None, item_row.get("dksh_item_code") or None)
    return "CD and DKSH", external_item_code


def _legacy_dksh_company() -> str:
    return DKSH_COMPANY


def _log_mapping_issues(message: str) -> None:
    frappe.logger(__name__).warning(message)
    frappe.log_error(title="Customer onboarding legacy item mapping", message=message)
