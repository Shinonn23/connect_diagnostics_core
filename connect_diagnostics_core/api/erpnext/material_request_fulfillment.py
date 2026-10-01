# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import frappe
from erpnext.stock.utils import get_stock_balance
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime, today

from connect_diagnostics_core.connect_diagnostics_stock.doctype.equipment_model.equipment_model import (
    get_eligible_demo_stock_items,
)

READ_ROLES = {
    "Stock User",
    "Stock Manager",
    "Accounts User",
    "Accounts Manager",
    "System Manager",
}
STOCK_ROLES = {"Stock User", "Stock Manager", "System Manager"}
PURCHASE_ROLES = {"Purchase User", "Purchase Manager"}
FORBIDDEN_ASSET_STATUSES = {
    "Cancelled",
    "Sold",
    "Scrapped",
    "Capitalized",
    "In Maintenance",
    "Out of Order",
}


def on_submit(doc: Document, method: str) -> str | None:
    """Create the immutable, non-posting plan for an eligible submitted Demo request."""
    if doc.get("request_usage") != "Customer Demo":
        return
    mr = frappe.db.get_value(
        "Material Request",
        doc.name,
        ["name", "docstatus", "company", "request_usage"],
        as_dict=True,
        for_update=True,
    )
    if not mr or mr.docstatus != 1:
        frappe.throw(_("Only a submitted Material Request can create a Fulfillment plan."))
    if mr.request_usage != "Customer Demo":
        return
    operation_id = f"material-request:{doc.name}:submitted"
    existing = frappe.db.get_value("Material Request Fulfillment", {"operation_id": operation_id}, "name")
    if existing:
        return existing
    rows = frappe.get_all(
        "Material Request Item",
        filters={"parent": doc.name},
        fields=["name", "item_code", "item_name", "qty", "uom", "stock_uom"],
        order_by="idx asc",
    )
    eligible = set(get_eligible_demo_stock_items(mr.company))
    if not rows or any(row.item_code not in eligible for row in rows):
        frappe.throw(_("Every Demo request item must have an active Equipment Model mapping."))
    source = {
        "material_request": doc.name,
        "company": mr.company,
        "request_usage": mr.request_usage,
        "items": [
            {key: row.get(key) for key in ("name", "item_code", "item_name", "qty", "uom", "stock_uom")}
            for row in rows
        ],
    }
    digest = hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()
    allocations: list[dict[str, Any]] = []
    for row in rows:
        mappings = frappe.get_all(
            "Equipment Model",
            filters={"stock_item": row.item_code, "disabled": 0, "allow_demo": 1},
            fields=["name", "fixed_asset_item", "company"],
            order_by="name asc",
        )
        mapping = next(
            (candidate for candidate in mappings if candidate.company in (None, "", mr.company)), None
        )
        if not mapping:
            frappe.throw(_("Item {0} no longer has an eligible Equipment Model.").format(row.item_code))
        mapping = cast(frappe._dict, mapping)
        allocations.append(
            {
                "material_request_item": row.name,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": row.qty,
                "uom": row.uom or row.stock_uom,
                "equipment_model": mapping.name,
                "fixed_asset_item": mapping.fixed_asset_item,
                "source_type": "Unplanned",
            }
        )
    payload = {
        "doctype": "Material Request Fulfillment",
        "material_request": doc.name,
        "operation_id": operation_id,
        "company": mr.company,
        "source_version": 1,
        "source_digest": digest,
        "status": "Planned",
        "allocations": allocations,
    }
    previous_flag = getattr(frappe.flags, "material_request_fulfillment_handoff", False)
    frappe.flags.material_request_fulfillment_handoff = True
    try:
        return frappe.get_doc(payload).insert(ignore_permissions=True).name
    except frappe.DuplicateEntryError:
        return frappe.db.get_value("Material Request Fulfillment", {"operation_id": operation_id}, "name")
    except frappe.QueryDeadlockError:
        # MariaDB can reject simultaneous naming-series updates before the
        # operation-id uniqueness check. Its deadlock handling rolls back this
        # transaction, so re-lock the source request and return the winner.
        frappe.db.rollback()
        source_request = frappe.db.get_value("Material Request", doc.name, "name", for_update=True)
        if source_request:
            winner = frappe.db.get_value(
                "Material Request Fulfillment", {"operation_id": operation_id}, "name"
            )
            if winner:
                return winner
        raise
    finally:
        frappe.flags.material_request_fulfillment_handoff = previous_flag


def get_permission_query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & PURCHASE_ROLES and not roles & READ_ROLES:
        return f"`tabMaterial Request Fulfillment`.material_request in (select name from `tabMaterial Request` where owner = {frappe.db.escape(user)})"
    if not roles & (PURCHASE_ROLES | READ_ROLES):
        return "1=0"
    return "1=1"


def has_permission(doc: Document, ptype: str, user: str | None = None, **kwargs: Any) -> bool | None:
    if ptype != "read":
        return False
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & READ_ROLES:
        return True
    if roles & PURCHASE_ROLES:
        owner = frappe.db.get_value("Material Request", doc.get("material_request"), "owner")
        return owner == user
    return False


