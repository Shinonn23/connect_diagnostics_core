# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Controlled post-submit Dispatch mutations and native transit movements."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

STOCK_ROUTES = frozenset({"Stock Entry", "Purchase"})
ASSET_ROUTES = frozenset({"Existing Asset", "Stock Capitalization"})
STOCK_ROLES = frozenset({"Stock User", "Stock Manager"})


@frappe.whitelist(methods=["POST"])
def confirm_dispatch_delivery(
    dispatch: str,
    company: str,
    receiver_name: str,
    receiver_signature: str,
    receiver_contact: str | None = None,
    received_at: str | None = None,
    delivery_note: str | None = None,
) -> dict[str, Any]:
    """Confirm receipt, complete native transit, and persist the POD atomically."""
    doc = _locked_dispatch(dispatch, company)
    if not receiver_name or not receiver_signature:
        frappe.throw(_("Receiver Name and Receiver Signature are required."))

    return _confirm_delivery(
        doc,
        method="Receiver Signature",
        receiver_name=receiver_name,
        receiver_signature=receiver_signature,
        receiver_contact=receiver_contact,
        received_at=received_at,
        delivery_note=delivery_note,
    )


@frappe.whitelist(methods=["POST"])
def override_dispatch_delivery(
    dispatch: str,
    company: str,
    override_reason: str,
    override_attachment: str | None = None,
    receiver_name: str | None = None,
    receiver_contact: str | None = None,
    received_at: str | None = None,
    delivery_note: str | None = None,
) -> dict[str, Any]:
    """Complete delivery without a signature when a Stock role records a reason."""
    doc = _locked_dispatch(dispatch, company)
    if not override_reason or not override_reason.strip():
        frappe.throw(_("Override Reason is required."))
    return _confirm_delivery(
        doc,
        method="Warehouse Override",
        receiver_name=receiver_name,
        receiver_signature=None,
        receiver_contact=receiver_contact,
        received_at=received_at,
        delivery_note=delivery_note,
        override_reason=override_reason,
        override_attachment=override_attachment,
    )


@frappe.whitelist(methods=["POST"])
def report_dispatch_failure(dispatch: str, company: str, failure_note: str) -> dict[str, Any]:
    """Mark a submitted journey failed while retaining its movement references."""
    doc = _locked_dispatch(dispatch, company)
    if not failure_note:
        frappe.throw(_("Failure Note is required."))

    doc.set("delivery_status", "Failed")
    doc.set("delivery_note", failure_note)
    doc.flags.dispatch_action = "failure"
    doc.save()
    return {"data": doc.as_dict(), "message": _("Dispatch failure reported.")}


@frappe.whitelist(methods=["POST"])
def return_dispatch_to_origin(dispatch: str, company: str, reason: str) -> dict[str, Any]:
    """Recover a failed journey to its pre-trip native stock and asset state."""
    doc = _locked_dispatch(dispatch, company, allowed_statuses=("Failed", "Dispatched"))
    if doc.get("dispatch_type") not in {"Outbound", "Return"}:
        frappe.throw(_("Only an Outbound or Return Dispatch can be returned to origin."))
    if doc.get("dispatch_type") == "Return" and doc.get("delivery_status") != "Failed":
        frappe.throw(_("Only a failed Return Dispatch can be returned to origin."))
    if not reason or not reason.strip():
        frappe.throw(_("Return to Origin reason is required."))

    _lock_dispatch_transfers(doc)
    _create_return_to_origin(doc)
    doc.set("delivery_status", "Returned to Origin")
    doc.set("delivery_note", reason)
    doc.set("delivery_confirmed_by", frappe.session.user)
    doc.set("delivery_confirmed_at", now_datetime())
    doc.flags.dispatch_action = "return_origin"
    doc.save()
    if doc.get("dispatch_type") == "Outbound":
        frappe.db.set_value(
            "Material Request", doc.get("material_request"), "status", "Stopped", update_modified=False
        )
    return {"data": doc.as_dict(), "message": _("Dispatch returned to origin.")}


