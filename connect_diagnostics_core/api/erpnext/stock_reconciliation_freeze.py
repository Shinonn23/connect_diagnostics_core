# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Block stock effects while a native Stock Reconciliation is in progress."""

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe import approval_controls

_EXECUTION_FLAG = "stock_reconciliation_execution"
_APPROVED_STATE = "Stock Reconciliation Approved"
_SUBMITTED_STATE = "Stock Reconciliation Submitted"
_CANCELLED_STATE = "Stock Reconciliation Cancelled"
_STRUCTURAL_FIELDS = frozenset(
    {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "workflow_state",
    }
)


def _approval_digest(doc: Document) -> str:
    payload = {
        str(key): value
        for key, value in doc.as_dict().items()
        if key not in _STRUCTURAL_FIELDS and not str(key).startswith("approval_")
    }
    return "stock-reconciliation-approval-v1:" + approval_controls.critical_digest(payload)


def capture_maker(doc: Document, method: str | None = None) -> None:
    del method
    clear_approval(doc)
    doc.set("approval_maker_user", approval_controls.resolve_user(frappe.session.user))


def capture_review(doc: Document, method: str | None = None) -> None:
    del method
    maker = str(doc.get("approval_maker_user") or "")
    reviewer = approval_controls.resolve_user(frappe.session.user)
    approval_controls.require_distinct_actors(maker, reviewer, ())
    doc.set("approval_critical_digest", _approval_digest(doc))
    doc.set("approval_reviewer_user", reviewer)


def capture_approval(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("approval_critical_digest") != _approval_digest(doc):
        frappe.throw(_("Stock Reconciliation changed after review and must be reviewed again."))
    maker = str(doc.get("approval_maker_user") or "")
    reviewer = str(doc.get("approval_reviewer_user") or "")
    approver = approval_controls.resolve_user(frappe.session.user)
    approval_controls.require_distinct_actors(maker, approver, (reviewer,))
    doc.set("approval_authorized_user", approver)


def clear_approval(doc: Document, method: str | None = None) -> None:
    del method
    for fieldname in (
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "approval_critical_digest",
    ):
        doc.set(fieldname, None)


def _persisted_approval(doc: Document) -> dict[str, object]:
    row = frappe.db.get_value(
        "Stock Reconciliation",
        doc.name,
        [
            "workflow_state",
            "docstatus",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "approval_critical_digest",
        ],
        as_dict=True,
        for_update=True,
    )
    if not row:
        frappe.throw(_("Stock Reconciliation approval record cannot be found."))
    return dict(row)


def _validate_approval(doc: Document, persisted: dict[str, object]) -> None:
    digest = _approval_digest(doc)
    if persisted.get("approval_critical_digest") != digest or doc.get("approval_critical_digest") != digest:
        frappe.throw(_("Stock Reconciliation approval is missing or stale."))
    maker = str(persisted.get("approval_maker_user") or "")
    reviewer = str(persisted.get("approval_reviewer_user") or "")
    approver = str(persisted.get("approval_authorized_user") or "")
    approval_controls.require_distinct_actors(maker, reviewer, ())
    approval_controls.require_distinct_actors(maker, approver, (reviewer,))


def authorize_submit_execution(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _persisted_approval(doc)
    if (
        persisted.get("workflow_state") != _APPROVED_STATE
        or persisted.get("docstatus") != 0
        or doc.get("workflow_state") != _SUBMITTED_STATE
    ):
        frappe.throw(_("Stock Reconciliation submit authorization requires the approved transition."))
    _validate_approval(doc, persisted)
    approval_controls.require_permission(doc, "submit")
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "submit"})


def authorize_cancel_execution(doc: Document, method: str | None = None) -> None:
    del method
    persisted = _persisted_approval(doc)
    if (
        persisted.get("workflow_state") != _SUBMITTED_STATE
        or persisted.get("docstatus") != 1
        or doc.get("workflow_state") != _CANCELLED_STATE
    ):
        frappe.throw(_("Stock Reconciliation cancel authorization requires the submitted transition."))
    approval_controls.require_permission(doc, "cancel")
    setattr(frappe.flags, _EXECUTION_FLAG, {"doctype": doc.doctype, "name": doc.name, "action": "cancel"})


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
        {
            "terminal_states": tuple(_TERMINAL_WORKFLOW_STATES),
            "warehouses": tuple(warehouses),
            "exclude_name": None,
        },
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
    if doc.doctype in _UPDATE_STOCK_DOCTYPES and not doc.get("update_stock"):
        return

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


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != {"doctype": doc.doctype, "name": doc.name, "action": "submit"}:
            frappe.throw(_("Stock Reconciliation must be submitted through its Workflow action."))
        persisted = _persisted_approval(doc)
        if (
            persisted.get("workflow_state") != _APPROVED_STATE
            or doc.get("workflow_state") != _SUBMITTED_STATE
        ):
            frappe.throw(_("Stock Reconciliation must have current approval before submission."))
        approval_controls.require_permission(doc, "submit")
        _validate_approval(doc, persisted)
    finally:
        setattr(frappe.flags, _EXECUTION_FLAG, None)


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != {"doctype": doc.doctype, "name": doc.name, "action": "cancel"}:
            frappe.throw(_("Stock Reconciliation must be cancelled through its Workflow action."))
        persisted = _persisted_approval(doc)
        if (
            persisted.get("workflow_state") != _SUBMITTED_STATE
            or doc.get("workflow_state") != _CANCELLED_STATE
        ):
            frappe.throw(_("Submitted Stock Reconciliations must be cancelled through the Workflow."))
        approval_controls.require_permission(doc, "cancel")
    finally:
        setattr(frappe.flags, _EXECUTION_FLAG, None)


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
