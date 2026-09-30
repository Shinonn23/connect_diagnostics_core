# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Block stock effects while a native Stock Reconciliation is in progress."""

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

_WAREHOUSE_FIELDS: dict[str, tuple[str, ...]] = {
    "Stock Entry": ("s_warehouse", "t_warehouse"),
    "Delivery Note": ("warehouse", "target_warehouse"),
    "Purchase Receipt": ("warehouse", "rejected_warehouse"),
    "Sales Invoice": ("warehouse", "target_warehouse"),
    "Purchase Invoice": ("warehouse", "rejected_warehouse"),
    "Stock Reconciliation": ("warehouse",),
    "Pick List": ("warehouse",),
}
_UPDATE_STOCK_DOCTYPES = frozenset({"Sales Invoice", "Purchase Invoice"})
_TERMINAL_WORKFLOW_STATES = frozenset({"Stock Reconciliation Rejected", "Stock Reconciliation Cancelled"})


def get_active_freeze_scope(doc: Document) -> list[dict[str, str]]:
    """Return the current native Freeze rows intersecting this document."""
    _pairs, warehouses = _rows_to_check(doc)
    if not warehouses:
        return []
    rows = frappe.db.sql(
        """
        select sr.name as reconciliation, sri.item_code, sri.warehouse, sr.modified
        from `tabStock Reconciliation Item` sri
        inner join `tabStock Reconciliation` sr on sr.name = sri.parent
        where sr.docstatus = 0
          and (sr.workflow_state is null or sr.workflow_state not in %(terminal_states)s)
          and sri.warehouse in %(warehouses)s
        order by sr.name, sri.item_code, sri.warehouse
        """,
        {"terminal_states": tuple(_TERMINAL_WORKFLOW_STATES), "warehouses": tuple(warehouses)},
        as_dict=True,
    )
    return [
        {
            "item_code": str(row.item_code),
            "reconciliation": str(row.reconciliation),
            "warehouse": str(row.warehouse),
            "modified": str(row.modified),
        }
        for row in rows
    ]


def validate_transaction(doc: Document, method: str | None = None) -> None:
    """Block submit against active native Stock Reconciliation scope."""
    del method
    execution_marker = getattr(frappe.flags, "freeze_exception_execution", None)
    try:
        if doc.doctype == "Stock Entry":
            from connect_diagnostics_core.api.erpnext.stock_entry_workflow import (
                is_authorized_freeze_exception,
            )

            if is_authorized_freeze_exception(doc):
                return
            if doc.get("workflow_state") == "Emergency Stock Movement Submitted":
                frappe.throw(
                    _("Emergency Stock Movement must be approved through the native Workflow before posting.")
                )
        if doc.doctype in _UPDATE_STOCK_DOCTYPES and not doc.get("update_stock"):
            return

        pairs, warehouses = _rows_to_check(doc)
        if not pairs and not warehouses:
            return

        exclude_name = doc.name if doc.doctype == "Stock Reconciliation" else None
        messages = _check_item_level(pairs, exclude_name=exclude_name) + _check_warehouse_level(
            warehouses, exclude_name=exclude_name
        )
        if messages:
            frappe.throw("<br>".join(messages), title=_("Stock Reconciliation in progress"))
    finally:
        if execution_marker is not None:
            from connect_diagnostics_core.api.erpnext.stock_entry_workflow import (
                clear_freeze_exception_execution,
            )

            clear_freeze_exception_execution()


def _rows_to_check(doc: Document) -> tuple[set[tuple[str, str]], set[str]]:
    fields = _WAREHOUSE_FIELDS.get(doc.doctype, ())
    pairs: set[tuple[str, str]] = set()
    warehouses: set[str] = set()
    for row in doc.get("items", []):
        item_code = cast(str, row.get("item_code") or "")
        for fieldname in fields:
            warehouse = cast(str, row.get(fieldname) or "")
            if not warehouse:
                continue
            warehouses.add(warehouse)
            if item_code:
                pairs.add((item_code, warehouse))
    return pairs, warehouses


_ACTIVE_RECONCILIATION_CLAUSE = """
    sr.docstatus = 0
    and (sr.workflow_state is null or sr.workflow_state not in %(terminal_states)s)
"""
_ITEM_SCOPE_QUERY = (
    """
    select sri.item_code, sri.warehouse, sr.name as reconciliation
    from `tabStock Reconciliation Item` sri
    inner join `tabStock Reconciliation` sr on sr.name = sri.parent
    where """
    + _ACTIVE_RECONCILIATION_CLAUSE
    + """
        and sri.item_code in %(item_codes)s
        and sri.warehouse in %(warehouses)s
        and (%(exclude_name)s is null or sr.name != %(exclude_name)s)
    """
)
_WAREHOUSE_SCOPE_QUERY = (
    """
    select distinct sri.warehouse, sr.name as reconciliation
    from `tabStock Reconciliation Item` sri
    inner join `tabStock Reconciliation` sr on sr.name = sri.parent
    where """
    + _ACTIVE_RECONCILIATION_CLAUSE
    + """
        and sri.warehouse in %(warehouses)s
        and (%(exclude_name)s is null or sr.name != %(exclude_name)s)
    """
)


def _check_item_level(pairs: set[tuple[str, str]], *, exclude_name: str | None = None) -> list[str]:
    if not pairs:
        return []
    item_codes = tuple({item_code for item_code, _warehouse in pairs})
    warehouses = tuple({warehouse for _item_code, warehouse in pairs})
    rows = frappe.db.sql(
        _ITEM_SCOPE_QUERY,
        {
            "terminal_states": tuple(_TERMINAL_WORKFLOW_STATES),
            "item_codes": item_codes,
            "warehouses": warehouses,
            "exclude_name": exclude_name,
        },
        as_dict=True,
    )
    return [
        _(
            "Item {0} in Warehouse {1} is frozen by Stock Reconciliation {2} (reconciliation in progress)."
        ).format(frappe.bold(row.item_code), frappe.bold(row.warehouse), frappe.bold(row.reconciliation))
        for row in rows
        if (row.item_code, row.warehouse) in pairs
    ]


def _check_warehouse_level(warehouses: set[str], *, exclude_name: str | None = None) -> list[str]:
    if not warehouses:
        return []
    rows = frappe.db.sql(
        _WAREHOUSE_SCOPE_QUERY,
        {
            "terminal_states": tuple(_TERMINAL_WORKFLOW_STATES),
            "warehouses": tuple(warehouses),
            "exclude_name": exclude_name,
        },
        as_dict=True,
    )
    return [
        _("Warehouse {0} is frozen by Stock Reconciliation {1} (reconciliation in progress).").format(
            frappe.bold(row.warehouse), frappe.bold(row.reconciliation)
        )
        for row in rows
    ]