def _require_stock_access(fulfillment_name: str) -> Document:
    if not set(frappe.get_roles()) & STOCK_ROLES:
        frappe.throw(_("Only Stock users can plan Demo Fulfillments."), frappe.PermissionError)
    fulfillment = frappe.get_doc("Material Request Fulfillment", fulfillment_name)
    if not frappe.has_permission("Material Request Fulfillment", "read", doc=fulfillment):
        frappe.throw(_("You do not have permission to plan this Fulfillment."), frappe.PermissionError)
    if fulfillment.status != "Planned":
        frappe.throw(_("Only the active planned Fulfillment can be replanned."))
    return fulfillment


def _company_configuration(company: str) -> dict[str, Any]:
    values = frappe.db.get_value(
        "Company", company, ["demo_asset_pool_location", "demo_return_reuse_window_days"], as_dict=True
    )
    if not values or not values.demo_asset_pool_location or values.demo_return_reuse_window_days is None:
        frappe.throw(_("Company Demo asset pool and return reuse settings are required."))
    if frappe.db.get_value("Location", values.demo_asset_pool_location, "is_group"):
        frappe.throw(_("Company Demo asset pool must be a leaf Location."))
    window = int(values.demo_return_reuse_window_days)
    if window < 0:
        frappe.throw(_("Demo return reuse window cannot be negative."))
    return {
        "demo_asset_pool_location": values.demo_asset_pool_location,
        "demo_return_reuse_window_days": window,
    }


def _active_asset_names() -> set[str]:
    return set(frappe.get_all("Demo Asset Reservation", filters={"status": "Active"}, pluck="asset"))


def _has_outstanding_dispatch(asset: str) -> bool:
    return bool(
        frappe.db.sql(
            """
            SELECT out_row.name
            FROM `tabDispatch Transfer` out_row
            INNER JOIN `tabDispatch` out_doc ON out_doc.name = out_row.parent
            LEFT JOIN `tabDispatch Transfer` ret_row
                ON ret_row.against_dispatch_transfer = out_row.name
            LEFT JOIN `tabDispatch` ret_doc
                ON ret_doc.name = ret_row.parent
                AND ret_doc.dispatch_type = 'Return'
                AND ret_doc.docstatus = 1
                AND ret_doc.delivery_status = 'Delivered'
            WHERE out_row.asset = %s
                AND out_doc.dispatch_type = 'Outbound'
                AND out_doc.docstatus = 1
            GROUP BY out_row.name, out_row.qty
            HAVING out_row.qty - COALESCE(SUM(CASE WHEN ret_doc.name IS NOT NULL THEN ret_row.qty ELSE 0 END), 0) > 0
            LIMIT 1
            """,
            (asset,),
        )
    )


def _available_assets(company: str, item_codes: set[str], location: str) -> list[dict[str, Any]]:
    held = _active_asset_names()
    assets = frappe.get_all(
        "Asset",
        filters={"company": company, "docstatus": 1, "location": location},
        fields=["name", "item_code", "status"],
        order_by="name asc",
    )
    return [
        asset
        for asset in assets
        if asset.item_code in item_codes
        and asset.name not in held
        and asset.status not in FORBIDDEN_ASSET_STATUSES
        and not _has_outstanding_dispatch(asset.name)
    ]


def _returning_assets(
    company: str, item_codes: set[str], location: str, reuse_window_days: int
) -> list[dict[str, Any]]:
    deadline = getdate(add_days(today(), reuse_window_days))
    candidates = frappe.db.sql(
        """
        SELECT
            out_row.asset AS name,
            asset.item_code,
            request.expected_return_date AS expected_available_on,
            out_row.name AS outbound_transfer
        FROM `tabDispatch Transfer` out_row
        INNER JOIN `tabDispatch` out_doc ON out_doc.name = out_row.parent
        INNER JOIN `tabMaterial Request` request ON request.name = out_doc.material_request
        INNER JOIN `tabAsset` asset ON asset.name = out_row.asset
        LEFT JOIN `tabDispatch Transfer` ret_row
            ON ret_row.against_dispatch_transfer = out_row.name
        LEFT JOIN `tabDispatch` ret_doc
            ON ret_doc.name = ret_row.parent
            AND ret_doc.dispatch_type = 'Return'
            AND ret_doc.docstatus = 1
            AND ret_doc.delivery_status = 'Delivered'
        WHERE out_doc.dispatch_type = 'Outbound'
            AND out_doc.docstatus = 1
            AND out_doc.delivery_status = 'Delivered'
            AND out_doc.company = %(company)s
            AND request.request_usage = 'Customer Demo'
            AND request.expected_return_date BETWEEN %(start_date)s AND %(end_date)s
            AND out_row.original_source_location = %(location)s
            AND asset.company = %(company)s
            AND asset.docstatus = 1
            AND asset.item_code IN %(item_codes)s
        GROUP BY out_row.name, out_row.asset, asset.item_code, request.expected_return_date, out_row.qty
        HAVING out_row.qty - COALESCE(SUM(CASE WHEN ret_doc.name IS NOT NULL THEN ret_row.qty ELSE 0 END), 0) > 0
        ORDER BY request.expected_return_date, out_row.asset
        """,
        {
            "company": company,
            "start_date": getdate(today()),
            "end_date": deadline,
            "location": location,
            "item_codes": tuple(sorted(item_codes)) or ("",),
        },
        as_dict=True,
    )
    held = _active_asset_names()
    return [
        row
        for row in candidates
        if row.name not in held
        and frappe.db.get_value("Asset", row.name, "status") not in FORBIDDEN_ASSET_STATUSES
    ]