@frappe.whitelist(methods=["POST"])
def prepare_return_transit(dispatch: str, company: str) -> dict[str, Any]:
    """Prepare and submit a native Borrow Warehouse → Transit return Outward."""
    doc = _editable_dispatch(dispatch, company)
    if doc.get("dispatch_type") != "Return":
        frappe.throw(_("Only a Return Dispatch can prepare return transit."))
    stock_rows = [row for row in doc.get("transfers", []) if row.get("reference_doctype") == "Stock Entry"]
    existing_stock_refs = {row.get("reference_name") for row in stock_rows if row.get("reference_name")}
    if existing_stock_refs:
        if len(existing_stock_refs) == 1 and all(row.get("reference_name") for row in stock_rows):
            return {"data": doc.as_dict(), "message": _("Return transit is already prepared.")}
        frappe.throw(_("Return transit is partially prepared; discard the draft and prepare it again."))

    transit = frappe.db.get_value("Company", company, "borrow_in_transit_warehouse")
    employee = frappe.db.get_value("Material Request", doc.get("material_request"), "responsible_employee")
    source = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
    if not transit or not source:
        frappe.throw(_("Borrow Warehouse and Borrow In Transit Warehouse are required."))
    if not stock_rows:
        return {"data": doc.as_dict(), "message": _("No stock return movement is required.")}

    entry = frappe.new_doc("Stock Entry")
    entry.update(
        {
            "stock_entry_type": "Material Transfer",
            "purpose": "Material Transfer",
            "company": company,
            "add_to_transit": 1,
            "from_warehouse": source,
            "to_warehouse": transit,
            "return_dispatch_transfer": stock_rows[0].name,
        }
    )
    for transfer in stock_rows:
        row = {
            "item_code": transfer.get("item_code"),
            "qty": transfer.get("qty"),
            "s_warehouse": source,
            "t_warehouse": transit,
            "uom": transfer.get("uom"),
            "stock_uom": transfer.get("uom"),
            "material_request": doc.get("material_request"),
            "material_request_item": transfer.get("material_request_item"),
        }
        if transfer.get("serial_no"):
            row["serial_no"] = transfer.get("serial_no")
        if transfer.get("batch_no"):
            row["batch_no"] = transfer.get("batch_no")
        entry.append("items", row)
    entry.insert()
    entry.submit()
    doc.set("outward_stock_entry", entry.name)
    details = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": entry.name},
        fields=["name", "material_request_item"],
    )
    detail_by_item = {row.material_request_item: row.name for row in details}
    for transfer in stock_rows:
        transfer.set("reference_name", entry.name)
        transfer.set("outward_stock_entry_detail", detail_by_item.get(transfer.material_request_item))
    doc.save()
    return {"data": doc.as_dict(), "message": _("Return transit Stock Entry prepared.")}


def _confirm_delivery(
    doc: Document,
    *,
    method: str,
    receiver_name: str | None,
    receiver_signature: str | None,
    receiver_contact: str | None,
    received_at: str | None,
    delivery_note: str | None,
    override_reason: str | None = None,
    override_attachment: str | None = None,
) -> dict[str, Any]:
    received = get_datetime(received_at) if received_at else now_datetime()
    received = received or now_datetime()
    dispatched_at = get_datetime(doc.get("dispatched_at"))
    if dispatched_at and received < dispatched_at:
        frappe.throw(_("Received At cannot be before Dispatched At."))

    _create_delivery_movements(doc)
    doc.set("delivery_status", "Delivered")
    doc.set("received_at", received)
    doc.set("receiver_name", receiver_name)
    doc.set("receiver_contact", receiver_contact)
    doc.set("receiver_signature", receiver_signature)
    doc.set("delivery_note", delivery_note)
    doc.set("delivery_confirmation_method", method)
    doc.set("delivery_confirmed_by", frappe.session.user)
    doc.set("delivery_confirmed_at", now_datetime())
    doc.set("delivery_override_reason", override_reason)
    doc.set("delivery_override_attachment", override_attachment)
    doc.flags.dispatch_action = "delivery"
    doc.save()
    _complete_demo_allocation_delivery(doc)
    return {"data": doc.as_dict(), "message": _("Dispatch delivery confirmed.")}


