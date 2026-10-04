# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from erpnext.stock.doctype.material_request.material_request import MaterialRequest
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.model.document import Document

ASSET_TRANSFER = "Asset Transfer"
NON_TRANSFERABLE_ASSET_STATUSES = ("Draft", "Scrapped", "Sold")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def asset_transfer_employee_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Search same-company Employees, ranking the Asset's Department first."""
    filters = dict(filters or {})
    if doctype != "Employee":
        return []
    company = _text(filters.get("company"))
    department = _text(filters.get("preferred_department"))
    if not company:
        return []

    permission_type = "select" if frappe.only_has_select_perm("Employee") else "read"
    if not frappe.has_permission("Employee", ptype=permission_type):
        return []

    query = (
        "select `tabEmployee`.name, `tabEmployee`.employee_name "
        "from `tabEmployee` "
        "where `tabEmployee`.company = %(company)s "
        "and `tabEmployee`.status in ('Active', 'Suspended') "
        "and `tabEmployee`.docstatus < 2 "
        "and (`tabEmployee`.name like %(txt)s or `tabEmployee`.employee_name like %(txt)s) "
        + get_match_cond("Employee")
        + " order by case when %(department)s != '' and `tabEmployee`.department = %(department)s "
        "then 0 else 1 end, `tabEmployee`.employee_name, `tabEmployee`.name "
        "limit %(page_len)s offset %(start)s"
    )
    return cast(
        list[tuple[str, str]],
        frappe.db.sql(
            query,
            {
                "company": company,
                "department": department,
                "txt": f"%{txt}%",
                "page_len": page_len,
                "start": start,
            },
        ),
    )


def validate_material_request(doc: Document, method: str) -> None:
    """Validate the Asset Transfer purpose and retain mandatory stock rows elsewhere."""
    items = doc.get("items") or []
    assets = doc.get("asset_transfer_assets") or []

    if doc.get("material_request_type") != ASSET_TRANSFER:
        if assets:
            frappe.throw(_("Assets can only be added to an Asset Transfer Material Request."))
        if not items:
            frappe.throw(_("At least one stock item is required."))
        return

    if items:
        frappe.throw(_("Asset Transfer Material Requests cannot contain stock items."))
    if not assets:
        frappe.throw(_("Add at least one Asset to the Asset Transfer request."))

    source_location = doc.get("asset_source_location")
    target_location = doc.get("asset_target_location")
    if not source_location or not target_location:
        frappe.throw(_("Set both Source Location and Target Location."))
    if source_location == target_location:
        frappe.throw(_("Source Location and Target Location must be different."))

    _validate_locations(source_location, target_location)
    _validate_assets(doc, assets, source_location)

    title = doc.get("title")
    if not title or title.strip().endswith(" for"):
        asset_names = [row.get("asset_name") or row.get("asset") for row in assets[:3]]
        doc.set("title", _("Asset Transfer Request for {0}").format(", ".join(asset_names))[:100])


def _validate_locations(source_location: str, target_location: str) -> None:
    locations = frappe.get_all(
        "Location",
        filters={"name": ["in", [source_location, target_location]]},
        fields=["name", "is_group"],
    )
    locations_by_name = {location.name: location for location in locations}
    for field_label, location_name in (
        (_("Source Location"), source_location),
        (_("Target Location"), target_location),
    ):
        location = cast(Any, locations_by_name.get(location_name))
        if not location:
            frappe.throw(_("{0} does not exist.").format(field_label))
        if location.is_group:
            frappe.throw(_("{0} must be a leaf Location.").format(field_label))


