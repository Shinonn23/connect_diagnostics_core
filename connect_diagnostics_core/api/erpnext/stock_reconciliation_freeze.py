# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Block stock effects while a native Stock Reconciliation is in progress."""

from __future__ import annotations

from collections import Counter
from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.stock_ledger_lock import (
    lock_conflict,
    lock_warehouses,
    locked_document,
)

# Historical Workflow callback paths remain valid; signed approval belongs to the adapter.
from connect_diagnostics_core.api.erpnext.stock_reconciliation_workflow import (
    _EXECUTION_FLAG,
    _approval_digest,
    _persisted_approval,
    _validate_approval,
    authorize_cancel_execution,
    authorize_submit_execution,
    capture_approval,
    capture_maker,
    capture_review,
    clear_approval,
    validate_before_cancel,
    validate_before_submit,
)

_WAREHOUSE_FIELDS: dict[str, tuple[str, ...]] = {
    "Stock Entry": ("s_warehouse", "t_warehouse"),
    "Delivery Note": ("warehouse", "target_warehouse"),
    "Purchase Receipt": ("warehouse", "rejected_warehouse", "from_warehouse"),
    "Sales Invoice": ("warehouse", "target_warehouse"),
    "Purchase Invoice": ("warehouse", "rejected_warehouse", "from_warehouse"),
    "Stock Reconciliation": ("warehouse",),
    "Subcontracting Receipt": ("warehouse", "rejected_warehouse"),
    "Asset Capitalization": ("warehouse",),
}
_UPDATE_STOCK_DOCTYPES = frozenset({"Sales Invoice", "Purchase Invoice"})
_LANDED_COST_RECEIPTS = frozenset(
    {"Purchase Receipt", "Purchase Invoice", "Stock Entry", "Subcontracting Receipt"}
)
_TERMINAL_WORKFLOW_STATES = frozenset({"Stock Reconciliation Rejected", "Stock Reconciliation Cancelled"})


