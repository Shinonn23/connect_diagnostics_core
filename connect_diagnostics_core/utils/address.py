from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.contacts.doctype.address.address import get_default_address, render_address

ADDRESS_DISPLAY_FIELDS = {
    "address": "address_display",
    "billing_address": "billing_address_display",
    "company_address": "company_address_display",
    "customer_address": "address_display",
    "dispatch_address": "dispatch_address_display",
    "dispatch_address_name": "dispatch_address",
    "shipping_address": "shipping_address_display",
    "shipping_address_name": "shipping_address",
    "source_warehouse_address": "source_address_display",
    "supplier_address": "address_display",
    "target_warehouse_address": "target_address_display",
}


@dataclass
class RefreshAddressDisplayResult:
    changed: int = 0
    unchanged: int = 0
    dangling: int = 0

    def add(self, other: RefreshAddressDisplayResult) -> None:
        self.changed += other.changed
        self.unchanged += other.unchanged
        self.dangling += other.dangling


def refresh_address_display_values(
    *,
    all: bool = False,
    doctypes: tuple[str, ...] = (),
    names: tuple[str, ...] = (),
    addresses: tuple[str, ...] = (),
    include_party_primary: bool = False,
    apply: bool = False,
) -> RefreshAddressDisplayResult:
    doctypes = tuple(dict.fromkeys(doctypes))
    names = tuple(dict.fromkeys(names))
    addresses = tuple(dict.fromkeys(addresses))
    validate_refresh_address_display_selectors(all=all, doctypes=doctypes, names=names, addresses=addresses)

    address_scope = None if all or include_party_primary else addresses
    rendered_addresses = _render_addresses(address_scope)
    lazy_render = bool(doctypes and not addresses and not include_party_primary)
    result = RefreshAddressDisplayResult()

    if include_party_primary:
        result.add(_refresh_party_primary_addresses(rendered_addresses, apply=apply))

    for doctype in _get_selected_doctypes(all=all, doctypes=doctypes, addresses=addresses):
        meta = frappe.get_meta(doctype)
        if meta.is_virtual:
            continue

        for address_field in meta.get_link_fields():
            if address_field.options != "Address":
                continue

            display_field = get_display_field(meta, address_field.fieldname)
            if display_field:
                result.add(
                    _refresh_linked_address_display(
                        doctype,
                        address_field.fieldname,
                        display_field,
                        rendered_addresses,
                        names=names,
                        addresses=addresses,
                        apply=apply,
                        lazy_render=lazy_render,
                    )
                )

    return result


def get_display_field(meta, address_field: str) -> str | None:
    candidates = [ADDRESS_DISPLAY_FIELDS.get(address_field)]

    if address_field.endswith("_name"):
        candidates.append(address_field.removesuffix("_name"))
        candidates.append(f"{address_field.removesuffix('_name')}_display")

    candidates.append(f"{address_field}_display")

    for candidate in candidates:
        if candidate and meta.get_field(candidate):
            return candidate

    return None


def validate_refresh_address_display_selectors(
    *,
    all: bool,
    doctypes: tuple[str, ...],
    names: tuple[str, ...],
    addresses: tuple[str, ...],
) -> None:
    if not (all or doctypes or addresses):
        raise ValueError("Select records with --all, --doctype, or --address.")
    if all and (doctypes or names or addresses):
        raise ValueError("--all cannot be combined with --doctype, --name, or --address.")
    if names and len(set(doctypes)) != 1:
        raise ValueError("--name requires exactly one --doctype.")


def _render_addresses(addresses: tuple[str, ...] | None) -> dict[str, str]:
    if addresses == ():
        return {}

    filters = {"name": ("in", addresses)} if addresses is not None else None
    rendered_addresses: dict[str, str] = {}
    for address in frappe.get_all("Address", filters=filters, pluck="name", order_by=None):
        rendered = render_address(address, check_permissions=False)
        if rendered is not None:
            rendered_addresses[address] = rendered
    return rendered_addresses


def _get_selected_doctypes(
    *,
    all: bool,
    doctypes: tuple[str, ...],
    addresses: tuple[str, ...],
) -> tuple[str, ...] | list[str]:
    if doctypes:
        return doctypes
    if all or addresses:
        return frappe.get_all(
            "DocType",
            filters={"issingle": 0, "istable": 0},
            pluck="name",
            order_by=None,
        )
    return ()


def _refresh_party_primary_addresses(
    rendered_addresses: dict[str, str],
    *,
    apply: bool,
) -> RefreshAddressDisplayResult:
    result = RefreshAddressDisplayResult()

    for doctype in ("Customer", "Supplier"):
        for party in frappe.get_all(doctype, fields=["name", "primary_address"], order_by=None):
            address = get_default_address(doctype, party.name)
            if address and address not in rendered_addresses:
                result.dangling += 1
                continue

            expected = rendered_addresses.get(address)
            if party.primary_address == expected:
                result.unchanged += 1
                continue

            result.changed += 1
            if apply:
                frappe.db.set_value(
                    doctype,
                    party.name,
                    "primary_address",
                    expected,
                    update_modified=False,
                )

    return result


def _refresh_linked_address_display(
    doctype: str,
    address_field: str,
    display_field: str,
    rendered_addresses: dict[str, str],
    *,
    names: tuple[str, ...],
    addresses: tuple[str, ...],
    apply: bool,
    lazy_render: bool = False,
) -> RefreshAddressDisplayResult:
    filters: dict[str, tuple[str, object]] = {address_field: ("is", "set")}
    if names:
        filters["name"] = ("in", names)
    if addresses:
        filters[address_field] = ("in", addresses)

    result = RefreshAddressDisplayResult()
    for doc in frappe.get_all(
        doctype,
        filters=filters,
        fields=["name", address_field, display_field],
        order_by=None,
    ):
        address = doc.get(address_field)
        if not _ensure_rendered_address(address, rendered_addresses, lazy_render=lazy_render):
            result.dangling += 1
            continue

        expected = rendered_addresses[address]
        if doc.get(display_field) == expected:
            result.unchanged += 1
            continue

        result.changed += 1
        if apply:
            frappe.db.set_value(
                doctype,
                doc.name,
                display_field,
                expected,
                update_modified=False,
            )

    return result


def _ensure_rendered_address(
    address: str | None,
    rendered_addresses: dict[str, str],
    *,
    lazy_render: bool,
) -> bool:
    if not address:
        return False
    if address in rendered_addresses:
        return True
    if not lazy_render or not frappe.db.exists("Address", address):
        return False

    rendered = render_address(address, check_permissions=False)
    if rendered is None:
        return False
    rendered_addresses[address] = rendered
    return True