def _validate_assets(doc: Document, assets: list[Document], source_location: str) -> None:
    if doc.docstatus == 1:
        _validate_submitted_snapshot(doc, assets)

    asset_names = [row.get("asset") for row in assets]
    if any(not asset_name for asset_name in asset_names):
        frappe.throw(_("Select an Asset in every row."))
    if len(asset_names) != len(set(asset_names)):
        frappe.throw(_("An Asset can only appear once in an Asset Transfer request."))

    asset_records = frappe.get_list(
        "Asset",
        filters={"name": ["in", asset_names]},
        fields=[
            "name",
            "company",
            "location",
            "status",
            "docstatus",
            "asset_name",
            "item_code",
            "custodian",
            "department",
            "territory",
        ],
        limit_page_length=len(asset_names),
    )
    assets_by_name = {asset.name: asset for asset in asset_records}
    if set(assets_by_name) != set(asset_names):
        frappe.throw(_("One or more Assets are unavailable or you do not have permission to read them."))
    rows_by_asset = {row.get("asset"): row for row in assets}

    to_employee_names: set[str] = set()
    for asset_name in asset_names:
        asset = cast(Any, assets_by_name.get(asset_name))
        if not asset:
            frappe.throw(_("Asset {0} does not exist.").format(asset_name))
        if asset.docstatus != 1 or asset.status in NON_TRANSFERABLE_ASSET_STATUSES:
            frappe.throw(_("Asset {0} is not in a transferable status.").format(asset_name))
        if asset.company != doc.get("company"):
            frappe.throw(
                _("Asset {0} does not belong to company {1}.").format(asset_name, doc.get("company"))
            )
        if asset.location != source_location:
            frappe.throw(
                _("Asset {0} is not currently at Source Location {1}.").format(asset_name, source_location)
            )

        row = rows_by_asset[asset_name]
        has_approved_snapshot = bool(row.get("asset_transfer_snapshot_captured"))
        if doc.docstatus == 0 or not has_approved_snapshot:
            row.set("from_employee", asset.custodian)
            row.set("asset_name", asset.asset_name)
            row.set("item_code", asset.item_code)
            row.set("current_location", asset.location)
            row.set("target_location", doc.get("asset_target_location"))
            row.set("department", asset.department)
            row.set("territory", asset.territory)
        if doc.docstatus == 0 and not row.get("to_employee"):
            row.set("to_employee", asset.custodian)
        if doc.docstatus == 0:
            row.set("asset_transfer_snapshot_captured", 1)

        source_employee = row.get("from_employee") or asset.custodian
        receiver = row.get("to_employee")
        if receiver and receiver != source_employee:
            to_employee_names.add(receiver)

    _validate_transfer_receivers(doc.get("company"), to_employee_names)

    if doc.docstatus == 1:
        for asset_name in asset_names:
            asset = assets_by_name[asset_name]
            row = rows_by_asset[asset_name]
            if row.get("asset_transfer_snapshot_captured") and row.get("from_employee") != asset.custodian:
                frappe.throw(
                    _("Asset {0} custodian changed after the request was submitted.").format(asset_name)
                )


def _validate_submitted_snapshot(doc: Document, assets: list[Document]) -> None:
    """Reject submitted values that differ from the previously saved, validated draft."""
    if not doc.name:
        frappe.throw(_("Save the Asset Transfer Material Request as a draft before submitting it."))

    stored_docstatus = frappe.db.get_value("Material Request", doc.name, "docstatus")
    if stored_docstatus == 1:
        # Submitted MRs are revalidated when opening their explicit Create action.
        return
    if stored_docstatus != 0:
        frappe.throw(_("Save the Asset Transfer Material Request as a draft before submitting it."))

    saved_doc = frappe.get_doc("Material Request", doc.name)
    if (
        saved_doc.get("material_request_type") != doc.get("material_request_type")
        or saved_doc.get("company") != doc.get("company")
        or saved_doc.get("asset_source_location") != doc.get("asset_source_location")
        or saved_doc.get("asset_target_location") != doc.get("asset_target_location")
    ):
        frappe.throw(_("Asset Transfer request details changed after the draft was saved."))

    saved_rows = {row.name: row for row in saved_doc.get("asset_transfer_assets") or []}
    current_rows = {row.name: row for row in assets}
    if not all(row_name for row_name in current_rows) or set(saved_rows) != set(current_rows):
        frappe.throw(_("Save the Asset Transfer Assets as a draft before submitting the request."))

    snapshot_fields = (
        "asset",
        "asset_name",
        "item_code",
        "current_location",
        "target_location",
        "from_employee",
        "to_employee",
        "department",
        "territory",
        "asset_transfer_snapshot_captured",
    )
    for row_name, row in current_rows.items():
        saved_row = saved_rows[row_name]
        if any(row.get(fieldname) != saved_row.get(fieldname) for fieldname in snapshot_fields):
            frappe.throw(_("Asset Transfer approval details changed after the draft was saved."))