def _copy_allocation(row: Any) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "material_request_item",
            "item_code",
            "item_name",
            "qty",
            "uom",
            "equipment_model",
            "fixed_asset_item",
            "source_type",
            "selected_source",
            "asset_reservation",
            "expected_available_on",
            "downstream_doctype",
            "downstream_reference",
            "conversion_state",
            "conversion_source_warehouse",
            "conversion_source_bundle",
            "resolved_asset",
            "asset_movement",
            "dispatch_transfer",
            "lifecycle_state",
        )
    }


def _lock_current_plan(fulfillment: Document) -> Document:
    material_request = cast(str, fulfillment.get("material_request"))
    frappe.db.get_value("Material Request", material_request, "name", for_update=True)
    current = frappe.db.get_value(
        "Material Request Fulfillment",
        {"material_request": material_request, "status": "Planned"},
        ["name", "plan_revision"],
        order_by="plan_revision desc",
        for_update=True,
        as_dict=True,
    )
    if not current or current.name != fulfillment.name:
        frappe.throw(_("This Fulfillment has already been superseded. Refresh and try again."))
    return fulfillment


def _validate_locked_candidate(candidate: dict[str, Any], plan: Document, config: dict[str, Any]) -> None:
    asset = cast(str, candidate["name"])
    values = frappe.db.get_value(
        "Asset",
        asset,
        ["company", "docstatus", "item_code", "location", "status"],
        as_dict=True,
        for_update=True,
    )
    if not values or values.company != plan.get("company") or values.docstatus != 1:
        frappe.throw(_("Asset {0} is no longer eligible.").format(asset))
    if values.status in FORBIDDEN_ASSET_STATUSES:
        frappe.throw(_("Asset {0} is no longer usable.").format(asset))
    if frappe.db.exists("Demo Asset Reservation", {"active_asset_key": asset, "status": "Active"}):
        frappe.throw(_("Asset {0} is already reserved.").format(asset))
    source_type = candidate["source_type"]
    if source_type == "Existing Asset":
        if values.location != config["demo_asset_pool_location"] or _has_outstanding_dispatch(asset):
            frappe.throw(_("Asset {0} is no longer available at the Demo pool.").format(asset))
    elif source_type == "Returning Asset":
        matches = _returning_assets(
            cast(str, plan.get("company")),
            {cast(str, values.item_code)},
            cast(str, config["demo_asset_pool_location"]),
            int(config["demo_return_reuse_window_days"]),
        )
        if not any(row["name"] == asset for row in matches):
            frappe.throw(_("Asset {0} is no longer expected to return in time.").format(asset))