def _complete_demo_allocation_delivery(doc: Document) -> None:
    for row in sorted(
        (row for row in doc.get("transfers", []) if row.get("fulfillment_allocation")),
        key=lambda value: cast(str, value.get("fulfillment_allocation")),
    ):
        allocation = frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            row.get("fulfillment_allocation"),
            ["resolved_asset", "asset_reservation", "lifecycle_state"],
            as_dict=True,
            for_update=True,
        )
        expected_state = "Dispatched" if doc.get("dispatch_type") == "Outbound" else "Delivered"
        if (
            not allocation
            or allocation.resolved_asset != row.get("asset")
            or allocation.lifecycle_state != expected_state
        ):
            frappe.throw(_("A Demo allocation changed before delivery confirmation."))
        frappe.db.set_value(
            "Material Request Fulfillment Allocation",
            row.get("fulfillment_allocation"),
            "lifecycle_state",
            "Delivered" if doc.get("dispatch_type") == "Outbound" else "Returned",
            update_modified=False,
        )
        if doc.get("dispatch_type") != "Outbound" or not allocation.asset_reservation:
            continue
        reservation = frappe.db.get_value(
            "Demo Asset Reservation",
            allocation.asset_reservation,
            ["asset", "status"],
            as_dict=True,
            for_update=True,
        )
        if not reservation or reservation.asset != allocation.resolved_asset:
            frappe.throw(_("The Demo Asset reservation no longer matches its allocation."))
        if reservation.status == "Active":
            frappe.db.set_value(
                "Demo Asset Reservation",
                allocation.asset_reservation,
                {"status": "Consumed", "active_asset_key": None},
                update_modified=False,
            )
        elif reservation.status != "Consumed":
            frappe.throw(_("The Demo Asset reservation is not active for delivery."))


def _create_delivery_movements(doc: Document) -> None:
    """Complete native transit and verify submitted Asset Movements before saving the POD."""
    if not isinstance(doc, Document):
        return
    _create_end_transit_stock_entry(doc)
    _validate_asset_delivery_movements(doc)


def _create_end_transit_stock_entry(doc: Document) -> None:
    stock_rows = [row for row in doc.get("transfers", []) if row.get("reference_doctype") == "Stock Entry"]
    if not stock_rows:
        return
    if doc.get("end_transit_stock_entry"):
        return
    outward_names = {row.get("reference_name") for row in stock_rows if row.get("reference_name")}
    if len(outward_names) != 1:
        frappe.throw(_("A Dispatch must have one submitted Outward Stock Entry."))
    outward_name = cast(str, next(iter(outward_names)))
    from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry

    end_entry = make_stock_in_entry(outward_name)
    selected_names = {row.get("material_request_item") for row in stock_rows}
    end_entry.set(
        "items",
        [row for row in end_entry.get("items", []) if row.get("material_request_item") in selected_names],
    )
    if not end_entry.get("items"):
        frappe.throw(_("No pending Stock Entry rows remain in Transit for this Dispatch."))

    target_warehouse = _delivery_warehouse(doc)
    end_entry.set("to_warehouse", target_warehouse)
    if doc.get("dispatch_type") == "Return":
        end_entry.set("return_dispatch_transfer", stock_rows[0].name)
    for row in end_entry.get("items", []):
        row.set("t_warehouse", target_warehouse)
    end_entry.insert()
    end_entry.submit()
    doc.set("end_transit_stock_entry", end_entry.name)
    detail_by_source = {row.get("ste_detail"): row.name for row in end_entry.get("items", [])}
    source_details = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": outward_name},
        fields=["name", "material_request_item"],
    )
    source_detail_by_item = {row.material_request_item: row.name for row in source_details}
    for transfer in stock_rows:
        source_detail = transfer.get("outward_stock_entry_detail") or source_detail_by_item.get(
            transfer.get("material_request_item")
        )
        detail = detail_by_source.get(source_detail)
        if detail:
            transfer.set("end_transit_stock_entry_detail", detail)