def _validate_transfer_receivers(company: str, employee_names: set[str]) -> None:
    if not employee_names:
        return

    employees = frappe.get_list(
        "Employee",
        filters={"name": ["in", list(employee_names)]},
        fields=["name", "company", "status", "docstatus"],
        limit_page_length=len(employee_names),
    )
    employees_by_name = {employee.name: employee for employee in employees}
    if set(employees_by_name) != employee_names:
        frappe.throw(
            _("One or more selected Employees are unavailable or you do not have permission to read them.")
        )
    for employee_name in employee_names:
        employee = employees_by_name[employee_name]
        if (
            employee.company != company
            or employee.status not in ("Active", "Suspended")
            or employee.docstatus >= 2
        ):
            frappe.throw(
                _("Employee {0} must be Active or Suspended and belong to Company {1}.").format(
                    employee_name, company
                )
            )


def validate_asset_movement_reference(doc: Document, method: str) -> None:
    """Validate a Material Request reference on Asset Movement."""
    if doc.get("demo_return_for_material_request"):
        from connect_diagnostics_core.api.erpnext.customer_demo import validate_customer_demo_return_movement

        validate_customer_demo_return_movement(doc)
        return

    if doc.get("reference_doctype") != "Material Request":
        return

    if not doc.get("reference_name"):
        frappe.throw(_("Select the Asset Transfer Material Request to reference."))

    frappe.has_permission("Material Request", "read", doc.get("reference_name"), throw=True)
    material_request = cast(MaterialRequest, frappe.get_doc("Material Request", doc.get("reference_name")))
    if material_request.get("material_request_type") == "Customer Demo":
        from connect_diagnostics_core.api.erpnext.customer_demo import (
            validate_customer_demo_asset_movement_reference,
        )

        validate_customer_demo_asset_movement_reference(doc, material_request)
        return

    if material_request.docstatus != 1 or material_request.material_request_type != ASSET_TRANSFER:
        frappe.throw(_("Reference Document must be a submitted Asset Transfer Material Request."))
    if material_request.get("company") != doc.get("company"):
        frappe.throw(_("Asset Movement and Material Request must belong to the same company."))
    if doc.get("purpose") != "Transfer":
        frappe.throw(_("Asset Movement purpose must be Transfer for an Asset Transfer Material Request."))

    request_rows = {row.asset: row for row in material_request.get("asset_transfer_assets") or []}
    requested_assets = list(request_rows)
    movement_assets = [row.asset for row in doc.get("assets") or []]
    if len(movement_assets) != len(requested_assets) or set(movement_assets) != set(requested_assets):
        frappe.throw(_("Asset Movement Assets must match the referenced Material Request."))

    current_assets = frappe.get_list(
        "Asset",
        filters={"name": ["in", requested_assets]},
        fields=["name", "custodian", "department", "territory"],
        limit_page_length=len(requested_assets),
    )
    current_assets_by_name = {asset.name: asset for asset in current_assets}
    if set(current_assets_by_name) != set(requested_assets):
        frappe.throw(_("One or more Assets are unavailable or you do not have permission to read them."))

    for row in doc.get("assets") or []:
        request_row = request_rows[row.asset]
        current_asset = current_assets_by_name[row.asset]
        has_approved_snapshot = bool(request_row.asset_transfer_snapshot_captured)
        expected_from_employee = (
            request_row.from_employee
            if has_approved_snapshot
            else request_row.from_employee or current_asset.custodian
        )
        expected_to_employee = request_row.to_employee or expected_from_employee
        expected_department = (
            request_row.department
            if has_approved_snapshot
            else request_row.department or current_asset.department
        )
        expected_territory = (
            request_row.territory
            if has_approved_snapshot
            else request_row.territory or current_asset.territory
        )
        if (
            row.source_location != material_request.asset_source_location
            or row.target_location != material_request.asset_target_location
        ):
            frappe.throw(_("Asset Movement Locations must match the referenced Material Request."))
        if has_approved_snapshot and current_asset.custodian != request_row.from_employee:
            frappe.throw(_("Asset {0} custodian changed after the request was submitted.").format(row.asset))
        if (
            row.from_employee != expected_from_employee
            or row.to_employee != expected_to_employee
            or row.department != expected_department
            or row.territory != expected_territory
        ):
            frappe.throw(_("Asset Movement approval details must match the referenced Material Request."))

    new_receivers = {
        request_rows[row.asset].to_employee
        for row in doc.get("assets") or []
        if request_rows[row.asset].to_employee
        and request_rows[row.asset].to_employee
        != (
            request_rows[row.asset].from_employee
            if request_rows[row.asset].asset_transfer_snapshot_captured
            else request_rows[row.asset].from_employee or current_assets_by_name[row.asset].custodian
        )
    }
    _validate_transfer_receivers(doc.get("company"), new_receivers)