def _build_replan(
    fulfillment: Document,
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
    action: str,
) -> str:
    fulfillment = _lock_current_plan(fulfillment)
    available_by_item: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate.get("item_code"):
            available_by_item.setdefault(cast(str, candidate["item_code"]), []).append(candidate)
    released_reservation = candidates[0].get("reservation") if action == "Release Reservation" else None

    selected: list[dict[str, Any]] = []
    allocations: list[dict[str, Any]] = []
    changed = False
    for row in cast(list[Any], fulfillment.get("allocations", [])):
        if row.get("source_type") != "Unplanned":
            if released_reservation and row.get("asset_reservation") == released_reservation:
                released = _copy_allocation(row)
                released.update(
                    {
                        "source_type": "Unplanned",
                        "selected_source": None,
                        "asset_reservation": None,
                        "expected_available_on": None,
                        "resolved_asset": None,
                        "lifecycle_state": None,
                    }
                )
                allocations.append(released)
                changed = True
                continue
            allocations.append(_copy_allocation(row))
            continue
        remaining = float(row.get("qty") or 0)
        if action == "Stock Conversion":
            if not remaining.is_integer() or remaining < 1:
                frappe.throw(_("Stock Conversion quantities must be whole physical units."))
            while remaining >= 1:
                planned = _copy_allocation(row)
                planned.update(
                    {
                        "qty": 1,
                        "source_type": "Stock Conversion",
                        "selected_source": None,
                        "resolved_asset": None,
                        "lifecycle_state": None,
                    }
                )
                allocations.append(planned)
                remaining -= 1
            changed = True
            continue
        pool = available_by_item.get(cast(str, row.get("fixed_asset_item")), [])
        while remaining >= 1 and pool:
            candidate = pool.pop(0)
            candidate["material_request_item"] = row.get("material_request_item")
            candidate["source_type"] = action
            selected.append(candidate)
            planned = _copy_allocation(row)
            planned.update(
                {
                    "qty": 1,
                    "source_type": action,
                    "selected_source": candidate["name"],
                    "asset_reservation": None,
                    "expected_available_on": candidate.get("expected_available_on"),
                    "resolved_asset": candidate["name"],
                    "lifecycle_state": "Ready",
                }
            )
            allocations.append(planned)
            remaining -= 1
            changed = True
        if remaining > 0:
            unplanned = _copy_allocation(row)
            unplanned.update(
                {
                    "qty": remaining,
                    "source_type": "Unplanned",
                    "selected_source": None,
                    "asset_reservation": None,
                    "expected_available_on": None,
                    "resolved_asset": None,
                    "lifecycle_state": None,
                }
            )
            allocations.append(unplanned)
    if not changed:
        return cast(str, fulfillment.name)

    for candidate in sorted(selected, key=lambda row: cast(str, row["name"])):
        _validate_locked_candidate(candidate, fulfillment, config)

    current_revision = int(fulfillment.get("plan_revision") or 1)
    revision = current_revision + 1
    operation_id = f"material-request:{fulfillment.get('material_request')}:plan:{revision}"
    payload = {
        "doctype": "Material Request Fulfillment",
        "material_request": fulfillment.get("material_request"),
        "operation_id": operation_id,
        "plan_revision": revision,
        "company": fulfillment.get("company"),
        "source_version": fulfillment.get("source_version"),
        "source_digest": fulfillment.get("source_digest"),
        "configuration_snapshot": frappe.as_json(config),
        "status": "Planned",
        "allocations": allocations,
    }
    old_flag = getattr(frappe.flags, "material_request_fulfillment_handoff", False)
    frappe.flags.material_request_fulfillment_handoff = True
    try:
        new_plan = frappe.get_doc(payload).insert(ignore_permissions=True)
        reservation_flag = getattr(frappe.flags, "demo_asset_reservation_internal", False)
        frappe.flags.demo_asset_reservation_internal = True
        try:
            for row in cast(list[Any], new_plan.get("allocations", [])):
                if not row.get("selected_source") or row.get("asset_reservation"):
                    continue
                hold = frappe.get_doc(
                    {
                        "doctype": "Demo Asset Reservation",
                        "fulfillment": new_plan.name,
                        "fulfillment_allocation": row.name,
                        "asset": row.get("selected_source"),
                        "active_asset_key": row.get("selected_source"),
                        "reservation_type": row.get("source_type"),
                        "status": "Active",
                        "expected_available_on": row.get("expected_available_on"),
                    }
                ).insert(ignore_permissions=True)
                frappe.db.set_value(
                    "Material Request Fulfillment Allocation",
                    row.name,
                    "asset_reservation",
                    hold.name,
                    update_modified=False,
                )
        finally:
            frappe.flags.demo_asset_reservation_internal = reservation_flag
        retained_holds = {
            row.get("asset_reservation")
            for row in cast(list[Any], new_plan.get("allocations", []))
            if row.get("asset_reservation")
        }
        old_holds = {
            row.get("asset_reservation")
            for row in cast(list[Any], fulfillment.get("allocations", []))
            if row.get("asset_reservation")
            and frappe.db.get_value("Demo Asset Reservation", row.get("asset_reservation"), "status")
            == "Active"
        }
        for hold_name in set(old_holds) - retained_holds:
            frappe.db.set_value(
                "Demo Asset Reservation",
                hold_name,
                {
                    "status": "Released",
                    "active_asset_key": None,
                    "released_on": now_datetime(),
                    "release_reason": "Superseded plan",
                },
            )
        frappe.db.set_value("Material Request Fulfillment", fulfillment.name, "status", "Superseded")
        return new_plan.name
    except frappe.DuplicateEntryError:
        frappe.throw(_("An Asset was reserved by another planner. Refresh and try again."))
        raise AssertionError("frappe.throw must raise")
    finally:
        frappe.flags.material_request_fulfillment_handoff = old_flag


@frappe.whitelist(methods=["POST"])
def use_available_assets(fulfillment: str) -> dict[str, Any]:
    plan = _require_stock_access(fulfillment)
    config = _company_configuration(cast(str, plan.get("company")))
    rows = cast(list[Any], plan.get("allocations", []))
    codes = {row.get("fixed_asset_item") for row in rows}
    candidates = _available_assets(cast(str, plan.get("company")), codes, config["demo_asset_pool_location"])
    return {
        "data": _build_replan(plan, candidates, config, "Existing Asset"),
        "message": _("Available Assets selected."),
    }


@frappe.whitelist(methods=["POST"])
def wait_for_returning_assets(fulfillment: str) -> dict[str, Any]:
    plan = _require_stock_access(fulfillment)
    config = _company_configuration(cast(str, plan.get("company")))
    rows = cast(list[Any], plan.get("allocations", []))
    codes = {cast(str, row.get("fixed_asset_item")) for row in rows if row.get("fixed_asset_item")}
    candidates = _returning_assets(
        cast(str, plan.get("company")),
        codes,
        cast(str, config["demo_asset_pool_location"]),
        int(config["demo_return_reuse_window_days"]),
    )
    return {
        "data": _build_replan(plan, candidates, config, "Returning Asset"),
        "message": _("Returning Assets selected."),
    }


