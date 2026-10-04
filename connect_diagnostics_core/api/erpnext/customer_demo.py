# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.model.document import Document
from frappe.utils import today

CUSTOMER_DEMO = "Customer Demo"
CLAIM_DOCTYPE = "Customer Demo Asset Claim"
CANDIDATE_DOCTYPE = "Material Request Customer Demo Candidate"
NON_TRANSFERABLE_STATUSES = (
    "Draft",
    "Scrapped",
    "Sold",
    "Capitalized",
    "In Maintenance",
    "Out of Order",
)


def validate_material_request(doc: Document, method: str) -> None:
    """Validate Customer Demo fields and standard Material Request item rows."""
    if doc.get("material_request_type") != CUSTOMER_DEMO:
        if any(
            doc.get(fieldname)
            for fieldname in (
                "demo_customer",
                "demo_source_location",
                "demo_target_location",
                "demo_status",
                "demo_candidates",
            )
        ):
            frappe.throw(_("Customer Demo fields can only be used on Customer Demo requests."))
        return

    if doc.get("asset_transfer_assets"):
        frappe.throw(_("Customer Demo requests must use the standard Items table."))
    rows = doc.get("items") or []
    if not rows:
        frappe.throw(_("Add at least one Fixed Asset Item to the Customer Demo request."))

    customer = _text(doc.get("demo_customer"))
    if doc.docstatus == 0 and (
        doc.get("demo_status") or doc.get("demo_candidates") or doc.get("demo_hold_reason")
    ):
        frappe.throw(_("Use the Hold action after submitting the Customer Demo request."))
    source_location = _text(doc.get("demo_source_location"))
    target_location = _text(doc.get("demo_target_location"))
    if not customer or not source_location or not target_location:
        frappe.throw(_("Set Customer, Source Location, and Customer Location."))
    frappe.has_permission("Customer", "read", customer, throw=True)
    frappe.has_permission("Location", "read", source_location, throw=True)
    frappe.has_permission("Location", "read", target_location, throw=True)
    if source_location == target_location:
        frappe.throw(_("Source Location and Customer Location must be different."))
    _validate_leaf_locations(source_location, target_location)

    source = frappe.db.get_value(
        "Location", source_location, ["custom_party_type", "custom_party_name"], as_dict=True
    )
    if source and source.custom_party_type in ("Customer", "Supplier"):
        frappe.throw(_("Source Location must be an internal company Location."))

    target = frappe.db.get_value(
        "Location", target_location, ["custom_party_type", "custom_party_name"], as_dict=True
    )
    if not target or target.custom_party_type != "Customer" or target.custom_party_name != customer:
        frappe.throw(_("Customer Location must belong to the selected Customer."))

    item_codes: set[str] = set()
    for row in rows:
        item_code = _text(row.get("item_code"))
        _validate_demo_item_quantity(row, item_code)
        frappe.has_permission("Item", "read", item_code, throw=True)
        if item_code in item_codes:
            frappe.throw(_("Use one row per Fixed Asset Item in a Customer Demo request."))
        item_codes.add(item_code)

        fixed_item = frappe.db.get_value(
            "Item",
            item_code,
            ["is_fixed_asset", "is_stock_item", "stock_uom", "demo_stock_item"],
            as_dict=True,
        )
        if not fixed_item or not fixed_item.is_fixed_asset or fixed_item.is_stock_item:
            frappe.throw(_("Customer Demo items must be non-stock Fixed Asset Items."))
        if row.get("stock_uom") != fixed_item.stock_uom:
            frappe.throw(_("Request the Fixed Asset Item in its Stock UOM."))

        source_stock_item = _text(fixed_item.demo_stock_item)
        source_warehouse = _text(doc.get("set_warehouse"))
        if not source_stock_item:
            frappe.throw(
                _(
                    "Set a Paired Stock Item on Fixed Asset Item {0} before requesting a Customer Demo."
                ).format(item_code)
            )
        frappe.has_permission("Item", "read", source_stock_item, throw=True)
        stock_item = frappe.db.get_value(
            "Item", source_stock_item, ["is_stock_item", "disabled", "stock_uom"], as_dict=True
        )
        if not stock_item or not stock_item.is_stock_item or stock_item.disabled:
            frappe.throw(_("Paired Item {0} must be an enabled Stock Item.").format(source_stock_item))
        if stock_item.stock_uom != row.get("stock_uom"):
            frappe.throw(_("Paired Stock Item and Fixed Asset Item must use the same Stock UOM."))
        if not source_warehouse:
            frappe.throw(_("Select a Source Warehouse on the Material Request."))
        _validate_warehouse(source_warehouse, doc.get("company"))
        frappe.has_permission("Warehouse", "read", source_warehouse, throw=True)

    if doc.docstatus == 1 and doc.name:
        stored = frappe.db.get_value(
            "Material Request",
            doc.name,
            ["demo_status", "demo_hold_reason"],
            as_dict=True,
        )
        stored_candidates = frappe.get_all(
            CANDIDATE_DOCTYPE,
            filters={"parent": doc.name},
            fields=["material_request_item", "asset"],
            order_by="idx asc",
        )
        current_candidates = [
            {"material_request_item": row.get("material_request_item"), "asset": row.get("asset")}
            for row in doc.get("demo_candidates") or []
        ]
        state_changed = bool(
            stored
            and (
                doc.get("demo_status") != stored.demo_status
                or doc.get("demo_hold_reason") != stored.demo_hold_reason
                or current_candidates != stored_candidates
            )
        )
        if state_changed and not getattr(frappe.flags, "customer_demo_action", False):
            frappe.throw(_("Use the Customer Demo Hold action to change Hold status or Candidate Assets."))

    if doc.get("demo_status") == "Hold":
        if not _text(doc.get("demo_hold_reason")) or not (doc.get("demo_candidates") or []):
            frappe.throw(_("A Hold reason and at least one Candidate Asset are required."))
        for candidate in doc.get("demo_candidates") or []:
            claim = frappe.db.get_value(
                CLAIM_DOCTYPE,
                candidate.get("asset"),
                ["material_request", "material_request_item"],
                as_dict=True,
            )
            if (
                not claim
                or claim.material_request != doc.name
                or claim.material_request_item != candidate.get("material_request_item")
            ):
                if not getattr(frappe.flags, "customer_demo_action", False):
                    frappe.throw(_("Every Hold Candidate Asset must have an active claim for this request."))


def after_submit_material_request(doc: Document, method: str) -> None:
    """Initialize the Customer Demo status without changing ERPNext's native status."""
    if doc.get("material_request_type") == CUSTOMER_DEMO and not doc.get("demo_status"):
        doc.db_set("demo_status", "Ready", update_modified=True)