@frappe.whitelist()
def get_asset_movement_draft(material_request: str) -> dict[str, Any]:
    """Return an unsaved Asset Movement payload for a submitted Asset Transfer request."""
    if not isinstance(material_request, str) or not material_request.strip():
        frappe.throw(_("Material Request is required."))
    frappe.has_permission("Material Request", "read", material_request, throw=True)
    frappe.has_permission("Asset Movement", "create", throw=True)
    frappe.has_permission("Asset Movement", "read", throw=True)

    doc = frappe.get_doc("Material Request", material_request)
    if doc.docstatus != 1:
        frappe.throw(_("Submit the Material Request before creating an Asset Movement."))
    if doc.material_request_type != ASSET_TRANSFER:
        frappe.throw(_("Only Asset Transfer Material Requests can create an Asset Movement."))
    validate_material_request(doc, "asset_transfer_action")

    existing = frappe.get_all(
        "Asset Movement",
        filters={
            "reference_doctype": "Material Request",
            "reference_name": doc.name,
            "docstatus": ["<", 2],
        },
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if existing:
        frappe.has_permission("Asset Movement", "read", existing[0].name, throw=True)
        return {
            "data": {"existing_asset_movement": existing[0].name},
            "message": _("An Asset Movement already exists for this request."),
        }

    return {
        "data": {
            "doctype": "Asset Movement",
            "company": doc.get("company"),
            "purpose": "Transfer",
            "reference_doctype": "Material Request",
            "reference_name": doc.get("name"),
            "assets": [
                {
                    "doctype": "Asset Movement Item",
                    "asset": row.get("asset"),
                    "asset_name": row.get("asset_name"),
                    "source_location": doc.get("asset_source_location"),
                    "from_employee": row.get("from_employee"),
                    "target_location": row.get("target_location") or doc.get("asset_target_location"),
                    "to_employee": row.get("to_employee") or row.get("from_employee"),
                    "department": row.get("department"),
                    "territory": row.get("territory"),
                }
                for row in doc.get("asset_transfer_assets") or []
            ],
        },
        "message": _("Asset Movement draft is ready."),
    }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