@frappe.whitelist(methods=["POST"])
def use_stock_now(fulfillment: str) -> dict[str, Any]:
    plan = _require_stock_access(fulfillment)
    config = _company_configuration(cast(str, plan.get("company")))
    return {
        "data": _build_replan(plan, [], config, "Stock Conversion"),
        "message": _("Stock conversion candidates recorded."),
    }


@frappe.whitelist(methods=["POST"])
def create_stock_asset_conversion(
    fulfillment: str, allocation: str, warehouse: str, serial_and_batch_bundle: str | None = None
) -> dict[str, Any]:
    try:
        return _create_stock_asset_conversion(fulfillment, allocation, warehouse, serial_and_batch_bundle)
    except frappe.QueryDeadlockError:
        # A concurrent winner can update the allocation while this request is
        # waiting for its lock. MariaDB rolls this transaction back, so return
        # the durable operation winner after the rollback instead of creating
        # or retrying a second voucher.
        frappe.db.rollback()
        operation_id = f"fulfillment-allocation:{allocation}:stock-asset-conversion"
        winner = frappe.db.get_value("Stock Asset Conversion", {"operation_id": operation_id}, "name")
        if winner:
            return {"data": winner, "message": _("Stock Asset Conversion already exists.")}
        raise


def _create_stock_asset_conversion(
    fulfillment: str, allocation: str, warehouse: str, serial_and_batch_bundle: str | None = None
) -> dict[str, Any]:
    """Create one idempotent Draft conversion for a unit-sized active allocation."""
    if not set(frappe.get_roles()) & STOCK_ROLES:
        frappe.throw(_("Only Stock users can create Stock Asset Conversions."), frappe.PermissionError)
    plan = _require_stock_access(fulfillment)
    plan = _lock_current_plan(plan)
    company = cast(str, plan.get("company"))
    row = frappe.db.get_value(
        "Material Request Fulfillment Allocation",
        allocation,
        [
            "name",
            "parent",
            "source_type",
            "qty",
            "item_code",
            "fixed_asset_item",
            "equipment_model",
            "conversion_state",
            "downstream_reference",
        ],
        as_dict=True,
        for_update=True,
    )
    if not row or row.parent != plan.name or row.source_type != "Stock Conversion" or float(row.qty) != 1:
        frappe.throw(_("Only an active unit Stock Conversion allocation can be converted."))
    if row.conversion_state or row.downstream_reference:
        existing = frappe.db.get_value(
            "Stock Asset Conversion", {"fulfillment_allocation": allocation}, "name"
        )
        if existing:
            return {"data": existing, "message": _("Stock Asset Conversion already exists.")}
        frappe.throw(_("The allocation already has a conversion lifecycle result."))
    operation_id = f"fulfillment-allocation:{allocation}:stock-asset-conversion"
    existing = frappe.db.get_value("Stock Asset Conversion", {"operation_id": operation_id}, "name")
    if existing:
        return {"data": existing, "message": _("Stock Asset Conversion already exists.")}
    warehouse_values = frappe.db.get_value(
        "Warehouse", warehouse, ["company", "disabled"], as_dict=True, for_update=True
    )
    if not warehouse_values or warehouse_values.company != company or warehouse_values.disabled:
        frappe.throw(_("Select an enabled Warehouse belonging to the request Company."))
    available_qty = get_stock_balance(row.item_code, warehouse)
    if float(available_qty or 0) < 1:
        frappe.throw(_("The selected Warehouse does not have one available stock unit."))
    mapping = frappe.db.get_value(
        "Equipment Model",
        row.equipment_model,
        ["stock_item", "fixed_asset_item", "company", "disabled", "allow_demo"],
        as_dict=True,
        for_update=True,
    )
    if (
        not mapping
        or mapping.stock_item != row.item_code
        or mapping.fixed_asset_item != row.fixed_asset_item
        or mapping.disabled
        or not mapping.allow_demo
        or (mapping.company and mapping.company != company)
    ):
        frappe.throw(_("The Equipment Model mapping is no longer eligible."))
    target_location = frappe.db.get_value("Company", company, "demo_asset_pool_location")
    if not target_location:
        frappe.throw(_("Company Demo asset pool Location is required."))
    payload = {
        "doctype": "Stock Asset Conversion",
        "company": company,
        "material_request_fulfillment": fulfillment,
        "fulfillment_allocation": allocation,
        "operation_id": operation_id,
        "target_asset_item": row.fixed_asset_item,
        "asset_category": frappe.db.get_value("Item", row.fixed_asset_item, "asset_category"),
        "target_location": target_location,
        "items": [
            {
                "item_code": row.item_code,
                "warehouse": warehouse,
                "qty": 1,
                "serial_and_batch_bundle": serial_and_batch_bundle,
            }
        ],
    }
    old_flag = getattr(frappe.flags, "stock_asset_conversion_handoff", False)
    frappe.flags.stock_asset_conversion_handoff = True
    try:
        doc = frappe.get_doc(payload).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Material Request Fulfillment Allocation",
            allocation,
            {
                "conversion_state": "Draft",
                "conversion_source_warehouse": warehouse,
                "conversion_source_bundle": serial_and_batch_bundle,
                "downstream_doctype": "Stock Asset Conversion",
                "downstream_reference": doc.name,
            },
            update_modified=False,
        )
        return {"data": doc.name, "message": _("Stock Asset Conversion draft created.")}
    except frappe.DuplicateEntryError:
        winner = frappe.db.get_value("Stock Asset Conversion", {"operation_id": operation_id}, "name")
        if winner:
            return {"data": winner, "message": _("Stock Asset Conversion already exists.")}
        raise
    finally:
        frappe.flags.stock_asset_conversion_handoff = old_flag


