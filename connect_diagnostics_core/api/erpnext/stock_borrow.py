# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_borrow.stock_borrow import (
    derive_status,
)

OUTBOUND = "Borrow Outbound"
RETURN = "Borrow Exact Return"


def get_permission_query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & {"System Manager", "Stock User", "Stock Manager"}:
        return ""
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    escaped_employee = frappe.db.escape(employee or "__none__")
    return f"`tabStock Borrow`.responsible_employee = {escaped_employee}"


def has_permission(doc: Document | None = None, ptype: str = "read", user: str | None = None) -> bool:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & {"System Manager", "Stock User", "Stock Manager"}:
        return True
    if ptype != "read" or not doc:
        return False
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    return bool(employee and doc.get("responsible_employee") == employee)


def _require_stock_borrow_permission(name: str, ptype: str = "read") -> None:
    if not frappe.has_permission("Stock Borrow", ptype, name):
        frappe.throw(_("You do not have permission to access this Stock Borrow."), frappe.PermissionError)


def _validate_request(name: str) -> Any:
    request = cast(Any, frappe.get_doc("Material Request", name))
    if request.docstatus != 1 or request.get("request_usage") != "Employee Borrow":
        frappe.throw(_("Only submitted Employee Borrow Material Requests are eligible."))
    if not frappe.has_permission("Material Request", "read", request):
        frappe.throw(_("You do not have permission to access this Material Request."), frappe.PermissionError)
    return request


def _validate_warehouse(name: str, company: str, label: str) -> None:
    values = frappe.db.get_value(
        "Warehouse",
        name,
        ["company", "is_group", "disabled"],
        as_dict=True,
    )
    if not values or values.company != company or values.is_group or values.disabled:
        frappe.throw(_("{0} must be an active leaf Warehouse for the Borrow company.").format(_(label)))


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = frappe.parse_json(value)
    if not isinstance(value, list) or not value:
        frappe.throw(_("Rows must be a non-empty list."))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"stock_borrow_item", "qty"}:
            frappe.throw(_("Each row must contain only a Borrow item and quantity."))
        key = row["stock_borrow_item"]
        if not isinstance(key, str) or key in seen or isinstance(row["qty"], bool):
            frappe.throw(_("Borrow rows must contain unique item names and numeric quantities."))
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            frappe.throw(_("Borrow quantities must be numeric."))
        if qty <= 0:
            frappe.throw(_("Borrow quantities must be greater than zero."))
        seen.add(key)
        result.append({"stock_borrow_item": key, "qty": qty})
    return result


@frappe.whitelist()
def create_stock_borrow(material_request: str) -> dict[str, Any]:
    request = _validate_request(material_request)
    frappe.db.sql("SELECT name FROM `tabMaterial Request` WHERE name=%s FOR UPDATE", (material_request,))
    existing = frappe.db.get_value("Stock Borrow", {"material_request": material_request}, "name")
    if existing:
        _require_stock_borrow_permission(existing, "read")
        return {"data": frappe.get_doc("Stock Borrow", existing).as_dict(), "message": existing}
    if not frappe.has_permission("Stock Borrow", "create"):
        frappe.throw(_("You do not have permission to create a Stock Borrow."), frappe.PermissionError)
    responsible = request.get("responsible_employee")
    if not responsible:
        frappe.throw(_("Responsible Employee is required."))
    employee = frappe.db.get_value(
        "Employee", responsible, ["status", "company", "borrow_warehouse"], as_dict=True
    )
    company = request.get("company")
    return_hold = frappe.db.get_value("Company", company, "return_qa_hold_warehouse")
    if (
        not employee
        or employee.status != "Active"
        or employee.company != company
        or not employee.borrow_warehouse
        or not return_hold
    ):
        frappe.throw(_("The Employee Borrow warehouse configuration is invalid."))
    _validate_warehouse(employee.borrow_warehouse, company, "Borrow Warehouse")
    _validate_warehouse(return_hold, company, "Return Hold Warehouse")
    eligible = []
    for row in request.items:
        item = frappe.db.get_value(
            "Item",
            row.item_code,
            ["is_stock_item", "allow_borrow", "has_serial_no", "has_batch_no", "stock_uom"],
            as_dict=True,
        )
        if (
            not item
            or not item.allow_borrow
            or not item.is_stock_item
            or item.has_serial_no
            or item.has_batch_no
        ):
            frappe.throw(_("All rows on an Employee Borrow request must use eligible Borrow Items."))
        if item:
            stock_qty = row.get("stock_qty")
            if stock_qty is None or stock_qty <= 0:
                frappe.throw(_("Borrow quantity must be greater than zero."))
            # stock_qty is already normalized by ERPNext; Stock Entry rows remain in Stock UOM.
            eligible.append((row, item.stock_uom, stock_qty))
    if not eligible:
        frappe.throw(_("The Material Request has no eligible Borrow items."))
    borrow = cast(Any, frappe.new_doc("Stock Borrow"))
    borrow.material_request = request.name
    borrow.company = company
    borrow.responsible_employee = responsible
    borrow.destination_type = request.get("destination_type")
    borrow.destination_customer = request.get("destination_customer")
    borrow.destination_address = request.get("destination_address")
    borrow.expected_return_date = request.get("expected_return_date")
    borrow.borrow_warehouse = employee.borrow_warehouse
    borrow.return_hold_warehouse = return_hold
    for row, uom, stock_qty in eligible:
        borrow.append(
            "items",
            {
                "material_request_item": row.name,
                "item_code": row.item_code,
                "uom": uom,
                "requested_qty": stock_qty,
                "pending_issue_qty": stock_qty,
            },
        )
    borrow.flags.from_borrow_service = True
    try:
        borrow.insert()
    except frappe.DuplicateEntryError:
        existing = frappe.db.get_value("Stock Borrow", {"material_request": material_request}, "name")
        if not existing:
            raise
        borrow = frappe.get_doc("Stock Borrow", existing)
    return {"data": borrow.as_dict(), "message": borrow.name}


