# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Physical repost reservations using native Warehouse and RIV transactions."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import (
    lock_conflict,
    lock_warehouses,
    locked_document,
)
from connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze import (
    _check_item_level,
    _check_warehouse_level,
    _rows_to_check,
)

_PHYSICAL_SOURCES = frozenset(
    {
        "Stock Entry",
        "Purchase Receipt",
        "Purchase Invoice",
        "Delivery Note",
        "Sales Invoice",
        "Subcontracting Receipt",
        "Stock Reconciliation",
    }
)
_ACTIVE = ("Queued", "In Progress")
_FIELD = "reservation_warehouses"


def physical_scope(doc: Document) -> set[str]:
    """Lock current source and all existing voucher SLEs; return their union."""
    if not doc.get("recreate_stock_ledgers"):
        return set()
    if doc.get("based_on") != "Transaction":
        frappe.throw(_("Physical repost requires a transaction source."))
    source_type = str(doc.get("voucher_type") or "")
    source_name = str(doc.get("voucher_no") or "")
    if source_type not in _PHYSICAL_SOURCES or not source_name:
        frappe.throw(_("Physical repost source is unsupported or missing."))
    source = locked_document(source_type, source_name)
    if source.docstatus != 1:
        frappe.throw(_("Physical repost source must remain submitted."))
    if source_type in {"Purchase Invoice", "Sales Invoice"} and not source.get("update_stock"):
        frappe.throw(_("Physical repost source must update stock."))
    pairs, scope = _rows_to_check(source)
    rows = frappe.db.sql(
        """select distinct warehouse from `tabStock Ledger Entry`
        where voucher_type = %s and voucher_no = %s and warehouse is not null
        for update nowait""",
        (source_type, source_name),
    )
    scope.update(str(row[0]) for row in rows if row[0])
    if not scope:
        frappe.throw(_("Physical repost has no Warehouse scope."))
    lock_warehouses(scope)
    exclude_name = source_name if source_type == "Stock Reconciliation" else None
    messages = _check_item_level(pairs, exclude_name=exclude_name) + _check_warehouse_level(
        scope, exclude_name=exclude_name
    )
    if messages:
        frappe.throw("<br>".join(messages), title=_("Stock Reconciliation in progress"))
    return scope


def _persisted_scope(doc: Document) -> set[str]:
    rows = frappe.db.get_values(
        "Repost Warehouse Reservation",
        filters={"parent": doc.name, "parenttype": doc.doctype, "parentfield": _FIELD},
        fieldname="warehouse",
        pluck=True,
        for_update=True,
        wait=False,
        order_by="warehouse",
    )
    scope = {str(row) for row in rows}
    if len(scope) != len(rows):
        frappe.throw(_("Physical repost reservation has duplicate Warehouses."))
    return scope