def _locked_demo_context(fulfillment: str) -> tuple[Document, list[frappe._dict]]:
    """Lock and revalidate the exact latest Demo plan and its unit allocations."""
    plan = _require_stock_access(fulfillment)
    request = frappe.db.get_value(
        "Material Request",
        plan.get("material_request"),
        ["name", "company", "docstatus", "request_usage", "responsible_employee"],
        as_dict=True,
        for_update=True,
    )
    if (
        not request
        or request.docstatus != 1
        or request.request_usage != "Customer Demo"
        or request.company != plan.get("company")
    ):
        frappe.throw(_("The linked Material Request is no longer an active Demo request."))
    latest = frappe.db.get_value(
        "Material Request Fulfillment",
        {"material_request": request.name, "status": "Planned"},
        ["name", "company", "plan_revision"],
        order_by="plan_revision desc",
        as_dict=True,
        for_update=True,
    )
    if not latest or latest.name != plan.name or latest.company != request.company:
        frappe.throw(_("The Fulfillment is no longer the latest active plan."))

    names = frappe.get_all(
        "Material Request Fulfillment Allocation",
        filters={"parent": plan.name},
        order_by="idx asc",
        pluck="name",
    )
    rows: list[frappe._dict] = []
    for name in names:
        row = frappe.db.get_value(
            "Material Request Fulfillment Allocation", name, "*", as_dict=True, for_update=True
        )
        if row:
            rows.append(row)
    if not rows:
        frappe.throw(_("The Demo Fulfillment has no allocations."))

    requested = frappe.get_all(
        "Material Request Item",
        filters={"parent": request.name},
        fields=["name", "stock_qty"],
        order_by="idx asc",
    )
    requested_qty = {row.name: float(row.stock_qty) for row in requested}
    allocated_qty: dict[str, float] = {}
    for row in rows:
        material_request_item = cast(str, row.get("material_request_item"))
        allocated_qty[material_request_item] = allocated_qty.get(material_request_item, 0) + float(
            row.get("qty") or 0
        )
    if requested_qty != allocated_qty:
        frappe.throw(_("Fulfillment allocations do not exactly match the Demo request."))
    return plan, rows


def _dispatchable_demo_context(
    fulfillment: str, *, after_issue: bool = False
) -> tuple[Document, list[frappe._dict]]:
    plan, rows = _locked_demo_context(fulfillment)
    if any(
        float(row.get("qty") or 0) != 1
        or not row.resolved_asset
        or row.lifecycle_state not in (None, "Ready")
        for row in rows
    ):
        frappe.throw(_("Every allocation must resolve to one ready unit Asset before dispatch."))
    assets = [cast(str, row.resolved_asset) for row in rows]
    if len(assets) != len(set(assets)):
        frappe.throw(_("Each Demo allocation must resolve to a unique Asset."))
    pool_location = frappe.db.get_value("Company", plan.get("company"), "demo_asset_pool_location")
    if not pool_location:
        frappe.throw(_("Company Demo asset pool Location is required."))
    responsible_employee = frappe.db.get_value(
        "Material Request", plan.get("material_request"), "responsible_employee"
    )
    for asset in sorted(assets):
        values = frappe.db.get_value(
            "Asset",
            asset,
            ["company", "docstatus", "status", "location", "custodian"],
            as_dict=True,
            for_update=True,
        )
        if (
            not values
            or values.company != plan.get("company")
            or values.docstatus != 1
            or values.status in FORBIDDEN_ASSET_STATUSES
            or values.location != pool_location
            or (values.custodian != responsible_employee if after_issue else bool(values.custodian))
        ):
            frappe.throw(_("A resolved Asset is no longer eligible for dispatch."))
        if _has_outstanding_dispatch(asset):
            frappe.throw(_("A resolved Asset already has an outstanding Dispatch."))
    for row in rows:
        if row.source_type not in {"Existing Asset", "Returning Asset"}:
            continue
        reservation = frappe.db.get_value(
            "Demo Asset Reservation",
            row.asset_reservation,
            ["asset", "status", "active_asset_key"],
            as_dict=True,
            for_update=True,
        )
        if (
            not reservation
            or reservation.asset != row.resolved_asset
            or reservation.status != "Active"
            or reservation.active_asset_key != row.resolved_asset
        ):
            frappe.throw(_("A Demo Asset reservation is no longer active."))
    return plan, rows