def _build_transfer(
    borrow: Any,
    movement_type: str,
    rows: list[dict[str, Any]],
    source_warehouse: str,
    target_warehouse: str,
) -> Document:
    _require_stock_borrow_permission(borrow.name, "write")
    rows = _rows(rows)
    if movement_type not in (OUTBOUND, RETURN):
        frappe.throw(_("Unsupported Borrow movement type."))
    if movement_type == OUTBOUND and target_warehouse != borrow.borrow_warehouse:
        frappe.throw(_("Outbound target must be the employee Borrow Warehouse."))
    if movement_type == RETURN and (
        source_warehouse != borrow.borrow_warehouse or target_warehouse != borrow.return_hold_warehouse
    ):
        frappe.throw(_("Return warehouses do not match the Borrow configuration."))
    if not source_warehouse or not target_warehouse or source_warehouse == target_warehouse:
        frappe.throw(_("Source and target warehouses must be different."))
    _validate_warehouse(source_warehouse, borrow.company, "Source Warehouse")
    _validate_warehouse(target_warehouse, borrow.company, "Target Warehouse")
    if not frappe.has_permission("Stock Entry", "create"):
        frappe.throw(_("You do not have permission to create a Stock Entry."), frappe.PermissionError)
    entry = cast(Any, frappe.new_doc("Stock Entry"))
    entry.stock_entry_type = "Material Transfer"
    entry.purpose = "Material Transfer"
    entry.company = borrow.company
    entry.stock_borrow = borrow.name
    entry.borrow_movement_type = movement_type
    for row in rows:
        item = next((item for item in borrow.items if item.name == row["stock_borrow_item"]), None)
        if item is None:
            frappe.throw(_("Invalid Borrow item."))
            return entry
        if row["qty"] <= 0:
            frappe.throw(_("Invalid Borrow item or quantity."))
        if movement_type == OUTBOUND and row["qty"] > item.pending_issue_qty:
            frappe.throw(_("The outbound quantity exceeds the outstanding quantity."))
        if movement_type == RETURN and row["qty"] > item.issued_qty - item.returned_qty:
            frappe.throw(_("The return quantity exceeds the issued quantity."))
        entry.append(
            "items",
            {
                "item_code": item.item_code,
                "qty": row["qty"],
                "uom": item.uom,
                "conversion_factor": 1,
                "s_warehouse": source_warehouse,
                "t_warehouse": target_warehouse,
                "stock_borrow_item": item.name,
            },
        )
        if row["qty"] > item.requested_qty:
            frappe.throw(_("The transfer quantity exceeds the requested quantity."))
    entry.insert()
    return entry