def _delivery_warehouse(doc: Document) -> str:
    if doc.get("dispatch_type") == "Return":
        warehouse = frappe.db.get_value("Company", doc.get("company"), "return_qa_hold_warehouse")
        if not warehouse:
            frappe.throw(_("Return QA Hold Warehouse is required before confirming a return."))
        return cast(str, warehouse)
    employee = None
    if doc.get("dispatch_type") == "Return":
        employee = frappe.db.get_value(
            "Material Request", doc.get("material_request"), "responsible_employee"
        )
    warehouse = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
    if not warehouse:
        frappe.throw(_("Responsible Employee Borrow Warehouse is required before confirming delivery."))
    return cast(str, warehouse)


def _validate_asset_delivery_movements(doc: Document) -> None:
    """Re-fetch and lock the submitted Asset Movement used by this Dispatch."""
    asset_rows = [row for row in doc.get("transfers", []) if row.get("asset")]
    if not asset_rows:
        return
    movement_names = {row.get("reference_name") for row in asset_rows if row.get("reference_name")}
    if len(movement_names) != 1:
        frappe.throw(_("A Dispatch must use one submitted Asset Movement for its Asset rows."))
    movement_name = cast(str, next(iter(movement_names)))
    movement = frappe.db.get_value(
        "Asset Movement",
        movement_name,
        ["company", "material_request", "docstatus", "purpose"],
        as_dict=True,
        for_update=True,
    )
    expected_purpose = "Receipt" if doc.get("dispatch_type") == "Return" else "Issue"
    if (
        not movement
        or movement.docstatus != 1
        or movement.company != doc.get("company")
        or movement.material_request != doc.get("material_request")
        or movement.purpose != expected_purpose
    ):
        frappe.throw(_("The Dispatch Asset Movement must be submitted and match this journey."))
    demo_rows = [row for row in asset_rows if row.get("fulfillment_allocation")]
    if demo_rows:
        expected_reference_doctype = (
            "Dispatch" if doc.get("dispatch_type") == "Return" else "Material Request Fulfillment"
        )
        expected_reference_name = (
            doc.get("original_dispatch")
            if doc.get("dispatch_type") == "Return"
            else frappe.db.get_value(
                "Material Request Fulfillment Allocation",
                demo_rows[0].get("fulfillment_allocation"),
                "parent",
            )
        )
        reference = frappe.db.get_value(
            "Asset Movement", movement_name, ["reference_doctype", "reference_name"], as_dict=True
        )
        if (
            not reference
            or reference.reference_doctype != expected_reference_doctype
            or reference.reference_name != expected_reference_name
        ):
            frappe.throw(_("The Demo Asset Movement reference does not match this journey."))
    for transfer in asset_rows:
        if not frappe.db.exists(
            "Asset Movement Item", {"parent": movement_name, "asset": transfer.get("asset")}
        ):
            frappe.throw(
                _("Asset {0} is missing from the Dispatch Asset Movement.").format(transfer.get("asset"))
            )


def _create_return_to_origin(doc: Document) -> None:
    if not isinstance(doc, Document):
        return
    _create_recovery_stock_entry(doc)
    _create_recovery_asset_movement(doc)