def _locked_demo_outbound(dispatch: str) -> tuple[Document, Document, list[Document]]:
    locked = frappe.db.get_value(
        "Dispatch",
        dispatch,
        ["name", "company", "material_request", "docstatus", "dispatch_type", "delivery_status"],
        as_dict=True,
        for_update=True,
    )
    if (
        not locked
        or locked.docstatus != 1
        or locked.dispatch_type != "Outbound"
        or locked.delivery_status != "Delivered"
    ):
        frappe.throw(_("Only a delivered Demo Outbound Dispatch can start a return."))
    outbound = cast(Document, frappe.get_doc("Dispatch", locked.name))
    linked_rows = [row for row in outbound.get("transfers", []) if row.get("fulfillment_allocation")]
    if not linked_rows or len(linked_rows) != len(outbound.get("transfers", [])):
        frappe.throw(_("The Outbound Dispatch is not an exact Demo allocation Dispatch."))
    fulfillment_names = {
        frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            row.get("fulfillment_allocation"),
            "parent",
            for_update=True,
        )
        for row in sorted(linked_rows, key=lambda value: cast(str, value.get("fulfillment_allocation")))
    }
    if len(fulfillment_names) != 1 or None in fulfillment_names:
        frappe.throw(_("The Outbound Dispatch mixes unrelated Demo allocations."))
    plan, allocations = _locked_demo_context(cast(str, next(iter(fulfillment_names))))
    if plan.get("material_request") != outbound.get("material_request"):
        frappe.throw(_("The Outbound Dispatch does not match the active Demo plan."))
    allocation_by_name = {row.name: row for row in allocations}
    linked_names = {cast(str, row.get("fulfillment_allocation")) for row in linked_rows}
    if linked_names != set(allocation_by_name):
        frappe.throw(_("The Outbound Dispatch does not contain the complete Demo allocation set."))
    for row in linked_rows:
        allocation = allocation_by_name[cast(str, row.get("fulfillment_allocation"))]
        if (
            row.get("asset") != allocation.resolved_asset
            or row.get("material_request_item") != allocation.material_request_item
            or float(row.get("qty") or 0) != 1
            or allocation.lifecycle_state not in {"Delivered", "Sold"}
        ):
            frappe.throw(_("The Outbound Dispatch no longer matches its Demo allocation."))
    returnable_names = {
        row.name
        for row in allocations
        if row.lifecycle_state == "Delivered" and not row.current_sales_invoice
    }
    if not returnable_names:
        frappe.throw(_("No remaining delivered Demo allocation is available for return."))
    return_rows = [row for row in linked_rows if row.get("fulfillment_allocation") in returnable_names]
    if {row.get("fulfillment_allocation") for row in return_rows} != returnable_names:
        frappe.throw(_("The Outbound Dispatch does not contain every returnable Demo allocation."))
    return outbound, plan, return_rows


@frappe.whitelist(methods=["POST"])
def prepare_demo_outbound_movement(fulfillment: str) -> dict[str, Any]:
    plan, rows = _dispatchable_demo_context(fulfillment)
    existing = frappe.db.get_value(
        "Asset Movement",
        {
            "reference_doctype": "Material Request Fulfillment",
            "reference_name": fulfillment,
            "purpose": "Issue",
            "docstatus": ("<", 2),
        },
        "name",
    )
    if existing:
        return {"data": existing, "message": _("Outbound Asset Movement already exists.")}
    employee = frappe.db.get_value("Material Request", plan.get("material_request"), "responsible_employee")
    if not employee:
        frappe.throw(_("A responsible Employee is required for Demo dispatch."))
    movement = frappe.get_doc(
        {
            "doctype": "Asset Movement",
            "company": plan.get("company"),
            "purpose": "Issue",
            "transaction_date": now_datetime(),
            "material_request": plan.get("material_request"),
            "reference_doctype": "Material Request Fulfillment",
            "reference_name": fulfillment,
        }
    )
    for row in rows:
        location = frappe.db.get_value("Asset", row.resolved_asset, "location")
        movement.append(
            "assets",
            {"asset": row.resolved_asset, "source_location": location, "to_employee": employee},
        )
    movement.insert()
    for row in rows:
        frappe.db.set_value(
            "Material Request Fulfillment Allocation",
            row.name,
            "asset_movement",
            movement.name,
            update_modified=False,
        )
    return {"data": movement.name, "message": _("Outbound Asset Movement draft created.")}