def before_cancel_material_request(doc: Document, method: str) -> None:
    """Release exact Asset claims atomically when their Customer Demo request is cancelled."""
    if doc.get("material_request_type") != CUSTOMER_DEMO:
        return
    linked_movements = frappe.get_all(
        "Asset Movement",
        filters={
            "reference_doctype": "Material Request",
            "reference_name": doc.name,
            "docstatus": ["<", 2],
        },
        pluck="name",
        limit_page_length=1,
    )
    linked_returns = frappe.get_all(
        "Asset Movement",
        filters={"demo_return_for_material_request": doc.name, "docstatus": ["<", 2]},
        pluck="name",
        limit_page_length=1,
    )
    linked_capitalizations = frappe.get_all(
        "Asset Capitalization",
        filters={"demo_material_request": doc.name, "docstatus": ["<", 2]},
        pluck="name",
        limit_page_length=1,
    )
    if linked_movements or linked_returns or linked_capitalizations:
        frappe.throw(
            _("Cancel linked Asset Movements and Asset Capitalizations before cancelling this request.")
        )
    claim_assets = frappe.get_all(CLAIM_DOCTYPE, filters={"material_request": doc.name}, pluck="asset")
    _lock_asset_rows(claim_assets)
    for asset_name in claim_assets:
        claim = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        if claim == doc.name:
            frappe.delete_doc(CLAIM_DOCTYPE, asset_name, ignore_permissions=True, force=True)


