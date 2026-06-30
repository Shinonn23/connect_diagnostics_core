from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import frappe

from connect_diagnostics_core.utils.address import refresh_address_display_values

ADDRESS_TAX_FIELDS = ("tax_id", "branch_code")
SOURCE_DOCTYPE_PRIORITIES = {
    "Customer": 0,
    "Supplier": 1,
    "Company": 2,
}
DEFAULT_SOURCE_PRIORITY = 100
BATCH_SIZE = 500


@dataclass(frozen=True)
class AddressTaxSource:
    address: str
    link_doctype: str
    link_name: str
    idx: int
    tax_id: str | None = None
    branch_code: str | None = None

    @property
    def priority(self) -> int:
        return SOURCE_DOCTYPE_PRIORITIES.get(self.link_doctype, DEFAULT_SOURCE_PRIORITY)


def execute() -> None:
    changed = sync_linked_address_tax_values()
    if changed:
        refresh_address_display_values(
            all=True,
            include_party_primary=True,
            apply=True,
        )
        frappe.db.commit()


def sync_linked_address_tax_values() -> int:
    address_fields = _get_existing_fields("Address", ADDRESS_TAX_FIELDS)
    if "tax_id" not in address_fields:
        return 0

    sources = _get_linked_address_tax_sources(include_branch="branch_code" in address_fields)
    selected_sources = _select_address_tax_sources(sources)
    if not selected_sources:
        return 0

    address_values = _get_address_values(tuple(selected_sources), address_fields)
    changed = 0
    for address, source in selected_sources.items():
        current_values = address_values.get(address)
        if not current_values:
            continue

        values_to_set = _get_address_values_to_set(current_values, source, address_fields)
        if not values_to_set:
            continue

        frappe.db.set_value("Address", address, values_to_set, update_modified=False)
        changed += 1

    return changed


def _get_linked_address_tax_sources(*, include_branch: bool) -> list[AddressTaxSource]:
    links_by_doctype: dict[str, list[Any]] = defaultdict(list)
    for link in frappe.get_all(
        "Dynamic Link",
        filters={"parenttype": "Address"},
        fields=["parent", "link_doctype", "link_name", "idx"],
        order_by="parent asc, idx asc",
    ):
        if _get_value(link, "parent") and _get_value(link, "link_doctype") and _get_value(link, "link_name"):
            links_by_doctype[_get_value(link, "link_doctype")].append(link)

    sources: list[AddressTaxSource] = []
    for doctype, links in links_by_doctype.items():
        source_fields = _get_source_tax_fields(doctype, include_branch=include_branch)
        if not source_fields:
            continue

        records = _get_source_tax_records(
            doctype,
            tuple(dict.fromkeys(_get_value(link, "link_name") for link in links)),
            source_fields,
        )
        for link in links:
            record = records.get(_get_value(link, "link_name"))
            if not record:
                continue

            tax_id = _get_value(record, "tax_id")
            branch_code = _get_value(record, "branch_code") if "branch_code" in source_fields else None
            if not (tax_id or branch_code):
                continue

            sources.append(
                AddressTaxSource(
                    address=_get_value(link, "parent"),
                    link_doctype=doctype,
                    link_name=_get_value(link, "link_name"),
                    idx=_get_value(link, "idx") or 0,
                    tax_id=tax_id,
                    branch_code=branch_code,
                )
            )

    return sources


def _select_address_tax_sources(sources: list[AddressTaxSource]) -> dict[str, AddressTaxSource]:
    selected: dict[str, AddressTaxSource] = {}
    for source in sorted(
        sources,
        key=lambda source: (
            source.address,
            source.priority,
            source.idx,
            source.link_doctype,
            source.link_name,
        ),
    ):
        selected.setdefault(source.address, source)
    return selected


def _get_address_values(addresses: tuple[str, ...], fields: tuple[str, ...]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for batch in _chunks(addresses):
        for address in frappe.get_all(
            "Address",
            filters={"name": ("in", batch)},
            fields=["name", *fields],
            order_by=None,
        ):
            values[_get_value(address, "name")] = address
    return values


def _get_source_tax_records(doctype: str, names: tuple[str, ...], fields: tuple[str, ...]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for batch in _chunks(names):
        for record in frappe.get_all(
            doctype,
            filters={"name": ("in", batch)},
            fields=["name", *fields],
            order_by=None,
        ):
            records[_get_value(record, "name")] = record
    return records


def _get_address_values_to_set(
    address_values: Any,
    source: AddressTaxSource,
    address_fields: tuple[str, ...],
) -> dict[str, str]:
    values: dict[str, str] = {}

    if source.tax_id and _get_value(address_values, "tax_id") != source.tax_id:
        values["tax_id"] = source.tax_id
    if (
        "branch_code" in address_fields
        and source.branch_code
        and _get_value(address_values, "branch_code") != source.branch_code
    ):
        values["branch_code"] = source.branch_code

    return values


def _get_source_tax_fields(doctype: str, *, include_branch: bool) -> tuple[str, ...]:
    try:
        if not frappe.db.table_exists(doctype):
            return ()
        meta = frappe.get_meta(doctype)
    except Exception:
        return ()

    if getattr(meta, "issingle", False) or getattr(meta, "is_virtual", False):
        return ()

    fields = []
    if meta.get_field("tax_id"):
        fields.append("tax_id")
    if include_branch and meta.get_field("branch_code"):
        fields.append("branch_code")
    return tuple(fields)


def _get_existing_fields(doctype: str, fields: tuple[str, ...]) -> tuple[str, ...]:
    meta = frappe.get_meta(doctype)
    return tuple(field for field in fields if meta.get_field(field))


def _chunks(values: tuple[str, ...], size: int = BATCH_SIZE) -> list[tuple[str, ...]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _get_value(row: Any, fieldname: str) -> Any:
    if hasattr(row, "get"):
        return row.get(fieldname)
    return getattr(row, fieldname, None)