def _create_recovery_stock_entry(doc: Document) -> None:
    if doc.get("recovery_stock_entry"):
        return
    stock_rows = [row for row in doc.get("transfers", []) if row.get("reference_doctype") == "Stock Entry"]
    if not stock_rows:
        return
    outward_names = {row.get("reference_name") for row in stock_rows if row.get("reference_name")}
    if len(outward_names) != 1:
        frappe.throw(_("A Dispatch must have one submitted Outward Stock Entry."))
    from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry

    recovery = make_stock_in_entry(cast(str, next(iter(outward_names))))
    if doc.get("dispatch_type") == "Outbound":
        recovery.set("return_dispatch_transfer", stock_rows[0].name)
    source_details = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": next(iter(outward_names))},
        fields=["material_request_item", "s_warehouse"],
    )
    source_by_item = {
        row.material_request_item: next(
            (
                detail.s_warehouse
                for detail in source_details
                if detail.material_request_item == row.material_request_item
            ),
            None,
        )
        for row in stock_rows
    }
    recovery.set(
        "items",
        [row for row in recovery.get("items", []) if row.get("material_request_item") in source_by_item],
    )
    for row in recovery.get("items", []):
        source = source_by_item.get(row.get("material_request_item"))
        if not source:
            frappe.throw(_("Original source Warehouse is missing for a recovery row."))
        row.set("t_warehouse", source)
    recovery.insert()
    recovery.submit()
    doc.set("recovery_stock_entry", recovery.name)


def _create_recovery_asset_movement(doc: Document) -> None:
    if doc.get("recovery_asset_movement"):
        return
    asset_rows = [row for row in doc.get("transfers", []) if row.get("asset")]
    if not asset_rows:
        return
    employee = None
    if doc.get("dispatch_type") == "Return":
        employee = frappe.db.get_value(
            "Material Request", doc.get("material_request"), "responsible_employee"
        )
    movement = frappe.new_doc("Asset Movement")
    movement.update(
        {
            "company": doc.get("company"),
            "purpose": "Receipt",
            "transaction_date": now_datetime(),
            "reference_doctype": "Dispatch",
            "reference_name": doc.name,
            "material_request": doc.get("material_request"),
        }
    )
    for row in asset_rows:
        source_location = row.get("original_source_location")
        if not source_location:
            frappe.throw(
                _("Original source Location is required to recover Asset {0}.").format(row.get("asset"))
            )
        movement_row: dict[str, Any] = {
            "asset": row.get("asset"),
            "target_location": source_location,
        }
        if doc.get("dispatch_type") == "Return":
            if not employee:
                frappe.throw(_("Responsible Employee is required to recover a failed Return Asset."))
            movement_row["to_employee"] = employee
        movement.append("assets", movement_row)
    movement.insert()
    movement.submit()
    doc.set("recovery_asset_movement", movement.name)


def _lock_dispatch_transfers(doc: Document) -> None:
    for transfer in doc.get("transfers", []):
        if transfer.get("name"):
            frappe.db.get_value("Dispatch Transfer", transfer.get("name"), "name", for_update=True)


def _locked_dispatch(
    dispatch: str, company: str, allowed_statuses: Iterable[str] = ("Dispatched",)
) -> Document:
    if not dispatch or not company:
        frappe.throw(_("Dispatch and Company are required."))
    if not _has_stock_role():
        frappe.throw(
            _("Only Stock User or Stock Manager can confirm Dispatch delivery."), frappe.PermissionError
        )
    if not frappe.has_permission("Dispatch", "write", doc=dispatch):
        frappe.throw(_("You do not have permission to update this Dispatch."), frappe.PermissionError)

    locked = frappe.db.get_value(
        "Dispatch", dispatch, ["name", "company", "docstatus", "delivery_status"], for_update=True
    )
    if not locked:
        frappe.throw(_("Dispatch {0} does not exist.").format(dispatch))
    name, actual_company, docstatus, delivery_status = locked
    if actual_company != company:
        frappe.throw(_("Dispatch does not belong to the supplied Company."), frappe.PermissionError)
    if docstatus != 1 or delivery_status not in set(allowed_statuses):
        frappe.throw(_("Only a submitted Dispatched journey can be updated."))

    doc = cast(Document, frappe.get_doc("Dispatch", name))
    doc.check_permission("write")
    return doc