@frappe.whitelist(methods=["POST"])
def prepare_demo_outbound_dispatch(fulfillment: str, delivery_address: str) -> dict[str, Any]:
    plan, rows = _dispatchable_demo_context(fulfillment, after_issue=True)
    delivery_address = (delivery_address or "").strip()
    if not delivery_address:
        frappe.throw(_("Delivery Address is required."))
    movement = frappe.db.get_value(
        "Asset Movement",
        {
            "reference_doctype": "Material Request Fulfillment",
            "reference_name": fulfillment,
            "purpose": "Issue",
            "docstatus": 1,
        },
        ["name", "material_request", "company"],
        as_dict=True,
    )
    if (
        not movement
        or movement.material_request != plan.get("material_request")
        or movement.company != plan.get("company")
    ):
        frappe.throw(_("Submit the outbound Asset Movement before creating Dispatch."))
    existing = frappe.db.get_value(
        "Dispatch",
        {
            "material_request": plan.get("material_request"),
            "dispatch_type": "Outbound",
            "docstatus": ("<", 2),
        },
        "name",
    )
    if existing:
        return {"data": existing, "message": _("Outbound Dispatch draft already exists.")}
    dispatch = frappe.get_doc(
        {
            "doctype": "Dispatch",
            "company": plan.get("company"),
            "material_request": plan.get("material_request"),
            "dispatch_type": "Outbound",
            "delivery_status": "Draft",
            "delivery_address": delivery_address,
        }
    )
    for row in rows:
        item = frappe.db.get_value(
            "Material Request Item", row.material_request_item, ["item_code", "stock_uom"], as_dict=True
        )
        dispatch.append(
            "transfers",
            {
                "material_request_item": row.material_request_item,
                "fulfillment_allocation": row.name,
                "item_code": item.item_code,
                "asset": row.resolved_asset,
                "qty": 1,
                "uom": item.stock_uom,
                "reference_doctype": "Asset Movement",
                "reference_name": movement.name,
                "original_source_location": frappe.db.get_value("Asset", row.resolved_asset, "location"),
            },
        )
    dispatch.insert()
    return {"data": dispatch.name, "message": _("Outbound Dispatch draft created.")}


@frappe.whitelist(methods=["POST"])
def prepare_demo_return_movement(dispatch: str) -> dict[str, Any]:
    outbound, plan, rows = _locked_demo_outbound(dispatch)
    existing = frappe.db.get_value(
        "Asset Movement",
        {
            "reference_doctype": "Dispatch",
            "reference_name": dispatch,
            "purpose": "Receipt",
            "docstatus": ("<", 2),
        },
        "name",
    )
    if existing:
        return {"data": existing, "message": _("Return Asset Movement already exists.")}
    hold = frappe.db.get_value("Company", outbound.get("company"), "return_qa_hold_location")
    if not hold:
        frappe.throw(_("Configure the Return QA Hold Location before preparing a return."))
    movement = frappe.get_doc(
        {
            "doctype": "Asset Movement",
            "company": outbound.get("company"),
            "purpose": "Receipt",
            "transaction_date": now_datetime(),
            "material_request": plan.get("material_request"),
            "reference_doctype": "Dispatch",
            "reference_name": dispatch,
        }
    )
    for row in rows:
        movement.append("assets", {"asset": row.get("asset"), "target_location": hold})
    movement.insert()
    return {"data": movement.name, "message": _("Return Asset Movement draft created.")}


@frappe.whitelist(methods=["POST"])
def prepare_demo_return_dispatch(dispatch: str) -> dict[str, Any]:
    outbound, plan, rows = _locked_demo_outbound(dispatch)
    movement = frappe.db.get_value(
        "Asset Movement",
        {
            "reference_doctype": "Dispatch",
            "reference_name": dispatch,
            "purpose": "Receipt",
            "docstatus": 1,
        },
        ["name", "material_request", "company"],
        as_dict=True,
    )
    if (
        not movement
        or movement.material_request != plan.get("material_request")
        or movement.company != plan.get("company")
    ):
        frappe.throw(_("Submit the return Asset Movement before creating Return Dispatch."))
    existing = frappe.db.get_value(
        "Dispatch",
        {"original_dispatch": dispatch, "dispatch_type": "Return", "docstatus": ("<", 2)},
        "name",
    )
    if existing:
        return {"data": existing, "message": _("Return Dispatch draft already exists.")}
    result = frappe.get_doc(
        {
            "doctype": "Dispatch",
            "company": outbound.get("company"),
            "material_request": outbound.get("material_request"),
            "dispatch_type": "Return",
            "original_dispatch": dispatch,
            "delivery_status": "Draft",
            "delivery_address": outbound.get("delivery_address"),
        }
    )
    for row in rows:
        result.append(
            "transfers",
            {
                "material_request_item": row.get("material_request_item"),
                "fulfillment_allocation": row.get("fulfillment_allocation"),
                "item_code": row.get("item_code"),
                "asset": row.get("asset"),
                "qty": 1,
                "uom": row.get("uom"),
                "reference_doctype": "Asset Movement",
                "reference_name": movement.name,
                "against_dispatch_transfer": row.name,
                "original_source_location": row.get("original_source_location"),
            },
        )
    result.insert()
    return {"data": result.name, "message": _("Return Dispatch draft created.")}


@frappe.whitelist(methods=["POST"])
def release_asset_reservation(fulfillment: str, reservation: str) -> dict[str, Any]:
    plan = _require_stock_access(fulfillment)
    config = _company_configuration(cast(str, plan.get("company")))
    hold = frappe.db.get_value(
        "Demo Asset Reservation",
        reservation,
        ["name", "status", "asset"],
        as_dict=True,
    )
    if (
        not hold
        or hold.status != "Active"
        or not any(
            row.get("asset_reservation") == reservation
            for row in cast(list[Any], plan.get("allocations", []))
        )
    ):
        frappe.throw(_("Select an active reservation from this Fulfillment."))
    return {
        "data": _build_replan(
            plan,
            [{"reservation": reservation}],
            config,
            "Release Reservation",
        ),
        "message": _("Asset reservation released into a new plan revision."),
    }