def get_active_freeze_scope(doc: Document) -> list[dict[str, str]]:
    """Return the current native Freeze rows intersecting this document."""
    _pairs, warehouses = _rows_to_check(doc)
    if not warehouses:
        return []
    try:
        lock_warehouses(warehouses)
        rows = frappe.db.sql(
            """
        select sr.name as reconciliation, sri.item_code, sri.warehouse, sr.modified
        from `tabStock Reconciliation Item` sri
        inner join `tabStock Reconciliation` sr on sr.name = sri.parent
        where sr.docstatus = 0
          and (sr.workflow_state is null or sr.workflow_state not in %(terminal_states)s)
          and sri.warehouse in %(warehouses)s
        order by sr.name, sri.item_code, sri.warehouse
        for update nowait
        """,
            {
                "terminal_states": tuple(_TERMINAL_WORKFLOW_STATES),
                "warehouses": tuple(warehouses),
                "exclude_name": None,
            },
            as_dict=True,
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()
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
    """Block physical stock effects against active native Stock Reconciliation scope."""
    if doc.doctype in _UPDATE_STOCK_DOCTYPES and not doc.get("update_stock"):
        return

    execution_marker = getattr(frappe.flags, "freeze_exception_execution", None)
    try:
        pairs, warehouses = (
            _landed_cost_scopes(doc) if doc.doctype == "Landed Cost Voucher" else _rows_to_check(doc)
        )
        if not pairs and not warehouses:
            return
        lock_warehouses(warehouses)
        from connect_diagnostics_core.api.erpnext.repost_item_valuation_reservation import (
            check_foreground_repost,
        )

        check_foreground_repost(warehouses)
        # Count leases are admitted before the emergency exception shortcut.
        # Emergency movement does not gain authority to cross an active Count.
        from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import (
            enforce_count_freeze,
        )

        enforce_count_freeze(doc, method)
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

        exclude_name = doc.name if doc.doctype == "Stock Reconciliation" else None
        messages = _check_item_level(pairs, exclude_name=exclude_name) + _check_warehouse_level(
            warehouses, exclude_name=exclude_name
        )
        if messages:
            frappe.throw("<br>".join(messages), title=_("Stock Reconciliation in progress"))
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()
    finally:
        if execution_marker is not None:
            from connect_diagnostics_core.api.erpnext.stock_entry_workflow import (
                clear_freeze_exception_execution,
            )

            clear_freeze_exception_execution()


def lock_reconciliation_scope_before_validate(doc: Document, method: str | None = None) -> None:
    """Serialize draft scope publication with physical effects on old and new Warehouses."""
    del method
    try:
        current_warehouses: set[str] = set()
        if not doc.is_new():
            _pairs, current_warehouses = _rows_to_check(
                locked_document("Stock Reconciliation", str(doc.name))
            )
        _pairs, proposed_warehouses = _rows_to_check(doc)
        lock_warehouses(current_warehouses | proposed_warehouses)
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()


def lock_reconciliation_scope_on_trash(doc: Document, method: str | None = None) -> None:
    """Keep a deleted draft's persisted scope locked until its deletion commits."""
    del method
    try:
        _pairs, warehouses = _rows_to_check(locked_document("Stock Reconciliation", str(doc.name)))
        lock_warehouses(warehouses)
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        lock_conflict()


def _rows_to_check(doc: Document) -> tuple[set[tuple[str, str]], set[str]]:
    fields = _WAREHOUSE_FIELDS.get(doc.doctype, ())
    pairs: set[tuple[str, str]] = set()
    warehouses: set[str] = set()
    tables = ("items",)
    if doc.doctype in {"Delivery Note", "Sales Invoice"}:
        tables = ("items", "packed_items")
    elif doc.doctype == "Asset Capitalization":
        tables = ("stock_items",)
    for table in tables:
        for row in doc.get(table, []):
            item_code = cast(str, row.get("item_code") or "")
            for fieldname in fields:
                warehouse = cast(str, row.get(fieldname) or "")
                if not warehouse:
                    continue
                warehouses.add(warehouse)
                if item_code:
                    pairs.add((item_code, warehouse))
    if doc.doctype == "Subcontracting Receipt" or (
        doc.doctype in {"Purchase Receipt", "Purchase Invoice"} and doc.get("is_old_subcontracting_flow")
    ):
        supplier_warehouse = cast(str, doc.get("supplier_warehouse") or "")
        if supplier_warehouse:
            for row in doc.get("supplied_items", []):
                item_code = cast(str, row.get("rm_item_code") or "")
                warehouses.add(supplier_warehouse)
                if item_code:
                    pairs.add((item_code, supplier_warehouse))
    return pairs, warehouses


def _landed_cost_scopes(doc: Document) -> tuple[set[tuple[str, str]], set[str]]:
    """Lock current sources named by the native effect document before replay."""
    pairs: set[tuple[str, str]] = set()
    warehouses: set[str] = set()
    current = locked_document("Landed Cost Voucher", str(doc.name)) if doc.name else None
    receipts = _landed_cost_receipt_identities(doc)
    if doc.docstatus == 2:
        if current is None or Counter(receipts) != Counter(_landed_cost_receipt_identities(current)):
            frappe.throw(
                _("Landed Cost Voucher receipt documents changed before cancellation; reload and retry.")
            )
    for receipt_type, receipt_name in receipts:
        receipt = locked_document(receipt_type, receipt_name)
        source_pairs, source_warehouses = _rows_to_check(receipt)
        pairs.update(source_pairs)
        warehouses.update(source_warehouses)
    return pairs, warehouses


def _landed_cost_receipt_identities(doc: Document) -> list[tuple[str, str]]:
    receipts = doc.get("purchase_receipts") or []
    if not receipts:
        frappe.throw(_("Landed Cost Voucher has no receipt documents to check."))
    identities: list[tuple[str, str]] = []
    for row in receipts:
        receipt_type = cast(str, row.get("receipt_document_type") or "")
        receipt_name = cast(str, row.get("receipt_document") or "")
        if receipt_type not in _LANDED_COST_RECEIPTS or not receipt_name:
            frappe.throw(_("Landed Cost Voucher has a missing or unsupported receipt document."))
        identities.append((receipt_type, receipt_name))
    return identities


_ACTIVE_RECONCILIATION_CLAUSE = """
    sr.docstatus = 0
    and (sr.workflow_state is null or sr.workflow_state not in %(terminal_states)s)
    and (%(exclude_name)s is null or sr.name != %(exclude_name)s)
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
        for update nowait
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
        for update nowait
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