def _editable_dispatch(dispatch: str, company: str) -> Document:
    if not dispatch or not company:
        frappe.throw(_("Dispatch and Company are required."))
    if not _has_stock_role():
        frappe.throw(_("Only Stock User or Stock Manager can prepare transit."), frappe.PermissionError)
    locked = frappe.db.get_value(
        "Dispatch", dispatch, ["name", "company", "docstatus", "dispatch_type"], for_update=True
    )
    if not locked:
        frappe.throw(_("Dispatch {0} does not exist.").format(dispatch))
    if locked[1] != company:
        frappe.throw(_("Dispatch does not belong to the supplied Company."), frappe.PermissionError)
    if locked[2] != 0:
        frappe.throw(_("Return transit can only be prepared on a draft Dispatch."))
    doc = cast(Document, frappe.get_doc("Dispatch", locked[0]))
    doc.check_permission("write")
    return doc


def _has_stock_role() -> bool:
    return frappe.session.user == "Administrator" or bool(STOCK_ROLES.intersection(frappe.get_roles()))


def get_dispatch_label_rows(doc: Document) -> list[dict[str, Any]]:
    """Build one QR-label row per Asset or native Serial No without mutating Dispatch."""
    mr = (
        frappe.db.get_value(
            "Material Request",
            doc.get("material_request"),
            ["responsible_employee", "destination_customer", "expected_return_date", "request_usage"],
            as_dict=True,
        )
        or frappe._dict()
    )
    rows: list[dict[str, Any]] = []
    stock_transfers = [
        row
        for row in doc.get("transfers", [])
        if row.get("reference_doctype") == "Stock Entry" and not row.get("asset")
    ]
    serials_by_key = _stock_serials(stock_transfers)
    for transfer in doc.get("transfers", []):
        identifiers = (
            [cast(str, transfer.get("asset"))]
            if transfer.get("asset")
            else serials_by_key.get(
                (cast(str, transfer.get("reference_name")), cast(str, transfer.get("material_request_item"))),
                [],
            )
        )
        if not identifiers:
            identifiers = [cast(str, transfer.get("item_code"))]
        for identifier in identifiers:
            rows.append(
                {
                    "identifier": identifier,
                    "identifier_type": "Asset ID" if transfer.get("asset") else "Serial No / Item",
                    "asset": transfer.get("asset"),
                    "item_code": transfer.get("item_code"),
                    "responsible_employee": mr.get("responsible_employee"),
                    "customer": mr.get("destination_customer"),
                    "expected_return_date": mr.get("expected_return_date"),
                    "request_usage": mr.get("request_usage"),
                }
            )
    return rows


def _stock_serials(transfers: list[Document]) -> dict[tuple[str, str], list[str]]:
    keys = {
        (
            cast(str, transfer.get("reference_name")),
            cast(str, transfer.get("material_request_item")),
            cast(str, transfer.get("item_code")),
        )
        for transfer in transfers
    }
    if not keys:
        return {}

    details = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": ("in", list({key[0] for key in keys}))},
        fields=[
            "parent",
            "material_request_item",
            "item_code",
            "serial_no",
            "serial_and_batch_bundle",
        ],
    )
    serials_by_key: dict[tuple[str, str], list[str]] = {
        (reference_name, material_request_item): []
        for reference_name, material_request_item, _item_code in keys
    }
    bundle_keys: dict[str, set[tuple[str, str]]] = {}
    for detail in details:
        detail_key = (
            cast(str, detail.get("parent")),
            cast(str, detail.get("material_request_item")),
            cast(str, detail.get("item_code")),
        )
        if detail_key not in keys:
            continue
        result_key = (detail_key[0], detail_key[1])
        serials_by_key[result_key].extend(
            serial for serial in str(detail.get("serial_no") or "").splitlines() if serial
        )
        if bundle := detail.get("serial_and_batch_bundle"):
            bundle_keys.setdefault(cast(str, bundle), set()).add(result_key)

    if bundle_keys:
        bundle_entries = frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": ("in", list(bundle_keys)), "serial_no": ("is", "set")},
            fields=["parent", "serial_no"],
        )
        for entry in bundle_entries:
            for result_key in bundle_keys.get(cast(str, entry.get("parent")), set()):
                serials_by_key[result_key].append(cast(str, entry.get("serial_no")))

    return {key: list(dict.fromkeys(serials)) for key, serials in serials_by_key.items()}
