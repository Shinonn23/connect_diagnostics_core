from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

PARTY_TAX_DOCTYPES = ("Customer", "Supplier")
PARTY_NAME_FIELDS = {
    "Customer": "customer_name",
    "Supplier": "supplier_name",
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


@dataclass(frozen=True)
class AddressPartyTaxCandidate:
    party_type: str
    party: str
    party_name: str | None = None
    tax_id: str | None = None
    branch_code: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "party_type": self.party_type,
            "party": self.party,
            "party_name": self.party_name,
            "tax_id": self.tax_id,
            "branch_code": self.branch_code,
            "label": self.label,
        }

    @property
    def label(self) -> str:
        title = self.party_name or self.party
        return f"{self.party_type}: {title}"

    @property
    def tax_key(self) -> tuple[str | None, str | None]:
        return self.tax_id, self.branch_code


@dataclass(frozen=True)
class AddressPartyTaxMismatch:
    party_type: str
    party: str
    party_name: str | None = None
    address_tax_id: str | None = None
    party_tax_id: str | None = None
    address_branch_code: str | None = None
    party_branch_code: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "party_type": self.party_type,
            "party": self.party,
            "party_name": self.party_name,
            "address_tax_id": self.address_tax_id,
            "party_tax_id": self.party_tax_id,
            "address_branch_code": self.address_branch_code,
            "party_branch_code": self.party_branch_code,
            "label": self.label,
        }

    @property
    def label(self) -> str:
        title = self.party_name or self.party
        return f"{self.party_type}: {title}"


@dataclass
class SyncAddressPartyTaxResult:
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0
    conflict: int = 0

    def add(self, other: SyncAddressPartyTaxResult) -> None:
        self.changed += other.changed
        self.unchanged += other.unchanged
        self.skipped += other.skipped
        self.conflict += other.conflict


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


def sync_address_party_tax_values(
    *,
    addresses: tuple[str, ...] = (),
    party_type: str | None = None,
    party: str | None = None,
    overwrite: bool = False,
    apply: bool = False,
) -> SyncAddressPartyTaxResult:
    validate_sync_address_party_tax_selectors(addresses=addresses, party_type=party_type, party=party)

    result = SyncAddressPartyTaxResult()
    for address in _get_selected_tax_addresses(addresses=addresses, party_type=party_type, party=party):
        result.add(
            _sync_single_address_party_tax(
                address.name,
                address_tax_id=address.get("tax_id"),
                address_branch_code=address.get("branch_code"),
                party_type=party_type,
                party=party,
                overwrite=overwrite,
                apply=apply,
            )
        )

    return result


def validate_sync_address_party_tax_selectors(
    *,
    addresses: tuple[str, ...],
    party_type: str | None,
    party: str | None,
) -> None:
    if party_type and party_type not in PARTY_TAX_DOCTYPES:
        raise ValueError("Party type must be Customer or Supplier.")
    if party and not party_type:
        raise ValueError("--party requires --party-type.")


def get_address_party_tax_candidates(
    address_name: str | None,
    *,
    party_type: str | None = None,
    party: str | None = None,
) -> list[AddressPartyTaxCandidate]:
    if party_type and party_type not in PARTY_TAX_DOCTYPES:
        raise ValueError("Party type must be Customer or Supplier.")
    if party and not party_type:
        raise ValueError("party requires party_type.")

    link_filters: dict[str, Any] = {
        "parenttype": "Address",
        "parent": address_name,
        "link_doctype": ("in", PARTY_TAX_DOCTYPES),
    }
    if party_type:
        link_filters["link_doctype"] = party_type
    if party:
        link_filters["link_name"] = party

    candidates: list[AddressPartyTaxCandidate] = []
    seen: set[tuple[str, str]] = set()

    for link in frappe.get_all(
        "Dynamic Link",
        filters=link_filters,
        fields=["link_doctype", "link_name"],
        order_by=None,
    ):
        doctype = link.link_doctype
        name = link.link_name
        if (doctype, name) in seen:
            continue
        seen.add((doctype, name))

        party_tax = _get_party_tax_values(doctype, name)
        if not party_tax or not (party_tax.get("tax_id") or party_tax.get("branch_code")):
            continue

        candidates.append(
            AddressPartyTaxCandidate(
                party_type=doctype,
                party=name,
                party_name=party_tax.get(PARTY_NAME_FIELDS[doctype]),
                tax_id=party_tax.get("tax_id"),
                branch_code=party_tax.get("branch_code"),
            )
        )

    return candidates


@frappe.whitelist()
def get_linked_party_tax_candidates(address_name: str) -> list[dict[str, str | None]]:
    address = frappe.get_doc("Address", address_name)
    address.check_permission("read")
    return [candidate.as_dict() for candidate in get_address_party_tax_candidates(address.name)]