@frappe.whitelist()
def prepare_outbound(
    stock_borrow: str, rows: list[dict[str, Any]], source_warehouse: str, target_warehouse: str
) -> dict[str, Any]:
    borrow = frappe.get_doc("Stock Borrow", stock_borrow)
    return {
        "data": _build_transfer(borrow, OUTBOUND, rows, source_warehouse, target_warehouse).as_dict(),
        "message": "Draft outbound Stock Entry prepared.",
    }


@frappe.whitelist()
def prepare_exact_return(
    stock_borrow: str, rows: list[dict[str, Any]], source_warehouse: str, target_warehouse: str
) -> dict[str, Any]:
    borrow = frappe.get_doc("Stock Borrow", stock_borrow)
    return {
        "data": _build_transfer(borrow, RETURN, rows, source_warehouse, target_warehouse).as_dict(),
        "message": "Draft exact return Stock Entry prepared.",
    }


@frappe.whitelist()
def confirm_physical_receipt(stock_entry: str) -> dict[str, Any]:
    entry = frappe.get_doc("Stock Entry", stock_entry)
    if entry.docstatus != 0 or entry.borrow_movement_type != RETURN:
        frappe.throw(_("Only a draft Borrow Exact Return can record receipt."))
    if not frappe.has_permission("Stock Entry", "write", entry):
        frappe.throw(_("You do not have permission to update this Stock Entry."), frappe.PermissionError)
    _require_stock_borrow_permission(entry.stock_borrow, "write")
    if not set(frappe.get_roles()) & {"Stock User", "Stock Manager"}:
        frappe.throw(
            _("Only Stock Users and Stock Managers can confirm physical receipt."), frappe.PermissionError
        )
    if entry.borrow_receipt_confirmed_at:
        frappe.throw(_("Physical receipt has already been confirmed."))
    entry.db_set(
        {"borrow_receipt_confirmed_at": now_datetime(), "borrow_receipt_confirmed_by": frappe.session.user}
    )
    return {"data": entry.as_dict(), "message": "Physical receipt confirmed."}


def before_submit(doc: Document, method: str) -> None:
    del method
    entry = cast(Any, doc)
    if entry.get("stock_borrow") and entry.get("borrow_movement_type") not in (OUTBOUND, RETURN):
        frappe.throw(_("Borrow Stock Entries must use a canonical movement type."))
    if (
        entry.get("stock_borrow")
        and entry.get("borrow_movement_type") == RETURN
        and not (entry.get("borrow_receipt_confirmed_at") and entry.get("borrow_receipt_confirmed_by"))
    ):
        frappe.throw(_("Physical receipt must be confirmed before submitting an exact return."))
    if entry.get("stock_borrow"):
        frappe.db.sql("SELECT name FROM `tabStock Borrow` WHERE name=%s FOR UPDATE", (entry.stock_borrow,))
        borrow = cast(Any, frappe.get_doc("Stock Borrow", entry.stock_borrow))
        if entry.stock_entry_type != "Material Transfer":
            frappe.throw(_("Borrow Stock Entries must be Material Transfers."))
        if (
            entry.borrow_movement_type == OUTBOUND
            and entry.items
            and any(row.t_warehouse != borrow.borrow_warehouse for row in entry.items)
        ):
            frappe.throw(_("Outbound target must be the configured Borrow Warehouse."))
        if entry.borrow_movement_type == RETURN and any(
            row.s_warehouse != borrow.borrow_warehouse or row.t_warehouse != borrow.return_hold_warehouse
            for row in entry.items
        ):
            frappe.throw(_("Return warehouses must match the configured Borrow warehouses."))
        for warehouse in {row.s_warehouse for row in entry.items} | {row.t_warehouse for row in entry.items}:
            _validate_warehouse(warehouse, borrow.company, "Movement Warehouse")
        seen: set[str] = set()
        cumulative = _submitted_totals(borrow.name, exclude=entry.name)
        for row in entry.items:
            linked = next((item for item in borrow.items if item.name == row.stock_borrow_item), None)
            if linked is None:
                frappe.throw(_("Stock Entry contains an invalid Stock Borrow Item link."))
                return
            if (
                row.stock_borrow_item in seen
                or row.item_code != linked.item_code
                or row.uom != linked.uom
                or not row.conversion_factor
                or row.transfer_qty <= 0
            ):
                frappe.throw(_("Stock Entry contains an invalid Stock Borrow Item link."))
            if row.s_warehouse == row.t_warehouse or row.transfer_qty > linked.requested_qty:
                frappe.throw(_("Stock Entry contains an invalid warehouse or quantity."))
            issued, returned = cumulative.get(linked.name, (0.0, 0.0))
            if entry.borrow_movement_type == OUTBOUND and issued + row.transfer_qty > linked.requested_qty:
                frappe.throw(_("The submitted outbound quantity exceeds the requested quantity."))
            if entry.borrow_movement_type == RETURN and returned + row.transfer_qty > issued:
                frappe.throw(_("The submitted return quantity exceeds the issued quantity."))
            seen.add(row.stock_borrow_item)