def assert_current_scope(doc: Document) -> set[str]:
    current = frappe.db.get_value(
        doc.doctype,
        doc.name,
        ["based_on", "voucher_type", "voucher_no", "recreate_stock_ledgers", "docstatus"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if (
        not current
        or current.docstatus != 1
        or any(
            current.get(field) != doc.get(field)
            for field in ("based_on", "voucher_type", "voucher_no", "recreate_stock_ledgers")
        )
    ):
        frappe.throw(_("Physical repost source identity changed; reload and retry."))
    expected = physical_scope(doc)
    if _persisted_scope(doc) != expected:
        frappe.throw(_("Physical repost Warehouse scope changed; restart after reviewing the source."))
    return expected


def active_reposts(warehouses: set[str], *, statuses: tuple[str, ...] = _ACTIVE) -> list[str]:
    """Indexed current locking reads, including empty key ranges."""
    if not warehouses:
        return []
    names: set[str] = set()
    for warehouse in sorted(warehouses):
        rows = frappe.db.sql(
            """select parent from `tabRepost Warehouse Reservation`
            where warehouse = %s and parenttype = 'Repost Item Valuation'
              and parentfield = %s for update nowait""",
            (warehouse, _FIELD),
        )
        names.update(str(row[0]) for row in rows)
    if not names:
        return []
    parents = frappe.db.get_values(
        "Repost Item Valuation",
        filters={"name": ("in", sorted(names))},
        fieldname=["name", "docstatus", "status", "recreate_stock_ledgers"],
        as_dict=True,
        for_update=True,
        wait=False,
        order_by="name",
    )
    return [
        str(row.name)
        for row in parents
        if row.docstatus == 1 and row.recreate_stock_ledgers and row.status in statuses
    ]


def check_foreground_repost(warehouses: set[str]) -> None:
    if active_reposts(warehouses, statuses=("In Progress",)):
        frappe.throw(_("A physical stock repost is in progress for this Warehouse; please retry later."))


def check_count_activation(warehouses: set[str]) -> None:
    if active_reposts(warehouses):
        frappe.throw(_("A physical stock repost is queued or in progress for this Warehouse."))


def preflight() -> None:
    """Require an explicit drain before installing a schema with no historical backfill."""
    if not frappe.db.table_exists("Repost Item Valuation"):
        return
    active = frappe.get_all(
        "Repost Item Valuation",
        filters={"docstatus": 1, "recreate_stock_ledgers": 1, "status": ("in", _ACTIVE)},
        pluck="name",
    )
    if not active:
        return
    if not frappe.db.table_exists("Repost Warehouse Reservation") or not frappe.db.exists(
        "Custom Field", {"dt": "Repost Item Valuation", "fieldname": _FIELD}
    ):
        frappe.throw(
            _("Drain active physical Repost Item Valuation before applying reservation configuration.")
        )
    reserved: dict[str, str] = {}
    for name in active:
        doc = cast(Document, frappe.get_doc("Repost Item Valuation", name))
        for warehouse in assert_current_scope(doc):
            if other := reserved.get(warehouse):
                frappe.throw(
                    _(
                        "Active physical reposts {0} and {1} overlap in Warehouse {2}; resolve them before migration."
                    ).format(frappe.bold(other), frappe.bold(name), frappe.bold(warehouse))
                )
            reserved[warehouse] = name


class RepostItemValuationReservationMixin:
    def before_submit(self) -> None:
        parent = getattr(super(), "before_submit", None)
        if parent:
            parent()
        doc = cast(Document, self)
        if doc.get("recreate_stock_ledgers"):
            try:
                scope = physical_scope(doc)
                check_count_activation(scope)
                doc.set(_FIELD, [{"warehouse": warehouse} for warehouse in sorted(scope)])
            except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
                lock_conflict()

    def set_status(self, status: str | None = None, write: bool = True) -> None:
        doc = cast(Document, self)
        if status == "In Progress" and doc.get("recreate_stock_ledgers"):
            scope = assert_current_scope(doc)
            # Preserve native recoverable DB errors so repost() retries its whole transaction.
            if any(name != doc.name for name in active_reposts(scope, statuses=("In Progress",))):
                frappe.throw(_("Another physical repost is in progress for this Warehouse."))
        cast(Any, super()).set_status(status, write)

    def recreate_stock_ledger_entries(self) -> None:
        doc = cast(Document, self)
        if doc.get("recreate_stock_ledgers"):
            scope = assert_current_scope(doc)
            if any(name != doc.name for name in active_reposts(scope, statuses=("In Progress",))):
                frappe.throw(_("Another physical repost is in progress for this Warehouse."))
        cast(Any, super()).recreate_stock_ledger_entries()

    @frappe.whitelist()
    def restart_reposting(self) -> None:
        doc = cast(Document, self)
        if not frappe.has_permission(doc.doctype, ptype="write"):
            raise frappe.PermissionError
        try:
            if not frappe.db.get_value(doc.doctype, doc.name, "name", for_update=True, wait=False):
                frappe.throw(_("Repost Item Valuation no longer exists."))
            current = cast(Document, frappe.get_doc(doc.doctype, doc.name, for_update=True))
            if current.docstatus != 1 or current.get("status") != "Failed":
                frappe.throw(_("Only a submitted failed Repost Item Valuation can restart."))
            if not frappe.has_permission(current.doctype, ptype="write", doc=current):
                raise frappe.PermissionError
            if current.get("recreate_stock_ledgers"):
                scope = physical_scope(current)
                check_count_activation(scope)
                current.set(_FIELD, [{"warehouse": warehouse} for warehouse in sorted(scope)])
                current.update_children()
            cast(
                Any,
                super(
                    RepostItemValuationReservationMixin, cast(RepostItemValuationReservationMixin, current)
                ),
            ).restart_reposting()
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()


class WarehouseReservationMixin:
    def before_rename(self, old: str, new: str, merge: bool = False) -> str | dict[str, str] | None:
        try:
            names = {old}
            if merge and frappe.db.exists("Warehouse", new):
                names.add(new)
            lock_warehouses(names)
            check_count_activation(names)
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()
        parent = getattr(super(), "before_rename", None)
        if parent:
            return parent(old, new, merge)
        return None

    def on_trash(self) -> None:
        doc = cast(Document, self)
        try:
            lock_warehouses((str(doc.name),))
            check_count_activation({str(doc.name)})
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            lock_conflict()
        cast(Any, super()).on_trash()
