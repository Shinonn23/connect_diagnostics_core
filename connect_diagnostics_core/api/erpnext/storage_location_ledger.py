# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Permission-checked, read-only exact Storage Location ledger snapshots."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.meta import get_field_precision
from frappe.utils import get_datetime, rounded

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_conflict, lock_warehouses
from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    require_location_warehouse,
    require_operational_warehouse,
)


@dataclass(frozen=True)
class LocationSnapshot:
    quantity: Decimal
    # Each key retains both native identity dimensions, including the empty component.
    identities: tuple[tuple[str, str, Decimal], ...]


def _quantity(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        frappe.throw(_("Stock ledger quantity is invalid."))
    if not result.is_finite():
        frappe.throw(_("Stock ledger quantity must be finite."))
    return result


def _native_float(value: Decimal) -> float:
    try:
        result = float(value)
    except (OverflowError, ValueError):
        frappe.throw(_("Stock ledger quantity is outside native Float range."))
    if not isfinite(result):
        frappe.throw(_("Stock ledger quantity is outside native Float range."))
    return result


def _require_read(doctype: str, name: str) -> Document:
    if not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected {0} does not exist.").format(doctype))
    doc = frappe.get_doc(doctype, name)
    if not frappe.has_permission(doctype, ptype="read", doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission to read this {0}.").format(doctype))
    return doc


def _require_current_read(doctype: str, name: str) -> Document:
    doc = frappe.get_doc(doctype, name, for_update=True)
    if not frappe.has_permission(doctype, ptype="read", doc=doc, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission to read this {0}.").format(doctype))
    return doc


def _rows(
    doctype: str, filters: dict[str, object], fields: list[str], *, locking_read: bool
) -> list[frappe._dict]:
    if locking_read:
        # Dict filters preserve NOWAIT in the installed Frappe get_values path.
        return cast(
            list[frappe._dict],
            frappe.db.get_values(
                doctype,
                filters,
                fields,
                as_dict=True,
                for_update=True,
                wait=False,
                order_by="name",
            ),
        )
    return cast(list[frappe._dict], frappe.get_all(doctype, filters=filters, fields=fields))


def snapshot_location(
    *,
    company: str,
    item_code: str,
    warehouse: str,
    storage_location: str,
    cutoff: datetime | str,
    locking_read: bool = False,
) -> LocationSnapshot:
    """Read an inclusive point-in-time balance, optionally locking current stock rows."""
    if not all((company, item_code, warehouse, storage_location)):
        frappe.throw(_("Company, Item, Warehouse and Storage Location are required."))
    if locking_read:
        try:
            lock_warehouses((warehouse,))
            for doctype, name in (
                ("Company", company),
                ("Item", item_code),
                ("Warehouse", warehouse),
                ("Storage Location", storage_location),
            ):
                if not frappe.db.get_value(doctype, name, "name", for_update=True, wait=False):
                    frappe.throw(_("The selected {0} does not exist.").format(doctype))
            company_doc = _require_current_read("Company", company)
            item = _require_current_read("Item", item_code)
            warehouse_doc = _require_current_read("Warehouse", warehouse)
            location_doc = _require_current_read("Storage Location", storage_location)
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()
        if warehouse_doc.get("is_group") or warehouse_doc.get("disabled"):
            frappe.throw(_("Storage Locations require an enabled, non-group Warehouse."))
        if location_doc.get("warehouse") != warehouse:
            frappe.throw(_("Storage Location must belong to its Stock Entry row Warehouse."))
    else:
        company_doc = _require_read("Company", company)
        item = _require_read("Item", item_code)
        require_operational_warehouse(warehouse)
        warehouse_doc = _require_read("Warehouse", warehouse)
        require_location_warehouse(storage_location, warehouse)
    if warehouse_doc.get("company") != company_doc.name:
        frappe.throw(_("Warehouse must belong to the selected Company."))
    if isinstance(cutoff, datetime):
        posting_datetime = get_datetime(cutoff)
    elif isinstance(cutoff, str) and cutoff.strip():
        try:
            posting_datetime = get_datetime(cutoff)
        except (TypeError, ValueError):
            frappe.throw(_("A valid posting datetime cutoff is required."))
    else:
        frappe.throw(_("A posting datetime cutoff is required."))
    if not isinstance(posting_datetime, datetime):
        frappe.throw(_("A valid posting datetime cutoff is required."))
    assert isinstance(posting_datetime, datetime)
    if posting_datetime.tzinfo is not None:
        frappe.throw(_("Posting datetime cutoff must use the site's local time without an offset."))

    try:
        ledger = _rows(
            "Stock Ledger Entry",
            {
                "company": company,
                "item_code": item_code,
                "warehouse": warehouse,
                "storage_location": storage_location,
                "docstatus": 1,
                "is_cancelled": 0,
                "posting_datetime": ("<=", posting_datetime),
            },
            [
                "name",
                "item_code",
                "warehouse",
                "voucher_type",
                "voucher_no",
                "voucher_detail_no",
                "actual_qty",
                "serial_and_batch_bundle",
            ],
            locking_read=locking_read,
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()
    quantity = sum((_quantity(row.actual_qty) for row in ledger), Decimal(0))
    tracked = bool(item.get("has_serial_no") or item.get("has_batch_no"))
    legs = [row for row in ledger if _quantity(row.actual_qty) and tracked]
    if not legs:
        return LocationSnapshot(quantity, ())
    bundle_names = [str(row.serial_and_batch_bundle or "") for row in legs]
    if not all(bundle_names) or len(set(bundle_names)) != len(bundle_names):
        frappe.throw(_("Tracked stock ledger entries require distinct Serial and Batch Bundles."))
    try:
        bundles = _rows(
            "Serial and Batch Bundle",
            {"name": ("in", bundle_names)},
            [
                "name",
                "docstatus",
                "is_cancelled",
                "company",
                "item_code",
                "warehouse",
                "voucher_type",
                "voucher_no",
                "voucher_detail_no",
                "type_of_transaction",
                "total_qty",
            ],
            locking_read=locking_read,
        )
        entries = _rows(
            "Serial and Batch Entry",
            {"parent": ("in", bundle_names), "parenttype": "Serial and Batch Bundle"},
            [
                "parent",
                "docstatus",
                "is_cancelled",
                "item_code",
                "warehouse",
                "voucher_type",
                "voucher_no",
                "voucher_detail_no",
                "type_of_transaction",
                "serial_no",
                "batch_no",
                "qty",
            ],
            locking_read=locking_read,
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()
    by_bundle = {row.name: row for row in bundles}
    by_parent: dict[str, list[frappe._dict]] = defaultdict(list)
    for entry in entries:
        by_parent[str(entry.parent or "")].append(entry)
    quantity_field = frappe.get_meta("Serial and Batch Bundle").get_field("total_qty")
    precision = get_field_precision(quantity_field)
    identities: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for leg in legs:
        bundle = by_bundle.get(leg.serial_and_batch_bundle)
        children = by_parent.get(str(leg.serial_and_batch_bundle or ""), [])
        direction = "Inward" if _quantity(leg.actual_qty) > 0 else "Outward"
        provenance = ("item_code", "warehouse", "voucher_type", "voucher_no", "voucher_detail_no")
        if (
            bundle is None
            or bundle.docstatus != 1
            or bundle.is_cancelled
            or bundle.company != company
            or bundle.type_of_transaction != direction
            or any(bundle.get(field) != leg.get(field) for field in provenance)
            or not children
        ):
            frappe.throw(_("Tracked stock ledger bundle provenance is invalid."))
        assert bundle is not None
        child_total = Decimal(0)
        for child in children:
            serial, batch = str(child.serial_no or ""), str(child.batch_no or "")
            child_qty = _quantity(child.qty)
            if (
                child.docstatus != 1
                or child.is_cancelled
                or child.type_of_transaction != direction
                or any(child.get(field) != leg.get(field) for field in provenance)
                or (item.get("has_serial_no") and not serial)
                or (item.get("has_batch_no") and not batch)
                or not child_qty
                or (child_qty > 0) != (direction == "Inward")
            ):
                frappe.throw(_("Tracked stock ledger bundle entry is invalid."))
            child_total += child_qty
            identities[(serial, batch)] += child_qty
        if not (
            rounded(_native_float(child_total), precision)
            == rounded(_native_float(_quantity(bundle.total_qty)), precision)
            == rounded(_native_float(_quantity(leg.actual_qty)), precision)
        ):
            frappe.throw(_("Tracked stock ledger bundle quantity does not match its entries."))
    return LocationSnapshot(
        quantity,
        tuple(sorted((serial, batch, qty) for (serial, batch), qty in identities.items())),
    )