@frappe.whitelist()
def hold_customer_demo_request(
    material_request: str, reason: str, candidates: str | list[dict[str, str]]
) -> dict[str, Any]:
    """Hold a submitted Customer Demo request and exclusively claim exact candidate Assets."""
    if not isinstance(material_request, str) or not material_request.strip():
        frappe.throw(_("Material Request is required."))
    frappe.has_permission("Material Request", "write", material_request, throw=True)
    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1 or doc.get("material_request_type") != CUSTOMER_DEMO:
        frappe.throw(_("Only a submitted Customer Demo request can be put on Hold."))
    reason = _text(reason)
    if not reason:
        frappe.throw(_("Enter why this Customer Demo request is on Hold."))

    candidate_rows = _parse_candidates(candidates)
    if not candidate_rows:
        frappe.throw(_("Select at least one Candidate Asset."))
    request_rows = {row.name: row for row in doc.get("items") or []}
    seen_assets: set[str] = set()
    for candidate in candidate_rows:
        request_item = candidate.get("material_request_item")
        asset_name = candidate.get("asset")
        if request_item not in request_rows or not asset_name:
            frappe.throw(_("Each Candidate Asset must reference a row in this Material Request."))
        if asset_name in seen_assets:
            frappe.throw(_("A Candidate Asset can only appear once in this request."))
        seen_assets.add(asset_name)
        _validate_candidate_asset(doc, request_rows[request_item], asset_name)

    old_claim_assets = set(
        frappe.get_all(CLAIM_DOCTYPE, filters={"material_request": doc.name}, pluck="asset")
    )
    prior_claims = (
        frappe.get_all(
            CLAIM_DOCTYPE,
            filters={"asset": ["in", sorted(old_claim_assets | seen_assets)]},
            fields=["material_request"],
        )
        if old_claim_assets or seen_assets
        else []
    )
    _lock_request_rows(
        {doc.name, *(claim.material_request for claim in prior_claims if claim.material_request)}
    )
    _lock_asset_rows(old_claim_assets | seen_assets)
    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1 or doc.get("material_request_type") != CUSTOMER_DEMO:
        frappe.throw(_("Only a submitted Customer Demo request can be put on Hold."))
    request_rows = {row.name: row for row in doc.get("items") or []}
    for candidate in candidate_rows:
        if candidate["material_request_item"] not in request_rows:
            frappe.throw(_("Candidate Asset must reference a row in this Material Request."))
        _validate_candidate_asset(
            doc,
            request_rows[candidate["material_request_item"]],
            candidate["asset"],
        )
    _validate_hold_candidate_counts(doc, candidate_rows)
    for asset_name in sorted(seen_assets):
        current_claim = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        if current_claim and current_claim != doc.name:
            frappe.throw(
                _("Asset {0} is already a Candidate for another Customer Demo request.").format(asset_name)
            )

    for asset_name in sorted(old_claim_assets - seen_assets):
        frappe.delete_doc(CLAIM_DOCTYPE, asset_name, ignore_permissions=True, force=True)

    candidate_rows = [
        {
            **candidate,
            **_validate_candidate_asset(
                doc,
                request_rows[candidate["material_request_item"]],
                candidate["asset"],
            ),
        }
        for candidate in candidate_rows
    ]
    doc.set("demo_candidates", candidate_rows)
    doc.set("demo_hold_reason", reason)
    doc.set("demo_status", "Hold")
    for candidate in doc.get("demo_candidates") or []:
        asset_name = candidate.get("asset")
        request_item = candidate.get("material_request_item")
        existing_claim = frappe.db.get_value(
            CLAIM_DOCTYPE,
            asset_name,
            ["material_request", "material_request_item"],
            as_dict=True,
        )
        if existing_claim and existing_claim.material_request == doc.name:
            if existing_claim.material_request_item != request_item:
                claim_doc = frappe.get_doc(CLAIM_DOCTYPE, asset_name)
                claim_doc.set("material_request_item", request_item)
                claim_doc.save(ignore_permissions=True)
            continue
        frappe.flags.customer_demo_action = True
        try:
            claim_doc = frappe.get_doc(
                {
                    "doctype": CLAIM_DOCTYPE,
                    "asset": asset_name,
                    "material_request": doc.name,
                    "material_request_item": request_item,
                }
            )
            claim_doc.insert(ignore_permissions=True)
        finally:
            frappe.flags.pop("customer_demo_action", None)

    frappe.flags.customer_demo_action = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.pop("customer_demo_action", None)

    return {
        "data": {"demo_status": "Hold", "candidate_count": len(candidate_rows)},
        "message": _("Customer Demo request is on Hold."),
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_demo_fixed_asset_item_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Search enabled non-stock Fixed Asset Items while respecting Item permissions."""
    if doctype != "Item":
        return []
    permission_type = "select" if frappe.only_has_select_perm("Item") else "read"
    if not frappe.has_permission("Item", ptype=permission_type):
        return []
    query = (
        "select name, item_name from `tabItem` "
        "where is_fixed_asset = 1 and is_stock_item = 0 and disabled = 0 "
        "and (name like %(txt)s or item_name like %(txt)s) "
        + get_match_cond("Item")
        + " order by item_name, name limit %(page_len)s offset %(start)s"
    )
    return [
        (row[0], row[1])
        for row in frappe.db.sql(
            query,
            {"txt": f"%{txt}%", "page_len": page_len, "start": start},
        )
    ]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_demo_candidate_asset_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Search submitted Assets currently out on another Customer's submitted Demo."""
    filters = dict(filters or {})
    company = _text(filters.get("company"))
    item_code = _text(filters.get("item_code"))
    exclude_customer = _text(filters.get("exclude_customer"))
    if doctype != "Asset" or not company or not item_code or not exclude_customer:
        return []
    permission_type = "select" if frappe.only_has_select_perm("Asset") else "read"
    if not frappe.has_permission("Asset", ptype=permission_type):
        return []

    asset_match_condition = get_match_cond("Asset").replace("tabAsset", "asset")
    query = (
        "select asset.name, asset.asset_name, location.custom_party_name, location.name from `tabAsset` asset "
        "inner join `tabLocation` location on location.name = asset.location "
        "inner join `tabAsset Movement Item` current_item on current_item.asset = asset.name "
        "inner join `tabAsset Movement` current_movement on current_movement.name = current_item.parent "
        "inner join `tabMaterial Request` source_request on source_request.name = current_movement.reference_name "
        "where asset.company = %(company)s and asset.item_code = %(item_code)s "
        "and asset.docstatus = 1 and asset.status not in "
        "('Draft', 'Scrapped', 'Sold', 'Capitalized', 'In Maintenance', 'Out of Order') "
        "and location.is_group = 0 and location.custom_party_type = 'Customer' "
        "and location.custom_party_name != %(exclude_customer)s "
        "and asset.location = current_item.target_location and current_movement.docstatus = 1 "
        "and current_movement.purpose = 'Transfer' and current_movement.reference_doctype = 'Material Request' "
        "and source_request.docstatus = 1 and source_request.material_request_type = 'Customer Demo' "
        "and source_request.demo_customer = location.custom_party_name "
        "and source_request.demo_target_location = location.name "
        "and not exists (select later_movement.name from `tabAsset Movement Item` later_item "
        "inner join `tabAsset Movement` later_movement on later_movement.name = later_item.parent "
        "where later_item.asset = asset.name and later_movement.docstatus = 1 and "
        "(later_movement.transaction_date > current_movement.transaction_date or "
        "(later_movement.transaction_date = current_movement.transaction_date "
        "and later_movement.creation > current_movement.creation))) "
        "and (asset.name like %(txt)s or asset.asset_name like %(txt)s) "
        + asset_match_condition
        + " order by asset.asset_name, asset.name limit %(page_len)s offset %(start)s"
    )
    results: list[tuple[str, str]] = []
    for row in frappe.db.sql(
        query,
        {
            "company": company,
            "item_code": item_code,
            "exclude_customer": exclude_customer,
            "txt": f"%{txt}%",
            "page_len": page_len,
            "start": start,
        },
    ):
        if not frappe.has_permission("Location", "read", row[3]):
            continue
        if not frappe.has_permission("Customer", "read", row[2]):
            continue
        results.append((row[0], _("{0} — {1} — {2}").format(row[1], row[2], row[3])))
    return results


@frappe.whitelist()
def get_customer_demo_asset_capitalization_drafts(material_request: str) -> dict[str, Any]:
    """Create Draft individual Assets and native Asset Capitalizations from paired stock."""
    doc = _get_submitted_demo_request(material_request, "read")
    frappe.has_permission("Material Request", "write", material_request, throw=True)
    frappe.has_permission("Asset", "create", throw=True)
    frappe.has_permission("Asset Capitalization", "create", throw=True)
    frappe.db.sql("SELECT name FROM `tabMaterial Request` WHERE name = %s FOR UPDATE", (material_request,))
    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1 or doc.material_request_type != CUSTOMER_DEMO:
        frappe.throw(_("Select a submitted Customer Demo Material Request."))

    created: list[dict[str, str]] = []
    waiting_for_stock: dict[str, int] = {}
    already_sent = _submitted_outbound_asset_names(doc.name)
    for row in doc.get("items") or []:
        frappe.has_permission("Item", "read", row.item_code, throw=True)
        fixed_item = frappe.get_cached_doc("Item", row.item_code)
        source_stock_item = _text(fixed_item.get("demo_stock_item"))
        if not source_stock_item:
            continue
        frappe.has_permission("Item", "read", source_stock_item, throw=True)
        target_qty = int(_number(row.stock_qty))
        sent_qty = _count_assets_by_item(already_sent, row.item_code)
        available_assets = _available_assets_for_row(doc, row, exclude=already_sent)
        claimed_assets = _returned_claim_assets(doc, row)
        available_assets.update(claimed_assets)
        existing_capitalized_assets = _capitalization_assets_for_row(doc.name, row.name)
        away_claims = _away_claim_assets(doc, row)
        needed = _required_capitalization_units(
            target_qty,
            sent_qty,
            available_assets,
            existing_capitalized_assets,
            away_claims,
        )
        source_warehouse = _text(doc.get("set_warehouse"))
        frappe.has_permission("Warehouse", "read", source_warehouse, throw=True)
        stock_qty = max(0, math.floor(_stock_balance(source_stock_item, source_warehouse)))
        capitalize_qty = min(needed, stock_qty)
        if needed > capitalize_qty:
            waiting_for_stock[row.name] = needed - capitalize_qty

        for unit_index in range(capitalize_qty):
            asset = frappe.get_doc(
                {
                    "doctype": "Asset",
                    "asset_name": _(
                        "{0} Customer Demo {1}"
                    ).format(frappe.db.get_value("Item", row.item_code, "item_name"), unit_index + 1),
                    "item_code": row.item_code,
                    "company": doc.company,
                    "location": doc.demo_source_location,
                    "purchase_date": today(),
                    "available_for_use_date": today(),
                    "asset_type": "Composite Asset",
                }
            )
            asset.insert()
            capitalization = frappe.get_doc(
                {
                    "doctype": "Asset Capitalization",
                    "company": doc.company,
                    "posting_date": today(),
                    "target_item_code": row.item_code,
                    "target_asset": asset.name,
                    "demo_material_request": doc.name,
                    "demo_material_request_item": row.name,
                    "stock_items": [
                        {
                            "item_code": source_stock_item,
                            "stock_qty": 1,
                            "warehouse": source_warehouse,
                        }
                    ],
                }
            )
            capitalization.insert()
            created.append({"asset": asset.name, "asset_capitalization": capitalization.name})

    message = _("Created {0} Asset Capitalization draft(s).").format(len(created))
    if waiting_for_stock:
        message += " " + _("Some requested units are still waiting for stock or a returned Candidate Asset.")
    return {
        "data": {"drafts": created, "waiting_for_stock": waiting_for_stock},
        "message": message,
    }


@frappe.whitelist()
def submit_customer_demo_capitalized_assets(material_request: str) -> dict[str, Any]:
    """Submit target Assets after their native Asset Capitalization has been submitted."""
    doc = _get_submitted_demo_request(material_request, "write")
    capitalization_names = frappe.get_list(
        "Asset Capitalization",
        filters={"demo_material_request": doc.name, "docstatus": 1},
        pluck="name",
        limit_page_length=1000,
    )
    asset_names = list(
        dict.fromkeys(
            asset_name
            for capitalization_name in capitalization_names
            if (
                asset_name := frappe.db.get_value("Asset Capitalization", capitalization_name, "target_asset")
            )
        )
    )
    submitted: list[str] = []
    for asset_name in asset_names:
        if frappe.db.get_value("Asset", asset_name, "docstatus") == 1:
            continue
        frappe.has_permission("Asset", "submit", asset_name, throw=True)
        asset = frappe.get_doc("Asset", asset_name)
        if asset.docstatus != 0:
            frappe.throw(_("Asset {0} must be a Draft Asset before submission.").format(asset_name))
        asset.submit()
        submitted.append(asset_name)
    return {"data": {"assets": submitted}, "message": _("Capitalized Assets are submitted.")}


@frappe.whitelist()
def get_customer_demo_asset_movement_draft(material_request: str) -> dict[str, Any]:
    """Return a draft payload for the remaining Customer Demo outbound Asset units."""
    doc = _get_submitted_demo_request(material_request, "read")
    if doc.get("demo_status") == "Hold":
        frappe.throw(_("Wait for every Candidate Asset to return before creating an outbound Movement."))
    frappe.has_permission("Asset Movement", "create", throw=True)
    frappe.has_permission("Asset Movement", "read", throw=True)

    existing = frappe.get_all(
        "Asset Movement",
        filters={
            "reference_doctype": "Material Request",
            "reference_name": doc.name,
            "demo_return_for_material_request": ["is", "not set"],
            "docstatus": 0,
        },
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if existing:
        frappe.has_permission("Asset Movement", "read", existing[0].name, throw=True)
        return {
            "data": {"existing_asset_movement": existing[0].name},
            "message": _("An Asset Movement draft already exists."),
        }

    assets: list[dict[str, Any]] = []
    sent_names = _submitted_outbound_asset_names(doc.name)
    for request_row in doc.get("items") or []:
        target_qty = int(_number(request_row.stock_qty))
        already_sent_for_row = _count_assets_by_item(sent_names, request_row.item_code)
        needed = max(0, target_qty - already_sent_for_row)
        candidate_assets = sorted(_returned_claim_assets(doc, request_row))
        candidates = _available_assets_for_row(doc, request_row, exclude=sent_names)
        candidates.update(candidate_assets)
        selected_assets = candidate_assets[:needed]
        remaining = max(0, needed - len(selected_assets))
        selected_assets.extend(
            asset_name for asset_name in sorted(candidates - set(selected_assets))[:remaining]
        )
        for asset_name in selected_assets:
            frappe.has_permission("Asset", "read", asset_name, throw=True)
            asset_data = frappe.db.get_value(
                "Asset",
                asset_name,
                ["name", "asset_name", "custodian", "department", "territory"],
                as_dict=True,
            )
            if not asset_data:
                continue
            assets.append(
                {
                    "doctype": "Asset Movement Item",
                    "asset": asset_name,
                    "asset_name": asset_data.asset_name,
                    "source_location": doc.demo_source_location,
                    "target_location": doc.demo_target_location,
                    "from_employee": asset_data.custodian,
                    "to_employee": asset_data.custodian,
                    "department": asset_data.department,
                    "territory": asset_data.territory,
                }
            )
    if not assets:
        frappe.throw(
            _(
                "No submitted eligible Assets are available. Capitalize paired stock or wait for Candidate Assets."
            )
        )

    return {
        "data": {
            "doctype": "Asset Movement",
            "company": doc.company,
            "purpose": "Transfer",
            "reference_doctype": "Material Request",
            "reference_name": doc.name,
            "assets": assets,
        },
        "message": _("Customer Demo Asset Movement draft is ready."),
    }


@frappe.whitelist()
def get_customer_demo_return_movement_draft(material_request: str, assets: str | list[str]) -> dict[str, Any]:
    """Return a Transfer draft payload to receive Assets from a submitted Customer Demo."""
    doc = _get_submitted_demo_request(material_request, "read")
    frappe.has_permission("Asset Movement", "create", throw=True)
    asset_names = _parse_asset_names(assets)
    if not asset_names:
        frappe.throw(_("Select at least one Asset to return."))

    rows: list[dict[str, Any]] = []
    for asset_name in asset_names:
        frappe.has_permission("Asset", "read", asset_name, throw=True)
        asset = frappe.db.get_value(
            "Asset",
            asset_name,
            ["name", "asset_name", "location", "company", "custodian", "department", "territory"],
            as_dict=True,
        )
        if not asset or asset.company != doc.company or asset.location != doc.demo_target_location:
            frappe.throw(_("Asset {0} is not currently at this Customer Demo Location.").format(asset_name))
        _validate_demo_outbound_provenance(doc, asset_name, doc.demo_target_location)
        claim = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        target_location = (
            frappe.db.get_value("Material Request", claim, "demo_source_location")
            if claim
            else doc.demo_source_location
        )
        rows.append(
            {
                "doctype": "Asset Movement Item",
                "asset": asset_name,
                "asset_name": asset.asset_name,
                "source_location": doc.demo_target_location,
                "target_location": target_location,
                "from_employee": asset.custodian,
                "to_employee": asset.custodian,
                "department": asset.department,
                "territory": asset.territory,
            }
        )

    return {
        "data": {
            "doctype": "Asset Movement",
            "company": doc.company,
            "purpose": "Transfer",
            "demo_return_for_material_request": doc.name,
            "assets": rows,
        },
        "message": _("Customer Demo return Asset Movement draft is ready."),
    }


def validate_customer_demo_asset_movement_reference(doc: Document, material_request: Document) -> None:
    """Validate an outbound Customer Demo Movement against its submitted request."""
    if material_request.docstatus != 1 or material_request.get("material_request_type") != CUSTOMER_DEMO:
        frappe.throw(_("Reference Document must be a submitted Customer Demo Material Request."))
    if material_request.company != doc.get("company") or doc.get("purpose") != "Transfer":
        frappe.throw(_("Customer Demo Asset Movement must be a same-company Transfer."))
    if doc.get("demo_return_for_material_request"):
        frappe.throw(_("Use Customer Demo Return For for a return Movement without an outbound reference."))
    if material_request.get("demo_status") not in ("Ready", "In Progress"):
        frappe.throw(_("Customer Demo request must be Ready before creating an outbound Asset Movement."))

    movement_rows = doc.get("assets") or []
    asset_names = [row.get("asset") for row in movement_rows]
    if not asset_names or any(not name for name in asset_names) or len(asset_names) != len(set(asset_names)):
        frappe.throw(_("Select each Asset only once in the Customer Demo Movement."))
    submitted_assets = _submitted_outbound_asset_names(material_request.name)
    if submitted_assets.intersection(asset_names):
        frappe.throw(_("An Asset already appears in a submitted Movement for this request."))

    request_by_item = {row.item_code: row for row in material_request.get("items") or []}
    quantities_sent = _submitted_outbound_counts(material_request.name)
    counts: dict[str, int] = {}
    for row in movement_rows:
        frappe.has_permission("Asset", "read", row.get("asset"), throw=True)
        asset = frappe.db.get_value(
            "Asset",
            row.get("asset"),
            ["item_code", "company", "docstatus", "status"],
            as_dict=True,
        )
        if (
            not asset
            or asset.docstatus != 1
            or asset.status in NON_TRANSFERABLE_STATUSES
            or asset.company != material_request.company
            or asset.item_code not in request_by_item
        ):
            frappe.throw(
                _("Asset {0} does not match a Fixed Asset Item on this request.").format(row.get("asset"))
            )
        request_row = request_by_item[asset.item_code]
        claim = frappe.db.get_value(
            CLAIM_DOCTYPE,
            row.get("asset"),
            ["material_request", "material_request_item"],
            as_dict=True,
        )
        if claim and (
            claim.material_request != material_request.name or claim.material_request_item != request_row.name
        ):
            frappe.throw(
                _("Asset {0} is reserved for another Customer Demo request.").format(row.get("asset"))
            )
        if (
            row.get("source_location") != material_request.demo_source_location
            or row.get("target_location") != material_request.demo_target_location
        ):
            frappe.throw(_("Movement Locations must match the Customer Demo request."))
        counts[asset.item_code] = counts.get(asset.item_code, 0) + 1

    for item_code, count in counts.items():
        request_row = request_by_item[item_code]
        if quantities_sent.get(item_code, 0) + count > int(_number(request_row.stock_qty)):
            frappe.throw(
                _("Movement quantity exceeds the Customer Demo request for Item {0}.").format(item_code)
            )

    returnable_claim_assets = {
        claim.asset
        for claim in frappe.get_all(
            CLAIM_DOCTYPE,
            filters={"material_request": material_request.name},
            fields=["asset"],
        )
        if _is_available_claim_asset(material_request, None, claim.asset)
    }
    if not returnable_claim_assets.issubset(set(asset_names)):
        frappe.throw(_("Include every returned Candidate Asset reserved for this request."))


def validate_customer_demo_return_movement(doc: Document, *, check_permission: bool = True) -> Document:
    """Validate provenance and exact locations for an inbound Customer Demo Movement."""
    request_name = _text(doc.get("demo_return_for_material_request"))
    if not request_name:
        frappe.throw(_("Select the Customer Demo request being returned."))
    if check_permission:
        frappe.has_permission("Material Request", "read", request_name, throw=True)
    request = frappe.get_doc("Material Request", request_name)
    if request.docstatus != 1 or request.material_request_type != CUSTOMER_DEMO:
        frappe.throw(_("Return source must be a submitted Customer Demo Material Request."))
    if doc.get("reference_doctype") == "Material Request":
        frappe.throw(_("A Customer Demo return Movement cannot reference its outbound Material Request."))
    if doc.get("company") != request.company or doc.get("purpose") != "Transfer":
        frappe.throw(_("Customer Demo return Movement must be a same-company Transfer."))
    rows = doc.get("assets") or []
    if not rows:
        frappe.throw(_("Add at least one Asset to return."))
    asset_names = [_text(row.get("asset")) for row in rows]
    if any(not asset_name for asset_name in asset_names) or len(asset_names) != len(set(asset_names)):
        frappe.throw(_("Select each Asset only once in a return Movement."))

    for row in rows:
        asset_name = _text(row.get("asset"))
        frappe.has_permission("Asset", "read", asset_name, throw=True)
        asset = frappe.db.get_value(
            "Asset", asset_name, ["docstatus", "status", "company", "location"], as_dict=True
        )
        if (
            not asset
            or asset.docstatus != 1
            or asset.status in NON_TRANSFERABLE_STATUSES
            or asset.company != request.company
            or asset.location != request.demo_target_location
        ):
            frappe.throw(
                _("Asset {0} is no longer transferable from this Customer Demo Location.").format(asset_name)
            )
        if row.get("source_location") != request.demo_target_location:
            frappe.throw(_("Return Movement Source Location must match the original Customer Demo request."))
        _validate_demo_outbound_provenance(request, asset_name, request.demo_target_location)
        claim_request = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        if claim_request:
            claimant_source = frappe.db.get_value("Material Request", claim_request, "demo_source_location")
            if row.get("target_location") != claimant_source:
                frappe.throw(_("Return the claimed Asset to the Source Location of its waiting request."))
        elif row.get("target_location") != request.demo_source_location:
            frappe.throw(_("Return Movement Target Location must match the original Customer Demo request."))
    return request


def guard_claimed_asset_movement(doc: Document, method: str) -> None:
    """Lock related requests before Assets and authorize only claimant flows."""
    movement_rows = doc.get("assets") or []
    asset_names = sorted({row.get("asset") for row in movement_rows if row.get("asset")})
    _lock_movement_context(doc, asset_names)
    if doc.get("demo_return_for_material_request"):
        validate_customer_demo_return_movement(doc, check_permission=False)
    elif doc.get("reference_doctype") == "Material Request" and doc.get("reference_name"):
        material_request = frappe.get_doc("Material Request", doc.reference_name)
        if material_request.get("material_request_type") == CUSTOMER_DEMO:
            validate_customer_demo_asset_movement_reference(doc, material_request)

    for row in movement_rows:
        asset_name = _text(row.get("asset"))
        if not asset_name:
            continue
        asset = frappe.db.get_value(
            "Asset", asset_name, ["docstatus", "status", "company", "location"], as_dict=True
        )
        if not asset or asset.company != doc.get("company"):
            frappe.throw(_("Asset {0} belongs to a different Company.").format(asset_name))
        if (
            doc.get("purpose") in ("Transfer", "Transfer and Issue")
            and row.get("source_location") != asset.location
        ):
            frappe.throw(_("Asset {0} is no longer at the selected Source Location.").format(asset_name))
        claim = frappe.db.get_value(
            CLAIM_DOCTYPE,
            asset_name,
            ["material_request", "material_request_item"],
            as_dict=True,
        )
        if not claim:
            continue
        if asset.docstatus != 1 or asset.status in NON_TRANSFERABLE_STATUSES:
            frappe.throw(_("Claimed Asset {0} is no longer transferable.").format(asset_name))
        claimant = frappe.db.get_value(
            "Material Request",
            claim.material_request,
            ["docstatus", "material_request_type", "company", "demo_source_location", "demo_target_location"],
            as_dict=True,
        )
        is_claimant_fulfillment = bool(
            claimant
            and claimant.docstatus == 1
            and claimant.material_request_type == CUSTOMER_DEMO
            and doc.get("reference_doctype") == "Material Request"
            and doc.get("reference_name") == claim.material_request
            and doc.get("purpose") == "Transfer"
            and row.get("source_location") == claimant.demo_source_location
            and row.get("target_location") == claimant.demo_target_location
            and asset.location == claimant.demo_source_location
        )
        is_validated_return = bool(
            doc.get("demo_return_for_material_request")
            and doc.get("purpose") == "Transfer"
            and row.get("source_location") == asset.location
            and row.get("target_location") == claimant.demo_source_location
        )
        if not is_claimant_fulfillment and not is_validated_return:
            frappe.throw(
                _("Asset {0} is reserved for Customer Demo request {1}.").format(
                    asset_name, claim.material_request
                )
            )


def lock_customer_demo_movement_before_cancel(doc: Document, method: str) -> None:
    """Use the same request-before-Asset lock order before ERPNext reverses a Movement."""
    asset_names = sorted({row.get("asset") for row in doc.get("assets") or [] if row.get("asset")})
    _lock_movement_context(doc, asset_names)


def guard_claimed_asset_cancel(doc: Document, method: str) -> None:
    """Prevent cancelling an Asset while another request holds its exact candidate claim."""
    _lock_asset_rows([doc.name])
    claim_request = frappe.db.get_value(CLAIM_DOCTYPE, doc.name, "material_request")
    if claim_request:
        frappe.throw(
            _("Asset {0} is reserved for Customer Demo request {1}.").format(doc.name, claim_request)
        )


def guard_demo_capitalization_cancel(doc: Document, method: str) -> None:
    """Require a target Asset to be Draft before cancelling its Demo capitalization."""
    if not doc.get("demo_material_request") or not doc.get("target_asset"):
        return
    asset = frappe.db.get_value("Asset", doc.target_asset, ["docstatus", "status"], as_dict=True)
    if asset and asset.docstatus == 1:
        frappe.throw(
            _("Cancel or amend Asset {0} before cancelling its Asset Capitalization.").format(
                doc.target_asset
            )
        )


def on_asset_movement_change(doc: Document, method: str) -> None:
    """Reconcile candidate claims after ERPNext updates Asset.location for a Movement."""
    asset_names = sorted({row.get("asset") for row in doc.get("assets") or [] if row.get("asset")})
    if not asset_names:
        return
    if doc.get("reference_doctype") == "Material Request" and doc.get("reference_name"):
        request = frappe.db.get_value(
            "Material Request",
            doc.reference_name,
            ["docstatus", "material_request_type"],
            as_dict=True,
        )
        if request and request.docstatus == 1 and request.material_request_type == CUSTOMER_DEMO:
            if method == "on_submit":
                _release_fulfilled_candidate_claims(doc.reference_name, asset_names)
            elif method == "on_cancel":
                _restore_candidate_claims(doc.reference_name, asset_names)
            _update_demo_fulfillment_status(doc.reference_name)

    request_names = frappe.get_all(
        CLAIM_DOCTYPE, filters={"asset": ["in", asset_names]}, pluck="material_request"
    )
    for request_name in sorted(set(request_names)):
        frappe.enqueue(
            "connect_diagnostics_core.api.erpnext.customer_demo.reconcile_customer_demo_claims",
            queue="short",
            timeout=60,
            enqueue_after_commit=True,
            job_id=f"customer-demo-claim-{doc.name}-{request_name}-{method}",
            deduplicate=True,
            material_request=request_name,
        )


def reconcile_customer_demo_claims(material_request: str) -> None:
    """Update Hold/Ready from current Asset locations and notify once per Ready transition."""
    _lock_request_rows([material_request])
    claims = frappe.get_all(
        CLAIM_DOCTYPE,
        filters={"material_request": material_request},
        fields=["asset"],
        order_by="asset asc",
    )
    if not claims:
        return
    _lock_asset_rows([claim.asset for claim in claims])
    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1 or doc.material_request_type != CUSTOMER_DEMO:
        return
    ready = all(_is_available_claim_asset(doc, None, claim.asset) for claim in claims)
    current_status = doc.get("demo_status")
    if ready and current_status == "Hold":
        doc.db_set("demo_status", "Ready", update_modified=True)
        _create_ready_notification(doc)
    elif not ready and current_status == "Ready":
        doc.db_set("demo_status", "Hold", update_modified=True)


def _release_fulfilled_candidate_claims(material_request: str, asset_names: list[str]) -> None:
    request = frappe.get_doc("Material Request", material_request)
    submitted = _submitted_outbound_counts(material_request)
    fulfilled = all(
        submitted.get(row.item_code, 0) >= int(_number(row.stock_qty)) for row in request.get("items") or []
    )
    assets_to_release = (
        frappe.get_all(CLAIM_DOCTYPE, filters={"material_request": material_request}, pluck="asset")
        if fulfilled
        else asset_names
    )
    _lock_asset_rows(assets_to_release)
    for asset_name in assets_to_release:
        claim_request = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        if claim_request == material_request:
            frappe.delete_doc(CLAIM_DOCTYPE, asset_name, ignore_permissions=True, force=True)


def _restore_candidate_claims(material_request: str, asset_names: list[str]) -> None:
    """Recreate candidate claims if a claimant's outbound Movement is cancelled."""
    _lock_asset_rows(asset_names)
    request = frappe.get_doc("Material Request", material_request)
    candidate_by_asset = {
        row.asset: row.material_request_item for row in request.get("demo_candidates") or []
    }
    for asset_name in asset_names:
        request_item = candidate_by_asset.get(asset_name)
        if not request_item:
            continue
        asset_location = frappe.db.get_value("Asset", asset_name, "location")
        if asset_location != request.demo_source_location:
            continue
        claim_request = frappe.db.get_value(CLAIM_DOCTYPE, asset_name, "material_request")
        if claim_request and claim_request != material_request:
            frappe.throw(
                _("Cannot cancel Movement because Asset {0} is claimed by another request.").format(
                    asset_name
                )
            )
        if not claim_request:
            frappe.get_doc(
                {
                    "doctype": CLAIM_DOCTYPE,
                    "asset": asset_name,
                    "material_request": material_request,
                    "material_request_item": request_item,
                }
            ).insert(ignore_permissions=True)


def _update_demo_fulfillment_status(material_request: str) -> None:
    frappe.db.sql("SELECT name FROM `tabMaterial Request` WHERE name = %s FOR UPDATE", (material_request,))
    request = frappe.get_doc("Material Request", material_request)
    if request.docstatus != 1 or request.material_request_type != CUSTOMER_DEMO:
        return
    claims = frappe.get_all(CLAIM_DOCTYPE, filters={"material_request": request.name}, fields=["asset"])
    pending_claim = any(not _is_available_claim_asset(request, None, claim.asset) for claim in claims)
    if pending_claim:
        status = "Hold"
    else:
        submitted = _submitted_outbound_counts(request.name)
        all_fulfilled = all(
            submitted.get(row.item_code, 0) >= int(_number(row.stock_qty))
            for row in request.get("items") or []
        )
        any_fulfilled = any(submitted.values())
        status = "Fulfilled" if all_fulfilled else "In Progress" if any_fulfilled else "Ready"
    if request.get("demo_status") != status:
        request.db_set("demo_status", status, update_modified=True)


def _create_ready_notification(doc: Document) -> None:
    """Create one Desk Notification Log for the request owner after a Ready transition."""
    if not doc.owner or not frappe.db.exists("User", doc.owner):
        return
    frappe.get_doc(
        {
            "doctype": "Notification Log",
            "for_user": doc.owner,
            "type": "Alert",
            "subject": _("Customer Demo Asset returned for {0}").format(doc.name),
            "email_content": _("Candidate Assets have returned to Source Location {0}.").format(
                doc.demo_source_location
            ),
            "document_type": "Material Request",
            "document_name": doc.name,
        }
    ).insert(ignore_permissions=True)


def _validate_candidate_asset(doc: Document, request_row: Document, asset_name: str) -> dict[str, str]:
    """Verify exact Item, customer location, and submitted Customer Demo provenance."""
    frappe.has_permission("Asset", "read", asset_name, throw=True)
    asset = frappe.db.get_value(
        "Asset", asset_name, ["name", "item_code", "company", "location", "docstatus", "status"], as_dict=True
    )
    if not asset or asset.docstatus != 1 or asset.status in NON_TRANSFERABLE_STATUSES:
        frappe.throw(_("Candidate Asset {0} must be a submitted transferable Asset.").format(asset_name))
    if asset.company != doc.company or asset.item_code != request_row.item_code:
        frappe.throw(
            _("Candidate Asset {0} must match the requested Fixed Asset Item and Company.").format(asset_name)
        )
    if asset.location in (doc.demo_source_location, doc.demo_target_location):
        frappe.throw(
            _("Candidate Asset {0} must currently be at another Customer's Demo Location.").format(asset_name)
        )
    location = frappe.db.get_value(
        "Location", asset.location, ["custom_party_type", "custom_party_name", "is_group"], as_dict=True
    )
    if (
        not location
        or location.custom_party_type != "Customer"
        or not location.custom_party_name
        or location.custom_party_name == doc.demo_customer
        or location.is_group
    ):
        frappe.throw(_("Candidate Asset {0} must be at another Customer's leaf Location.").format(asset_name))
    frappe.has_permission("Customer", "read", location.custom_party_name, throw=True)
    frappe.has_permission("Location", "read", asset.location, throw=True)
    if not _has_demo_outbound_provenance(asset_name, asset.location, location.custom_party_name, doc.company):
        frappe.throw(
            _("Candidate Asset {0} has no submitted Customer Demo Movement from that Customer.").format(
                asset_name
            )
        )
    return {"current_customer": location.custom_party_name, "current_location": asset.location}


def _has_demo_outbound_provenance(asset_name: str, location_name: str, customer: str, company: str) -> bool:
    rows = frappe.db.sql(
        """select movement.reference_name
        from `tabAsset Movement Item` movement_item
        inner join `tabAsset Movement` movement on movement.name = movement_item.parent
        where movement_item.asset = %s
          and movement.docstatus = 1 and movement.purpose = 'Transfer'
          and movement.reference_doctype = 'Material Request' and movement.company = %s
          and not exists (
              select later_movement.name
              from `tabAsset Movement Item` later_item
              inner join `tabAsset Movement` later_movement on later_movement.name = later_item.parent
              where later_item.asset = movement_item.asset and later_movement.docstatus = 1
                and (later_movement.transaction_date > movement.transaction_date
                  or (later_movement.transaction_date = movement.transaction_date
                    and later_movement.creation > movement.creation))
          )
        order by movement.transaction_date desc, movement.creation desc limit 1""",
        (asset_name, company),
        as_dict=True,
    )
    if not rows:
        return False
    request = frappe.db.get_value(
        "Material Request",
        rows[0].reference_name,
        ["docstatus", "material_request_type", "demo_customer", "demo_target_location", "company"],
        as_dict=True,
    )
    return bool(
        request
        and request.docstatus == 1
        and request.material_request_type == CUSTOMER_DEMO
        and request.demo_customer == customer
        and request.demo_target_location == location_name
        and request.company == company
        and frappe.db.get_value("Asset", asset_name, "location") == location_name
    )


def _validate_demo_outbound_provenance(request: Document, asset_name: str, customer_location: str) -> None:
    if not _has_demo_outbound_provenance(
        asset_name, customer_location, request.demo_customer, request.company
    ):
        frappe.throw(
            _("Asset {0} has no submitted outbound Movement for this Customer Demo request.").format(
                asset_name
            )
        )


def _get_submitted_demo_request(material_request: str, permission: str) -> Document:
    if not isinstance(material_request, str) or not material_request.strip():
        frappe.throw(_("Material Request is required."))
    frappe.has_permission("Material Request", permission, material_request, throw=True)
    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1 or doc.material_request_type != CUSTOMER_DEMO:
        frappe.throw(_("Select a submitted Customer Demo Material Request."))
    return doc


def _available_assets_for_row(doc: Document, request_row: Document, *, exclude: set[str]) -> set[str]:
    filters: dict[str, Any] = {
        "item_code": request_row.item_code,
        "company": doc.company,
        "location": doc.demo_source_location,
        "docstatus": 1,
        "status": ["not in", list(NON_TRANSFERABLE_STATUSES)],
    }
    assets = frappe.get_list(
        "Asset", filters=filters, pluck="name", order_by="creation asc", limit_page_length=1000
    )
    claims = (
        set(frappe.get_all(CLAIM_DOCTYPE, filters={"asset": ["in", assets]}, pluck="asset"))
        if assets
        else set()
    )
    return set(assets) - exclude - (claims - _claim_assets_for_request(doc.name))


def _returned_claim_assets(doc: Document, request_row: Document) -> set[str]:
    claims = frappe.get_all(
        CLAIM_DOCTYPE,
        filters={"material_request": doc.name, "material_request_item": request_row.name},
        pluck="asset",
    )
    return {asset_name for asset_name in claims if _is_available_claim_asset(doc, request_row, asset_name)}


def _claim_assets_for_request(material_request: str) -> set[str]:
    return set(frappe.get_all(CLAIM_DOCTYPE, filters={"material_request": material_request}, pluck="asset"))


def _capitalization_assets_for_row(material_request: str, request_item: str) -> set[str]:
    capitalization_names = frappe.get_all(
        "Asset Capitalization",
        filters={
            "demo_material_request": material_request,
            "demo_material_request_item": request_item,
            "docstatus": ["<", 2],
        },
        fields=["target_asset"],
        limit_page_length=1000,
    )
    return {row.target_asset for row in capitalization_names if row.target_asset}


def _away_claim_assets(doc: Document, request_row: Document) -> set[str]:
    claim_assets = frappe.get_all(
        CLAIM_DOCTYPE,
        filters={"material_request": doc.name, "material_request_item": request_row.name},
        pluck="asset",
    )
    return {
        asset_name
        for asset_name in claim_assets
        if not _is_available_claim_asset(doc, request_row, asset_name)
    }


def _remaining_demo_units(doc: Document, request_row: Document) -> int:
    """Count units not already sent, available, or represented by an Asset Capitalization."""
    sent_assets = _submitted_outbound_asset_names(doc.name)
    sent = _count_assets_by_item(sent_assets, request_row.item_code)
    available = _available_assets_for_row(doc, request_row, exclude=sent_assets)
    capitalized = _capitalization_assets_for_row(doc.name, request_row.name)
    return max(
        0,
        int(_number(request_row.stock_qty)) - sent - len(available | capitalized),
    )


def _validate_demo_item_quantity(row: Document, item_code: str) -> None:
    quantity = _number(row.get("qty"))
    stock_quantity = _number(row.get("stock_qty"))
    conversion_factor = _number(row.get("conversion_factor"))
    if (
        not item_code
        or quantity <= 0
        or not quantity.is_integer()
        or stock_quantity != quantity
        or conversion_factor != 1
        or row.get("uom") != row.get("stock_uom")
    ):
        frappe.throw(_("Customer Demo quantities must be positive whole Stock UOM units."))


def _validate_hold_candidate_counts(doc: Document, candidates: list[dict[str, str]]) -> None:
    candidate_counts: dict[str, int] = {}
    for candidate in candidates:
        item_name = candidate["material_request_item"]
        candidate_counts[item_name] = candidate_counts.get(item_name, 0) + 1
    for row in doc.get("items") or []:
        required_candidates = _remaining_demo_units(doc, row)
        if candidate_counts.get(row.name, 0) != required_candidates:
            frappe.throw(
                _("Select exactly {0} Candidate Asset(s) for Item {1}.").format(
                    required_candidates, row.item_code
                )
            )


def _required_capitalization_units(
    target_qty: int,
    sent_qty: int,
    available_assets: set[str],
    capitalized_assets: set[str],
    away_claim_assets: set[str],
) -> int:
    """Count demand not already fulfilled, ready, capitalized, or claimed for return."""
    represented_assets = available_assets | capitalized_assets
    return max(0, target_qty - sent_qty - len(represented_assets) - len(away_claim_assets))


def _is_available_claim_asset(doc: Document, request_row: Document | None, asset_name: str) -> bool:
    asset = frappe.db.get_value(
        "Asset",
        asset_name,
        ["docstatus", "status", "company", "item_code", "location"],
        as_dict=True,
    )
    return bool(
        asset
        and asset.docstatus == 1
        and asset.status not in NON_TRANSFERABLE_STATUSES
        and asset.company == doc.company
        and (request_row is None or asset.item_code == request_row.item_code)
        and asset.location == doc.demo_source_location
    )


def _lock_request_rows(request_names: set[str] | list[str]) -> None:
    for request_name in sorted(set(request_names)):
        frappe.db.sql("SELECT name FROM `tabMaterial Request` WHERE name = %s FOR UPDATE", (request_name,))


def _lock_movement_context(doc: Document, asset_names: list[str]) -> None:
    claim_requests = (
        frappe.get_all(
            CLAIM_DOCTYPE,
            filters={"asset": ["in", asset_names]},
            pluck="material_request",
        )
        if asset_names
        else []
    )
    request_names = {name for name in claim_requests if isinstance(name, str) and name}
    if doc.get("reference_doctype") == "Material Request" and doc.get("reference_name"):
        request_names.add(doc.reference_name)
    if doc.get("demo_return_for_material_request"):
        request_names.add(doc.demo_return_for_material_request)
    _lock_request_rows(request_names)
    _lock_asset_rows(asset_names)


def _submitted_outbound_asset_names(material_request: str) -> set[str]:
    rows = frappe.db.sql(
        """select movement_item.asset
        from `tabAsset Movement Item` movement_item
        inner join `tabAsset Movement` movement on movement.name = movement_item.parent
        where movement.reference_doctype = 'Material Request' and movement.reference_name = %s
          and (movement.demo_return_for_material_request is null or movement.demo_return_for_material_request = '')
          and movement.docstatus = 1 and movement.purpose = 'Transfer'""",
        (material_request,),
        pluck=True,
    )
    return set(rows)


def _submitted_outbound_counts(material_request: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset_name in _submitted_outbound_asset_names(material_request):
        item_code = frappe.db.get_value("Asset", asset_name, "item_code")
        if item_code:
            counts[item_code] = counts.get(item_code, 0) + 1
    return counts


def _count_assets_by_item(asset_names: set[str], item_code: str) -> int:
    if not asset_names:
        return 0
    return sum(frappe.db.get_value("Asset", name, "item_code") == item_code for name in asset_names)


def _stock_balance(item_code: str, warehouse: str) -> float:
    return _number(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def _validate_leaf_locations(*location_names: str) -> None:
    for location_name in location_names:
        if not frappe.db.exists("Location", location_name):
            frappe.throw(_("Location {0} does not exist.").format(location_name))
        if frappe.db.get_value("Location", location_name, "is_group"):
            frappe.throw(_("Location {0} must be a leaf Location.").format(location_name))


def _validate_warehouse(warehouse: str, company: str) -> None:
    record = frappe.db.get_value("Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True)
    if not record or record.company != company or record.is_group or record.disabled:
        frappe.throw(_("Source Warehouse must be an enabled leaf Warehouse in Company {0}.").format(company))


def _lock_asset_rows(asset_names: set[str] | list[str]) -> None:
    names = sorted({name for name in asset_names if name})
    if not names:
        return
    frappe.db.get_query(
        "Asset",
        fields=["name"],
        filters={"name": ["in", names]},
        order_by="name asc",
        for_update=True,
    ).run()


def _parse_candidates(value: str | list[dict[str, str]]) -> list[dict[str, str]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            frappe.throw(_("Candidate Assets must be a valid list."))
    if not isinstance(value, list):
        frappe.throw(_("Candidate Assets must be a list."))
    parsed: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            frappe.throw(_("Each Candidate Asset must include an MR Item and an Asset."))
        item = _text(entry.get("material_request_item"))
        asset = _text(entry.get("asset"))
        parsed.append({"material_request_item": item, "asset": asset})
    return parsed


def _parse_asset_names(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list):
        frappe.throw(_("Assets must be a list."))
    names = [_text(name) for name in value]
    names = [name for name in names if name]
    if len(names) != len(set(names)):
        frappe.throw(_("An Asset can only be selected once."))
    return names


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
