# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Warehouse-owned exact stock location master."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_conflict, lock_warehouses


class StorageLocation(Document):
    def validate(self) -> None:
        proposed = str(self.get("warehouse") or "").strip()
        if self.is_new():
            require_operational_warehouse(proposed)
            return
        try:
            previous = _locked_owner(str(self.name))
            lock_warehouses((previous, proposed))
            require_operational_warehouse(proposed)
            if previous != proposed and _has_stock_ledger_history(str(self.name)):
                frappe.throw(_("A Storage Location with stock ledger history cannot change Warehouse."))
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()

    def before_rename(self, old: str, new: str, merge: bool = False) -> None:
        if merge:
            frappe.throw(_("Storage Locations cannot be merged."))
        try:
            previous = _locked_owner(old)
            frappe.db.get_value("Storage Location", new, "name", for_update=True, wait=False)
            lock_warehouses((previous,))
            if _has_stock_ledger_history(old):
                frappe.throw(_("A Storage Location with stock ledger history cannot be renamed."))
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()

    def on_trash(self) -> None:
        try:
            previous = _locked_owner(str(self.name))
            lock_warehouses((previous,))
            if _has_stock_ledger_history(str(self.name)):
                frappe.throw(_("A Storage Location with stock ledger history cannot be deleted."))
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()


def validate_ledger_location(doc: Document, method: str | None = None) -> None:
    """Serialize a native Stock Ledger Entry's resolved Warehouse and Location."""
    del method
    location_name = str(doc.get("storage_location") or "").strip()
    if not location_name:
        return
    warehouse_name = str(doc.get("warehouse") or "").strip()
    try:
        lock_warehouses((warehouse_name,))
        owner = _locked_owner(location_name)
        if owner != warehouse_name:
            frappe.throw(_("Storage Location must belong to the Stock Ledger Entry Warehouse."))
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()


def _locked_owner(name: str) -> str:
    owner = frappe.db.get_value("Storage Location", name, "warehouse", for_update=True, wait=False)
    if not owner:
        frappe.throw(_("Storage Location no longer exists; reload and retry."))
    return str(owner)


def _has_stock_ledger_history(name: str) -> bool:
    return bool(
        frappe.db.get_value(
            "Stock Ledger Entry",
            {"storage_location": name},
            "name",
            for_update=True,
            wait=False,
        )
    )


def require_operational_warehouse(name: str) -> None:
    """Require a readable, enabled leaf Warehouse for location ownership or movement."""
    if not name:
        frappe.throw(_("A Warehouse is required for a Storage Location."))
    if not frappe.db.exists("Warehouse", name):
        frappe.throw(_("The selected Warehouse does not exist."))
    warehouse = frappe.get_doc("Warehouse", name)
    if not frappe.has_permission("Warehouse", ptype="read", doc=warehouse, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission to read this Warehouse."))
    if warehouse.get("is_group") or warehouse.get("disabled"):
        frappe.throw(_("Storage Locations require an enabled, non-group Warehouse."))


def require_location_warehouse(name: str, warehouse_name: str) -> None:
    """Require a readable Location owned by the row's Warehouse."""
    if not frappe.db.exists("Storage Location", name):
        frappe.throw(_("The selected Storage Location does not exist."))
    location = frappe.get_doc("Storage Location", name)
    if not frappe.has_permission("Storage Location", ptype="read", doc=location, user=frappe.session.user):
        raise frappe.PermissionError(_("You do not have permission to read this Storage Location."))
    if location.get("warehouse") != warehouse_name:
        frappe.throw(_("Storage Location must belong to its Stock Entry row Warehouse."))