@frappe.whitelist()
def get_party_tax_mismatches_for_links(
    *,
    links: str | list[dict[str, Any]],
    tax_id: str | None = None,
    branch_code: str | None = None,
) -> list[dict[str, str | None]]:
    parsed_links = frappe.parse_json(links) or []
    return [
        mismatch.as_dict()
        for mismatch in get_party_tax_mismatches_for_links_list(
            links=parsed_links,
            tax_id=tax_id,
            branch_code=branch_code,
        )
    ]


def get_party_tax_mismatches_for_links_list(
    *,
    links: list[dict[str, Any]],
    tax_id: str | None,
    branch_code: str | None,
) -> list[AddressPartyTaxMismatch]:
    mismatches: list[AddressPartyTaxMismatch] = []
    seen: set[tuple[str, str]] = set()

    for link in links:
        party_type = link.get("link_doctype")
        party = link.get("link_name")
        if party_type not in PARTY_TAX_DOCTYPES or not party or (party_type, party) in seen:
            continue
        seen.add((party_type, party))

        party_tax = _get_party_tax_values(party_type, party)
        if not party_tax:
            continue

        party_tax_id = party_tax.get("tax_id")
        party_branch_code = party_tax.get("branch_code")
        tax_id_mismatch = bool(tax_id and party_tax_id and tax_id != party_tax_id)
        branch_code_mismatch = bool(branch_code and party_branch_code and branch_code != party_branch_code)
        if not (tax_id_mismatch or branch_code_mismatch):
            continue

        frappe.has_permission(party_type, "read", party, throw=True)
        mismatches.append(
            AddressPartyTaxMismatch(
                party_type=party_type,
                party=party,
                party_name=party_tax.get(PARTY_NAME_FIELDS[party_type]),
                address_tax_id=tax_id,
                party_tax_id=party_tax_id,
                address_branch_code=branch_code,
                party_branch_code=party_branch_code,
            )
        )

    return mismatches


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


def _get_selected_tax_addresses(
    *,
    addresses: tuple[str, ...],
    party_type: str | None,
    party: str | None,
) -> list[Any]:
    filters: dict[str, Any] = {}
    if addresses:
        filters["name"] = ("in", tuple(dict.fromkeys(addresses)))

    if not party_type:
        return _deduplicate_address_rows(
            frappe.get_all(
                "Address",
                filters=filters,
                fields=["name", "tax_id", "branch_code"],
                order_by=None,
            )
        )

    dynamic_filters: list[list[str]] = [
        ["Dynamic Link", "link_doctype", "=", party_type],
    ]
    if party:
        dynamic_filters.append(["Dynamic Link", "link_name", "=", party])
    for key, value in filters.items():
        dynamic_filters.append(["Address", key, value[0], value[1]])

    return _deduplicate_address_rows(
        frappe.get_all(
            "Address",
            filters=dynamic_filters,
            fields=["name", "tax_id", "branch_code"],
            order_by=None,
        )
    )


def _deduplicate_address_rows(addresses: list[Any]) -> list[Any]:
    selected = []
    seen = set()
    for address in addresses:
        if address.name in seen:
            continue
        seen.add(address.name)
        selected.append(address)
    return selected


def _sync_single_address_party_tax(
    address: str,
    *,
    address_tax_id: str | None,
    address_branch_code: str | None,
    party_type: str | None,
    party: str | None,
    overwrite: bool,
    apply: bool,
) -> SyncAddressPartyTaxResult:
    result = SyncAddressPartyTaxResult()
    candidates = get_address_party_tax_candidates(address, party_type=party_type, party=party)
    if not candidates:
        result.skipped += 1
        return result

    unique_tax_values = {candidate.tax_key for candidate in candidates}
    if len(unique_tax_values) > 1:
        result.conflict += 1
        return result

    candidate = candidates[0]
    values_to_set = _get_address_tax_values_to_set(
        candidate,
        address_tax_id=address_tax_id,
        address_branch_code=address_branch_code,
        overwrite=overwrite,
    )

    if not values_to_set:
        result.unchanged += 1
        return result

    result.changed += 1
    if apply:
        frappe.db.set_value("Address", address, values_to_set, update_modified=False)
    return result


def _get_address_tax_values_to_set(
    candidate: AddressPartyTaxCandidate,
    *,
    address_tax_id: str | None,
    address_branch_code: str | None,
    overwrite: bool,
) -> dict[str, str]:
    values: dict[str, str] = {}

    if candidate.tax_id and (overwrite or not address_tax_id) and address_tax_id != candidate.tax_id:
        values["tax_id"] = candidate.tax_id
    if (
        candidate.branch_code
        and (overwrite or not address_branch_code)
        and address_branch_code != candidate.branch_code
    ):
        values["branch_code"] = candidate.branch_code

    return values


def _get_party_tax_values(doctype: str, name: str) -> Any | None:
    if doctype not in PARTY_NAME_FIELDS:
        return None

    fields = ["tax_id", "branch_code", PARTY_NAME_FIELDS[doctype]]
    return frappe.db.get_value(doctype, name, fields, as_dict=True)


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