def on_submit(doc: Document, method: str) -> None:
    del method
    entry = cast(Any, doc)
    if entry.get("stock_borrow"):
        rebuild_totals(entry.stock_borrow)


def on_cancel(doc: Document, method: str) -> None:
    del method
    entry = cast(Any, doc)
    if entry.get("stock_borrow"):
        rebuild_totals(entry.stock_borrow)


def rebuild_totals(stock_borrow: str) -> None:
    frappe.db.sql("SELECT name FROM `tabStock Borrow` WHERE name=%s FOR UPDATE", (stock_borrow,))
    borrow = cast(Any, frappe.get_doc("Stock Borrow", stock_borrow))
    totals = {item.name: {"issued": 0.0, "returned": 0.0} for item in borrow.items}
    entries = frappe.get_all(
        "Stock Entry",
        filters={"stock_borrow": stock_borrow, "docstatus": 1},
        fields=["name", "borrow_movement_type"],
    )
    for entry in entries:
        for row in frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": entry.name, "stock_borrow_item": ["is", "set"]},
            fields=["stock_borrow_item", "transfer_qty"],
        ):
            if row.stock_borrow_item in totals:
                if entry.borrow_movement_type not in (OUTBOUND, RETURN):
                    frappe.throw(_("Submitted Stock Borrow Entry has an invalid movement type."))
                key = "issued" if entry.borrow_movement_type == OUTBOUND else "returned"
                totals[row.stock_borrow_item][key] += row.transfer_qty or 0
    for item in borrow.items:
        item.issued_qty = totals[item.name]["issued"]
        item.returned_qty = totals[item.name]["returned"]
        item.outstanding_qty = max(item.issued_qty - item.returned_qty, 0)
        item.pending_issue_qty = max(item.requested_qty - item.issued_qty, 0)
        if item.returned_qty > item.issued_qty or item.issued_qty > item.requested_qty:
            frappe.throw(_("Stock Borrow totals are inconsistent."))
    issued = sum(item.issued_qty for item in borrow.items)
    returned = sum(item.returned_qty for item in borrow.items)
    pending_issue = sum(item.pending_issue_qty for item in borrow.items)
    outstanding = sum(item.outstanding_qty for item in borrow.items)
    borrow.set("issued_qty", issued)
    borrow.set("returned_qty", returned)
    borrow.set("pending_issue_qty", pending_issue)
    borrow.set("outstanding_qty", outstanding)
    borrow.set(
        "status",
        derive_status(
            issued=issued,
            returned=returned,
            pending_issue=pending_issue,
            outstanding=outstanding,
        ),
    )
    borrow.flags.from_borrow_rebuild = True
    borrow.save(ignore_permissions=True)


def _submitted_totals(stock_borrow: str, exclude: str | None = None) -> dict[str, tuple[float, float]]:
    totals: dict[str, tuple[float, float]] = {}
    filters: dict[str, Any] = {"stock_borrow": stock_borrow, "docstatus": 1}
    for entry in frappe.get_all("Stock Entry", filters=filters, fields=["name", "borrow_movement_type"]):
        if exclude and entry.name == exclude:
            continue
        if entry.borrow_movement_type not in (OUTBOUND, RETURN):
            frappe.throw(_("Submitted Stock Borrow Entry has an invalid movement type."))
        for row in frappe.get_all(
            "Stock Entry Detail", filters={"parent": entry.name}, fields=["stock_borrow_item", "transfer_qty"]
        ):
            issued, returned = totals.get(row.stock_borrow_item, (0.0, 0.0))
            if entry.borrow_movement_type == OUTBOUND:
                issued += row.transfer_qty or 0
            else:
                returned += row.transfer_qty or 0
            totals[row.stock_borrow_item] = (issued, returned)
    return totals
