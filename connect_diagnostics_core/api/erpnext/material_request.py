# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Material Request destination, fulfillment, cost, close, and dashboard rules."""

from __future__ import annotations

from typing import Any, cast

import frappe
from erpnext.accounts.utils import get_currency_precision
from erpnext.stock.stock_ledger import get_previous_sle
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now, rounded

DEMO_THRESHOLD = 10_000.0
RETURNABLE_USAGES = frozenset({"Employee Borrow", "Customer Demo", "Customer Loan"})
ASSET_ROUTES = frozenset({"Existing Asset", "Stock Capitalization"})
STOCK_ROUTES = frozenset({"Stock Entry", "Purchase"})
ROUTES_BY_USAGE = {
    "Employee Borrow": frozenset({"Stock Entry", "Existing Asset", "Purchase", "Stock Capitalization"}),
    "Customer Demo": frozenset({"Stock Entry", "Existing Asset", "Stock Capitalization"}),
    "Customer Loan": frozenset({"Stock Entry", "Existing Asset", "Purchase", "Stock Capitalization"}),
    "Internal Permanent Use": frozenset(
        {"Stock Entry", "Existing Asset", "Purchase", "Stock Capitalization"}
    ),
}
CONTROLLED_ITEM_FIELDS = (
    "fulfillment_route",
    "allocated_asset",
    "unit_cost_ex_vat",
    "cost_source",
)
FULFILLMENT_ROLES = frozenset({"Accounts User", "System Manager"})
FORBIDDEN_ASSET_STATUSES = frozenset(
    {
        "Cancelled",
        "Sold",
        "Scrapped",
        "Capitalized",
        "In Maintenance",
        "Out of Order",
    }
)


def validate(doc: Document, method: str | None = None) -> None:
    """Validate route invariants and protect Accounts-controlled item fields."""
    del method
    _validate_controlled_field_access(doc)
    _validate_downstream_lock(doc)
    _validate_routes(doc)
    if doc.get("request_usage") == "Internal Permanent Use":
        _validate_internal_destination(doc)


def validate_asset_movement(doc: Document, method: str | None = None) -> None:
    """Require Asset Movements linked to an MR to use its allocated Assets."""
    del method
    material_request = doc.get("material_request")
    if not material_request:
        return
    mr = frappe.db.get_value("Material Request", material_request, ["company", "docstatus"], as_dict=True)
    if not mr or mr.docstatus != 1:
        frappe.throw(_("Linked Material Request must be submitted."))
    if mr.company != doc.get("company"):
        frappe.throw(_("Asset Movement and Material Request must belong to the same company."))

    allocated_assets = set(
        frappe.get_all(
            "Material Request Item",
            filters={
                "parent": material_request,
                "fulfillment_route": ("in", tuple(ASSET_ROUTES)),
                "allocated_asset": ("is", "set"),
            },
            pluck="allocated_asset",
        )
    )
    for row in doc.get("assets", []):
        if row.get("asset") not in allocated_assets:
            frappe.throw(
                _("Row #{0}: Allocate Asset {1} on an Asset-route Material Request Item first.").format(
                    row.idx, row.get("asset")
                )
            )
        _validate_asset_qa_gate(doc, row)


def _validate_asset_qa_gate(doc: Any, row: Any) -> None:
    if doc.get("purpose") not in {"Transfer", "Transfer and Issue"} or not row.get("source_location"):
        return
    qahold, repair = frappe.db.get_value(
        "Company", doc.get("company"), ["return_qa_hold_location", "return_repair_location"]
    )
    if row.get("source_location") not in {qahold, repair}:
        return
    if doc.get("reference_doctype") == "Borrowed Asset Return Inspection" and doc.get("reference_name"):
        inspection = frappe.db.get_value(
            "Borrowed Asset Return Inspection",
            doc.reference_name,
            ["docstatus", "inspection_result", "return_disposition"],
            as_dict=True,
        )
        if (
            inspection
            and inspection.docstatus == 1
            and (
                inspection.inspection_result == "Accepted"
                or (row.get("source_location") == repair and inspection.return_disposition == "Repairable")
            )
        ):
            return
    if doc.get("reference_doctype") == "Asset Repair":
        return
    frappe.throw(_("Asset cannot leave QA Hold or Repair without an accepted inspection or repair action."))


def validate_quality_inspection(doc: Document, method: str | None = None) -> None:
    """Populate and verify the MR connection for Stock Entry inspections."""
    del method
    if doc.get("return_dispatch_transfer"):
        _validate_return_quality_inspection_reference(doc)
        return
    if doc.get("reference_type") != "Stock Entry" or not doc.get("reference_name"):
        return
    filters: dict[str, Any] = {
        "parent": doc.get("reference_name"),
        "item_code": doc.get("item_code"),
        "material_request": ("is", "set"),
    }
    if doc.get("child_row_reference"):
        filters["name"] = doc.get("child_row_reference")
    material_requests = set(frappe.get_all("Stock Entry Detail", filters=filters, pluck="material_request"))
    selected = doc.get("material_request")
    if selected and selected not in material_requests:
        frappe.throw(_("Quality Inspection Material Request does not match its Stock Entry row."))
    if len(material_requests) != 1:
        return
    material_request = material_requests.pop()
    doc.set("material_request", material_request)


def _validate_return_quality_inspection_reference(doc: Any) -> None:
    if doc.get("reference_type") != "Stock Entry" or not doc.get("reference_name"):
        frappe.throw(_("Return Quality Inspection must reference the Return End Transit Stock Entry."))

    transfer = frappe.db.get_value(
        "Dispatch Transfer",
        doc.get("return_dispatch_transfer"),
        [
            "parent",
            "material_request_item",
            "item_code",
            "reference_doctype",
            "end_transit_stock_entry_detail",
        ],
        as_dict=True,
    )
    dispatch = (
        frappe.db.get_value(
            "Dispatch",
            transfer.parent,
            [
                "company",
                "material_request",
                "dispatch_type",
                "delivery_status",
                "docstatus",
                "end_transit_stock_entry",
            ],
            as_dict=True,
        )
        if transfer
        else None
    )
    dispatch = cast(Any, dispatch)
    if (
        not transfer
        or transfer.reference_doctype != "Stock Entry"
        or not transfer.end_transit_stock_entry_detail
        or not dispatch
        or dispatch.docstatus != 1
        or dispatch.dispatch_type != "Return"
        or dispatch.delivery_status != "Delivered"
        or not dispatch.end_transit_stock_entry
    ):
        frappe.throw(_("Return Quality Inspection must reference a delivered Return Dispatch stock line."))
    if (
        doc.get("reference_name") != dispatch.get("end_transit_stock_entry")
        or doc.get("child_row_reference") != transfer.get("end_transit_stock_entry_detail")
        or doc.get("item_code") != transfer.get("item_code")
    ):
        frappe.throw(_("Quality Inspection must reference the exact returned Stock Entry Detail row."))
    if doc.get("material_request") and doc.get("material_request") != dispatch.get("material_request"):
        frappe.throw(_("Quality Inspection Material Request does not match the Return Dispatch."))
    doc.set("material_request", dispatch.get("material_request"))


def before_submit_quality_inspection(doc: Any, _method: str | None = None) -> None:
    """Keep one active accepted inspection for each returned Stock Entry detail."""
    if not doc.get("return_dispatch_transfer") or doc.get("status") != "Accepted":
        return
    duplicate = frappe.db.exists(
        "Quality Inspection",
        {
            "name": ("!=", doc.name or ""),
            "return_dispatch_transfer": doc.get("return_dispatch_transfer"),
            "child_row_reference": doc.child_row_reference,
            "status": "Accepted",
            "docstatus": 1,
        },
    )
    if duplicate:
        frappe.throw(_("This returned Stock Entry Detail already has an accepted Quality Inspection."))


def on_submit_quality_inspection(doc: Any, _method: str | None = None) -> None:
    """Create a draft native release or repair transfer after QA accepts/rejects stock."""
    if not doc.get("return_dispatch_transfer") or doc.docstatus != 1:
        return
    if doc.get("status") == "Accepted":
        if doc.get("release_stock_entry"):
            return
        _create_qa_stock_movement(doc, "release")
    elif doc.get("status") == "Rejected" and doc.get("return_disposition") == "Repairable":
        if doc.get("repair_stock_entry"):
            return
        _create_qa_stock_movement(doc, "repair")


def _create_qa_stock_movement(inspection: Any, action: str) -> None:
    transfer = frappe.get_doc("Dispatch Transfer", inspection.return_dispatch_transfer)
    dispatch = frappe.get_doc("Dispatch", transfer.parent)
    if not transfer.end_transit_stock_entry_detail:
        frappe.throw(_("Return Dispatch is missing the exact QA Stock Entry Detail link."))
    detail = frappe.db.get_value(
        "Stock Entry Detail",
        transfer.end_transit_stock_entry_detail,
        ["item_code", "qty", "stock_uom", "serial_no", "batch_no", "s_warehouse", "material_request_item"],
        as_dict=True,
    )
    if not detail:
        frappe.throw(_("The returned Stock Entry Detail no longer exists."))
    company = dispatch.company
    source = frappe.db.get_value("Company", company, "return_qa_hold_warehouse")
    target = (
        frappe.db.get_value("Company", company, "return_repair_warehouse")
        if action == "repair"
        else transfer.planned_final_warehouse
    )
    if not source or not target:
        frappe.throw(_("QA source and planned destination warehouses are required."))
    entry = frappe.new_doc("Stock Entry")
    entry.update(
        {
            "stock_entry_type": "Material Transfer",
            "purpose": "Material Transfer",
            "company": company,
            "return_dispatch_transfer": transfer.name,
        }
    )
    row = {
        "item_code": detail.item_code,
        "qty": detail.qty,
        "s_warehouse": source,
        "t_warehouse": target,
        "stock_uom": detail.stock_uom,
        "uom": detail.stock_uom,
        "material_request": inspection.material_request,
        "material_request_item": detail.material_request_item,
        "against_stock_entry": dispatch.end_transit_stock_entry,
        "ste_detail": transfer.end_transit_stock_entry_detail,
    }
    if detail.serial_no:
        row["serial_no"] = detail.serial_no
    if detail.batch_no:
        row["batch_no"] = detail.batch_no
    entry.append("items", row)
    entry.insert()
    fieldname = "repair_stock_entry" if action == "repair" else "release_stock_entry"
    inspection.db_set(fieldname, entry.name, update_modified=False)


def validate_submit_for_approval(doc: Document) -> None:
    """Workflow task: validate one complete destination before approval."""
    usage = cast(str, doc.get("request_usage") or "")
    if usage not in ROUTES_BY_USAGE:
        frappe.throw(_("Request Usage is required before submitting for approval."))

    if usage == "Employee Borrow":
        _require(doc, "responsible_employee", "Responsible Employee")
        _require(doc, "expected_return_date", "Expected Return Date")
    elif usage in {"Customer Demo", "Customer Loan"}:
        _require(doc, "destination_customer", "Destination Customer")
        _require(doc, "destination_address", "Destination Address")
        _require(doc, "responsible_employee", "Responsible Employee")
        _require(doc, "expected_return_date", "Expected Return Date")
        _validate_customer_address(doc)

    if usage == "Customer Demo" and doc.get("destination_type") != "Customer":
        frappe.throw(_("Customer Demo requires Destination Type Customer."))

    _validate_responsible_employee(doc)
    if usage in RETURNABLE_USAGES:
        from connect_diagnostics_core.api.erpnext.company import validate_returnable_configuration

        validate_returnable_configuration(
            cast(str, doc.get("company")), cast(str, doc.get("responsible_employee"))
        )
    if usage == "Internal Permanent Use":
        _validate_internal_destination(doc)


def before_cancel(doc: Document, _method: str | None = None) -> None:
    """Apply the returnable MR cancellation boundary without deleting links."""
    if doc.docstatus != 1:
        return
    if not _has_stock_cancel_role():
        frappe.throw(
            _("Only Stock User or Stock Manager can cancel this Material Request."), frappe.PermissionError
        )

    linked = frappe.db.sql(
        """
        SELECT se.name AS parent, 'Stock Entry' AS doctype
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        WHERE sed.material_request = %s AND se.docstatus = 0
        UNION ALL
        SELECT name, 'Dispatch' FROM `tabDispatch`
        WHERE material_request = %s AND docstatus = 0
        """,
        (doc.name, doc.name),
        as_dict=True,
    )
    if linked:
        frappe.throw(
            _(
                "Discard linked draft downstream documents before cancelling this Material Request: {0}."
            ).format(", ".join(f"{row.doctype} {row.parent}" for row in linked))
        )

    submitted = frappe.db.sql(
        """
        SELECT se.name, 'Stock Entry' AS doctype FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        WHERE sed.material_request = %s AND se.docstatus = 1
        UNION ALL
        SELECT name, 'Asset Movement' FROM `tabAsset Movement`
        WHERE material_request = %s AND docstatus = 1
        UNION ALL
        SELECT name, 'Dispatch' FROM `tabDispatch`
        WHERE material_request = %s AND docstatus = 1
        LIMIT 1
        """,
        (doc.name, doc.name, doc.name),
        as_dict=True,
    )
    if submitted:
        frappe.throw(
            _("Material Request cannot be cancelled after submitted {0} {1} exists.").format(
                submitted[0].doctype, submitted[0].name
            )
        )


def before_cancel_movement(doc: Document, _method: str | None = None) -> None:
    """Keep submitted native movements immutable once attached to a returnable MR."""
    material_request = doc.get("material_request")
    if not material_request:
        return
    usage = frappe.db.get_value("Material Request", material_request, "request_usage")
    if usage in RETURNABLE_USAGES:
        frappe.throw(_("Submitted native movement for a returnable Material Request cannot be cancelled."))


def validate_stock_entry(doc: Any, _method: str | None = None) -> None:
    """Validate the native Stock Entry half of the borrow/return transit loop."""
    links = {row.get("material_request") for row in doc.get("items", []) if row.get("material_request")}
    if not links:
        return
    if len(links) != 1:
        frappe.throw(_("A Stock Entry cannot mix Material Requests."))
    material_request = cast(str, next(iter(links)))
    usage = frappe.db.get_value("Material Request", material_request, "request_usage")
    if usage not in RETURNABLE_USAGES:
        return
    company = frappe.db.get_value("Material Request", material_request, "company")
    if company != doc.get("company"):
        frappe.throw(_("Stock Entry and Material Request must belong to the same company."))

    if (
        doc.get("return_dispatch_transfer")
        and not doc.get("outgoing_stock_entry")
        and not doc.get("add_to_transit")
    ):
        _validate_qa_stock_movement(doc)
    elif doc.get("return_dispatch_transfer") and doc.get("add_to_transit"):
        _validate_return_outward_entry(doc)
    elif doc.get("outgoing_stock_entry"):
        _validate_end_transit_entry(doc, material_request)
    elif doc.get("borrowed_item_resolution"):
        _validate_resolution_stock_entry(doc)
    elif doc.get("add_to_transit"):
        _validate_outward_entry(doc, material_request)
    else:
        _block_unapproved_qa_movement(doc)


def _validate_outward_entry(doc: Any, material_request: str) -> None:
    transit = frappe.db.get_value("Company", doc.company, "borrow_in_transit_warehouse")
    if not transit or doc.get("to_warehouse") != transit:
        frappe.throw(
            _("Returnable Outward Stock Entry must move into the Company's Borrow In Transit Warehouse.")
        )
    frappe.db.get_value("Material Request", material_request, "name", for_update=True)
    existing = frappe.db.sql(
        """
        SELECT DISTINCT sed.parent
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.material_request = %s AND se.add_to_transit = 1
            AND se.docstatus < 2 AND se.name != %s
        LIMIT 1
        """,
        (material_request, doc.name or ""),
        pluck="parent",
    )
    if existing:
        frappe.throw(_("This returnable Material Request already has an Outward Stock Entry."))
    _validate_full_stock_request(doc, material_request)


def _validate_return_outward_entry(doc: Any) -> None:
    transit = frappe.db.get_value("Company", doc.company, "borrow_in_transit_warehouse")
    if not transit or doc.get("to_warehouse") != transit:
        frappe.throw(
            _("Return Outward Stock Entry must move into the Company's Borrow In Transit Warehouse.")
        )
    dispatch_transfer = frappe.db.get_value(
        "Dispatch Transfer", doc.return_dispatch_transfer, ["parent", "material_request"], as_dict=True
    )
    if not dispatch_transfer:
        frappe.throw(_("Return Outward Stock Entry must reference a Dispatch Transfer."))
    dispatch = frappe.db.get_value(
        "Dispatch",
        dispatch_transfer.parent,
        ["company", "material_request", "dispatch_type"],
        as_dict=True,
    )
    if (
        not dispatch
        or dispatch.company != doc.company
        or dispatch.material_request != dispatch_transfer.material_request
        or dispatch.dispatch_type != "Return"
    ):
        frappe.throw(_("Return Outward Stock Entry must reference a matching Return Dispatch."))
    return_rows = frappe.get_all(
        "Dispatch Transfer",
        filters={"parent": dispatch_transfer.parent, "reference_doctype": "Stock Entry"},
        fields=["material_request_item", "item_code", "qty"],
    )
    expected = {(row.material_request_item, row.item_code): float(row.qty or 0) for row in return_rows}
    actual: dict[tuple[str, str], float] = {}
    for row in doc.get("items", []):
        key = (row.get("material_request_item"), row.get("item_code"))
        actual[key] = actual.get(key, 0.0) + float(row.get("transfer_qty") or 0)
    if actual != expected:
        frappe.throw(_("Return Outward Stock Entry must match the Return Dispatch quantities exactly."))
    employee = frappe.db.get_value(
        "Material Request", dispatch_transfer.material_request, "responsible_employee"
    )
    borrow = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
    if any(row.get("s_warehouse") != borrow for row in doc.get("items", [])):
        frappe.throw(_("Return Outward Stock Entry must move stock from the responsible Borrow Warehouse."))


def _validate_full_stock_request(doc: Any, material_request: str) -> None:
    expected = {
        row.name: float(row.stock_qty or 0)
        for row in frappe.get_all(
            "Material Request Item",
            filters={"parent": material_request, "fulfillment_route": "Stock Entry"},
            fields=["name", "stock_qty"],
        )
    }
    actual: dict[str, float] = {}
    for row in doc.get("items", []):
        if row.get("material_request_item") in expected:
            actual[row.material_request_item] = actual.get(row.material_request_item, 0.0) + float(
                row.transfer_qty or 0
            )
    if actual != expected:
        frappe.throw(
            _("Returnable Outward Stock Entry must contain 100% of every Stock-route Material Request row.")
        )


def _validate_end_transit_entry(doc: Any, material_request: str) -> None:
    source = frappe.db.get_value(
        "Stock Entry",
        doc.get("outgoing_stock_entry"),
        ["docstatus", "company", "add_to_transit", "return_dispatch_transfer", "to_warehouse"],
        as_dict=True,
    )
    transit = frappe.db.get_value("Company", doc.get("company"), "borrow_in_transit_warehouse")
    if (
        not source
        or source.docstatus != 1
        or source.company != doc.get("company")
        or not source.add_to_transit
        or source.to_warehouse != transit
    ):
        frappe.throw(_("End Transit Stock Entry must be mapped from a submitted Outward Stock Entry."))
    expected = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": doc.outgoing_stock_entry, "material_request": material_request},
        fields=["name", "material_request_item", "transfer_qty", "s_warehouse", "t_warehouse"],
    )
    source_names = {row.name for row in expected}
    actual = {row.get("ste_detail"): row for row in doc.get("items", [])}
    if set(actual) != source_names:
        frappe.throw(_("End Transit Stock Entry must complete every Outward Stock Entry row exactly once."))

    recovery_transfer = None
    if source.return_dispatch_transfer:
        transfer = frappe.db.get_value(
            "Dispatch Transfer", source.return_dispatch_transfer, ["parent"], as_dict=True
        )
        target = frappe.db.get_value("Company", doc.company, "return_qa_hold_warehouse")
        if transfer and frappe.db.get_value("Dispatch", transfer.parent, "delivery_status") == "Failed":
            employee = frappe.db.get_value("Material Request", material_request, "responsible_employee")
            target = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
        if not transfer or not target:
            frappe.throw(_("Return End Transit Stock Entry requires a controlled destination Warehouse."))
    elif doc.get("return_dispatch_transfer"):
        recovery_transfer = frappe.db.get_value(
            "Dispatch Transfer", doc.return_dispatch_transfer, ["parent"], as_dict=True
        )
        recovery_dispatch = (
            frappe.db.get_value(
                "Dispatch",
                recovery_transfer.parent,
                ["dispatch_type", "delivery_status", "material_request"],
                as_dict=True,
            )
            if recovery_transfer
            else None
        )
        if (
            not recovery_transfer
            or not recovery_dispatch
            or recovery_dispatch.dispatch_type != "Outbound"
            or recovery_dispatch.delivery_status not in {"Failed", "Dispatched"}
            or recovery_dispatch.material_request != material_request
        ):
            frappe.throw(_("Recovery End Transit Stock Entry must reference a failed Outbound Dispatch."))
    else:
        employee = frappe.db.get_value("Material Request", material_request, "responsible_employee")
        target = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
        if not target:
            frappe.throw(_("End Transit Stock Entry requires the responsible Employee Borrow Warehouse."))

    if recovery_transfer:
        expected_sources = {row.name: row.s_warehouse for row in expected}
        if any(row.get("t_warehouse") != expected_sources.get(name) for name, row in actual.items()):
            frappe.throw(_("Recovery End Transit Stock Entry must return each row to its source Warehouse."))
        targets = {row.get("t_warehouse") for row in doc.get("items", [])}
        if doc.get("to_warehouse") and targets != {doc.get("to_warehouse")}:
            frappe.throw(_("Recovery End Transit Stock Entry header must match its row destinations."))
    elif doc.get("to_warehouse") != target or any(
        row.get("t_warehouse") != target for row in doc.get("items", [])
    ):
        frappe.throw(_("End Transit Stock Entry must use the controlled destination Warehouse."))
    if any(row.get("s_warehouse") != source.to_warehouse for row in doc.get("items", [])):
        frappe.throw(_("End Transit Stock Entry must start from the Outward Transit Warehouse."))
    expected_qty = {row.name: float(row.transfer_qty or 0) for row in expected}
    if any(
        abs(float(row.get("transfer_qty") or 0) - expected_qty[name]) > 0.00001
        for name, row in actual.items()
    ):
        frappe.throw(_("End Transit Stock Entry must complete the exact Outward quantities."))
    duplicate = frappe.db.exists(
        "Stock Entry",
        {
            "outgoing_stock_entry": doc.outgoing_stock_entry,
            "docstatus": 1,
            "name": ("!=", doc.name or ""),
        },
    )
    if duplicate:
        frappe.throw(_("This Outward Stock Entry already has an End Transit Stock Entry."))


def _validate_qa_stock_movement(doc: Any) -> None:
    transfer = frappe.db.get_value(
        "Dispatch Transfer",
        doc.return_dispatch_transfer,
        [
            "parent",
            "material_request_item",
            "item_code",
            "planned_final_warehouse",
            "end_transit_stock_entry_detail",
        ],
        as_dict=True,
    )
    dispatch = (
        frappe.db.get_value(
            "Dispatch",
            transfer.parent,
            ["company", "material_request", "dispatch_type", "delivery_status", "end_transit_stock_entry"],
            as_dict=True,
        )
        if transfer
        else None
    )
    dispatch = cast(Any, dispatch)
    if (
        not transfer
        or not dispatch
        or dispatch.company != doc.company
        or dispatch.dispatch_type != "Return"
        or dispatch.delivery_status != "Delivered"
        or not dispatch.end_transit_stock_entry
        or not transfer.end_transit_stock_entry_detail
    ):
        frappe.throw(_("QA release Stock Entry must reference a valid Return Dispatch Transfer."))
    qahold = frappe.db.get_value("Company", doc.company, "return_qa_hold_warehouse")
    repair = frappe.db.get_value("Company", doc.company, "return_repair_warehouse")
    if any(
        row.get("s_warehouse") != qahold
        or row.get("against_stock_entry") != dispatch.end_transit_stock_entry
        or row.get("ste_detail") != transfer.end_transit_stock_entry_detail
        or row.get("material_request_item") != transfer.material_request_item
        or row.get("item_code") != transfer.item_code
        for row in doc.get("items", [])
    ):
        frappe.throw(_("QA release Stock Entry must move stock out of the Return QA Hold Warehouse."))
    targets = {row.get("t_warehouse") for row in doc.get("items", [])}
    if len(targets) != 1 or targets - {transfer.planned_final_warehouse, repair}:
        frappe.throw(_("QA release Stock Entry must use the planned final or Repair Warehouse."))
    target = next(iter(targets))
    if target == transfer.planned_final_warehouse:
        accepted = frappe.db.exists(
            "Quality Inspection",
            {
                "return_dispatch_transfer": doc.return_dispatch_transfer,
                "child_row_reference": transfer.end_transit_stock_entry_detail,
                "status": "Accepted",
                "docstatus": 1,
            },
        )
        if not accepted:
            frappe.throw(_("QA release requires an accepted Quality Inspection."))
    elif target == repair:
        repairable = frappe.db.exists(
            "Quality Inspection",
            {
                "return_dispatch_transfer": doc.return_dispatch_transfer,
                "child_row_reference": transfer.end_transit_stock_entry_detail,
                "status": "Rejected",
                "return_disposition": "Repairable",
                "docstatus": 1,
            },
        )
        if not repairable:
            frappe.throw(_("Repair movement requires a rejected Repairable Quality Inspection."))


def _validate_resolution_stock_entry(doc: Any) -> None:
    resolution = frappe.db.get_value(
        "Borrowed Item Resolution",
        doc.borrowed_item_resolution,
        ["company", "material_request", "docstatus"],
        as_dict=True,
    )
    if (
        not resolution
        or resolution.docstatus != 1
        or resolution.company != doc.company
        or doc.get("purpose") != "Material Issue"
    ):
        frappe.throw(_("Resolution Stock Entry must reference a submitted matching Resolution."))
    expected_rows = frappe.get_all(
        "Borrowed Item Resolution Item",
        filters={"parent": doc.borrowed_item_resolution, "asset": ("is", "not set")},
        fields=["material_request_item", "item_code", "warehouse", "qty"],
    )
    expected = {
        (row.material_request_item, row.item_code, row.warehouse): float(row.qty or 0)
        for row in expected_rows
    }
    actual: dict[tuple[str, str, str], float] = {}
    for row in doc.get("items", []):
        key = (row.get("material_request_item"), row.get("item_code"), row.get("s_warehouse"))
        actual[key] = actual.get(key, 0.0) + float(row.get("transfer_qty") or 0)
    if actual != expected:
        frappe.throw(_("Resolution Stock Entry rows must match the submitted Resolution exactly."))


def _block_unapproved_qa_movement(doc: Any) -> None:
    qahold, repair = frappe.db.get_value(
        "Company", doc.company, ["return_qa_hold_warehouse", "return_repair_warehouse"]
    )
    if any(row.get("s_warehouse") in {qahold, repair} for row in doc.get("items", [])):
        frappe.throw(_("Stock cannot leave QA Hold or Repair without an approved inspection or resolution."))


def _has_stock_cancel_role() -> bool:
    return frappe.session.user == "Administrator" or bool(
        {"Stock User", "Stock Manager"}.intersection(frappe.get_roles())
    )


def validate_close(doc: Document) -> None:
    """Workflow task: keep close manual while enforcing completion evidence."""
    if not doc.get("items"):
        frappe.throw(_("Material Request must contain at least one item before closing."))

    missing_routes = [str(row.idx) for row in doc.get("items") if not row.get("fulfillment_route")]
    if missing_routes:
        frappe.throw(
            _("Fulfillment Route is required for Material Request Item rows: {0}.").format(
                ", ".join(missing_routes)
            )
        )

    _validate_routes(doc)
    if not _has_downstream_document(doc):
        frappe.throw(_("At least one downstream fulfillment document is required before closing."))

    usage = cast(str, doc.get("request_usage") or "")
    if usage not in RETURNABLE_USAGES:
        return

    if not frappe.db.exists(
        "Dispatch",
        {
            "material_request": doc.name,
            "dispatch_type": "Outbound",
            "docstatus": 1,
            "delivery_status": "Delivered",
        },
    ):
        frappe.throw(_("A delivered Outbound Dispatch is required before closing."))

    from connect_diagnostics_core.connect_diagnostics_stock.report.outstanding_borrowed_items.outstanding_borrowed_items import (
        get_outstanding_rows,
    )

    outstanding = get_outstanding_rows(
        {
            "company": doc.get("company"),
            "as_of_date": getdate(),
            "material_request": doc.name,
        }
    )
    if any(float(row.get("outstanding_qty") or 0) > 0 for row in outstanding):
        frappe.throw(_("All borrowed or demo items must be returned before closing."))


@frappe.whitelist(methods=["POST"])
def refresh_unit_cost(
    material_request: str,
    material_request_items: str | list[str] | None = None,
) -> dict[str, Any]:
    """Refresh auditable per-stock-UOM cost snapshots for selected MR rows."""
    _require_fulfillment_role()
    if not material_request:
        frappe.throw(_("Material Request is required."))
    if not frappe.has_permission("Material Request", "write", doc=material_request):
        frappe.throw(_("You do not have permission to update this Material Request."), frappe.PermissionError)

    frappe.db.get_value("Material Request", material_request, "name", for_update=True)
    doc = cast(Document, frappe.get_doc("Material Request", material_request))
    doc.check_permission("write")
    if doc.docstatus == 2:
        frappe.throw(_("Unit cost cannot be refreshed on a cancelled Material Request."))

    requested = _parse_item_names(material_request_items)
    rows = [row for row in doc.get("items") if not requested or row.name in requested]
    if requested - {row.name for row in rows}:
        frappe.throw(_("One or more selected rows do not belong to this Material Request."))
    if not rows:
        frappe.throw(_("Select at least one Material Request Item."))

    refreshed: list[dict[str, Any]] = []
    for row in rows:
        if _row_has_active_downstream(doc, row.name):
            frappe.throw(
                _("Row #{0}: Unit cost is locked because downstream documents exist.").format(row.idx)
            )
        cost, source = _resolve_unit_cost(doc, row)
        row.set("unit_cost_ex_vat", cost)
        row.set("cost_source", source)
        if doc.get("request_usage") == "Customer Demo" and row.get("fulfillment_route") not in {
            None,
            "",
            "Existing Asset",
            _demo_cost_route(cost),
        }:
            row.set("fulfillment_route", None)
            row.set("allocated_asset", None)
        refreshed.append(
            {
                "material_request_item": row.name,
                "unit_cost_ex_vat": cost,
                "cost_source": source,
            }
        )

    doc.save()
    return {"data": refreshed, "message": _("Unit cost refreshed successfully.")}


@frappe.whitelist(methods=["POST"])
def create_outbound_transit_stock_entry(material_request: str, company: str) -> dict[str, Any]:
    """Create the single full-quantity native Outward Stock Entry for a returnable MR."""
    if not _has_stock_cancel_role():
        frappe.throw(_("Only Stock User or Stock Manager can prepare transit stock."), frappe.PermissionError)
    if not material_request or not company:
        frappe.throw(_("Material Request and Company are required."))
    frappe.db.get_value("Material Request", material_request, "name", for_update=True)
    request = frappe.get_doc("Material Request", material_request)
    request.check_permission("read")
    if request.docstatus != 1 or request.company != company or request.request_usage not in RETURNABLE_USAGES:
        frappe.throw(_("A submitted returnable Material Request in the supplied Company is required."))
    transit = frappe.db.get_value("Company", company, "borrow_in_transit_warehouse")
    if not transit:
        frappe.throw(_("Borrow In Transit Warehouse is required before preparing transit stock."))

    from erpnext.stock.doctype.material_request.material_request import make_in_transit_stock_entry

    entry = make_in_transit_stock_entry(material_request, transit)
    entry.set(
        "items",
        [
            row
            for row in entry.get("items", [])
            if frappe.db.get_value("Material Request Item", row.material_request_item, "fulfillment_route")
            == "Stock Entry"
        ],
    )
    if not entry.get("items"):
        frappe.throw(_("The Material Request has no Stock Entry-route rows to move through Transit."))
    entry.insert()
    entry.submit()
    return {"data": entry.as_dict(), "message": _("Outward transit Stock Entry created.")}


def get_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    """Add app fulfillment documents to native Material Request Connections."""
    transactions = data.setdefault("transactions", [])
    items = [
        "Asset Movement",
        "Asset Capitalization",
        "Quality Inspection",
        "Dispatch",
        "Borrowed Asset Return Inspection",
        "Borrowed Item Resolution",
    ]
    existing = {item for group in transactions for item in group.get("items", [])}
    missing = [item for item in items if item not in existing]
    if missing:
        transactions.append({"label": _("Demo / Loan Fulfillment"), "items": missing})
    return data


def _require(doc: Document, fieldname: str, label: str) -> None:
    if not doc.get(fieldname):
        frappe.throw(_("{0} is required for {1}.").format(_(label), doc.get("request_usage")))


def _validate_customer_address(doc: Document) -> None:
    if not frappe.db.exists(
        "Dynamic Link",
        {
            "parenttype": "Address",
            "parent": doc.get("destination_address"),
            "link_doctype": "Customer",
            "link_name": doc.get("destination_customer"),
        },
    ):
        frappe.throw(_("Destination Address must be linked to the selected Customer."))


def _validate_responsible_employee(doc: Document) -> None:
    employee = doc.get("responsible_employee")
    if not employee:
        return
    values = frappe.db.get_value("Employee", employee, ["status", "company"], as_dict=True)
    if not values or values.status != "Active":
        frappe.throw(_("Responsible Employee must be active."))
    if values.company != doc.get("company"):
        frappe.throw(_("Responsible Employee must belong to the Material Request company."))


def _validate_internal_destination(doc: Document) -> None:
    routed_rows = [row for row in doc.get("items") if row.get("fulfillment_route")]
    if not routed_rows:
        has_warehouse = any(_row_warehouse(doc, row) for row in doc.get("items"))
        if not has_warehouse and not doc.get("asset_location"):
            frappe.throw(_("Internal Permanent Use requires a Warehouse or Asset Location."))
        if doc.get("asset_location"):
            _validate_leaf_location(cast(str, doc.get("asset_location")))
        return
    for row in routed_rows:
        route = row.get("fulfillment_route")
        if not route:
            continue
        if route in STOCK_ROUTES and not _row_warehouse(doc, row):
            frappe.throw(_("Row #{0}: A Warehouse is required for stock fulfillment.").format(row.idx))
        if route in ASSET_ROUTES:
            location = doc.get("asset_location")
            if not location:
                frappe.throw(_("Asset Location is required for asset fulfillment."))
            _validate_leaf_location(cast(str, location))


def _validate_leaf_location(location: str) -> None:
    if frappe.db.get_value("Location", location, "is_group"):
        frappe.throw(_("Asset Location must be a leaf Location."))


def _validate_controlled_field_access(doc: Document) -> None:
    if _has_fulfillment_role():
        return
    before = doc.get_doc_before_save()
    before_rows = {row.name: row for row in before.get("items", [])} if before else {}
    for row in doc.get("items"):
        previous = before_rows.get(row.name)
        for fieldname in CONTROLLED_ITEM_FIELDS:
            old_value = previous.get(fieldname) if previous else None
            changed_existing_value = previous is not None and row.get(fieldname) != old_value
            populated_new_value = previous is None and row.get(fieldname) not in (None, "", 0, 0.0)
            if changed_existing_value or populated_new_value:
                frappe.throw(
                    _("Only Accounts User can change fulfillment route and cost fields."),
                    frappe.PermissionError,
                )


def _validate_downstream_lock(doc: Document) -> None:
    before = doc.get_doc_before_save()
    if not before:
        return
    before_rows = {row.name: row for row in before.get("items", [])}
    for row in doc.get("items"):
        previous = before_rows.get(row.name)
        if not previous or not any(
            row.get(fieldname) != previous.get(fieldname) for fieldname in CONTROLLED_ITEM_FIELDS
        ):
            continue
        if _row_has_active_downstream(doc, row.name):
            frappe.throw(
                _(
                    "Row #{0}: Cancel or reverse active downstream documents before changing "
                    "route, Asset, or cost."
                ).format(row.idx)
            )


def _validate_routes(doc: Document) -> None:
    usage = cast(str, doc.get("request_usage") or "")
    allowed = ROUTES_BY_USAGE.get(usage)
    for row in doc.get("items"):
        route = cast(str, row.get("fulfillment_route") or "")
        allocated_asset = cast(str, row.get("allocated_asset") or "")
        if not route:
            if allocated_asset:
                frappe.throw(
                    _("Row #{0}: Fulfillment Route is required for Allocated Asset.").format(row.idx)
                )
            continue
        if not allowed or route not in allowed:
            frappe.throw(_("Row #{0}: Route {1} is not allowed for {2}.").format(row.idx, route, usage))
        if route == "Existing Asset" and not allocated_asset:
            frappe.throw(_("Row #{0}: Allocated Asset is required for Existing Asset.").format(row.idx))
        if route in STOCK_ROUTES and allocated_asset:
            frappe.throw(_("Row #{0}: Allocated Asset must be empty for {1}.").format(row.idx, route))
        if allocated_asset:
            _validate_asset(doc, row, allocated_asset)
        if usage == "Customer Demo" and route != "Existing Asset":
            if not row.get("cost_source"):
                frappe.throw(
                    _("Row #{0}: Refresh Unit Cost before selecting a Customer Demo route.").format(row.idx)
                )
            expected_route = _demo_cost_route(float(row.get("unit_cost_ex_vat") or 0))
            if route != expected_route:
                frappe.throw(_("Row #{0}: Unit cost requires route {1}.").format(row.idx, expected_route))


def _validate_asset(doc: Document, row: Document, asset_name: str) -> None:
    values = frappe.db.get_value(
        "Asset", asset_name, ["docstatus", "company", "status", "item_code"], as_dict=True
    )
    if not values or values.docstatus != 1:
        frappe.throw(_("Row #{0}: Allocated Asset must be submitted.").format(row.idx))
    if values.company != doc.get("company"):
        frappe.throw(_("Row #{0}: Allocated Asset belongs to another company.").format(row.idx))
    if values.status in FORBIDDEN_ASSET_STATUSES:
        frappe.throw(
            _("Row #{0}: Asset {1} cannot be used while its status is {2}.").format(
                row.idx, asset_name, values.status
            )
        )
    if values.item_code != row.get("item_code"):
        frappe.throw(_("Row #{0}: Allocated Asset must match the requested Item.").format(row.idx))


def _demo_cost_route(cost: float) -> str:
    precision = get_currency_precision()
    return "Stock Capitalization" if rounded(cost, precision) > DEMO_THRESHOLD else "Stock Entry"


def _resolve_unit_cost(doc: Document, row: Document) -> tuple[float, str]:
    warehouse = _row_warehouse(doc, row)
    if not warehouse:
        frappe.throw(_("Row #{0}: Set a source Warehouse before refreshing unit cost.").format(row.idx))
    if frappe.db.get_value("Warehouse", warehouse, "company") != doc.get("company"):
        frappe.throw(_("Row #{0}: Source Warehouse belongs to another company.").format(row.idx))

    posting_date = getdate(doc.get("transaction_date"))
    sle = get_previous_sle(
        {
            "item_code": row.get("item_code"),
            "warehouse": warehouse,
            "posting_date": posting_date,
            "posting_time": "23:59:59",
        }
    )
    precision = get_currency_precision()
    if sle and sle.get("valuation_rate") is not None:
        if (
            sle.get("voucher_type") == "Purchase Receipt"
            and float(sle.get("actual_qty") or 0) > 0
            and (receipt_cost := _purchase_receipt_unit_cost(doc, row, sle, precision))
        ):
            return receipt_cost
        cost = rounded(float(sle.get("valuation_rate") or 0), precision)
        return cost, _("Stock Ledger Entry {0}; warehouse {1}; valuation at {2}; refreshed {3}").format(
            sle.get("name"), warehouse, posting_date, now()
        )

    receipt = frappe.db.sql(
        """
        SELECT pri.name AS row_name, pri.parent AS purchase_receipt,
            pri.base_net_amount, pri.stock_qty, pr.posting_date
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pr.docstatus = 1
            AND pr.company = %(company)s
            AND pri.item_code = %(item_code)s
            AND pri.warehouse = %(warehouse)s
            AND pr.posting_date <= %(posting_date)s
            AND pri.stock_qty > 0
        ORDER BY pr.posting_date DESC, pr.posting_time DESC, pr.creation DESC
        LIMIT 1
        """,
        {
            "company": doc.get("company"),
            "item_code": row.get("item_code"),
            "warehouse": warehouse,
            "posting_date": posting_date,
        },
        as_dict=True,
    )
    if receipt:
        source = receipt[0]
        cost = rounded(float(source.base_net_amount) / float(source.stock_qty), precision)
        return cost, _(
            "Purchase Receipt {0} row {1}; net cost excluding VAT per stock UOM on {2}; refreshed {3}"
        ).format(
            source.purchase_receipt,
            source.row_name,
            source.posting_date,
            now(),
        )

    frappe.throw(
        _(
            "Row #{0}: Unit cost is unavailable. Check the source Warehouse or submit the "
            "Purchase Receipt before refreshing."
        ).format(row.idx)
    )
    raise AssertionError("frappe.throw must raise")


def _purchase_receipt_unit_cost(
    doc: Document,
    row: Document,
    sle: Any,
    precision: int,
) -> tuple[float, str] | None:
    """Resolve the exact inbound Purchase Receipt row behind the latest SLE."""
    receipt = frappe.db.sql(
        """
        SELECT pri.name AS row_name, pri.parent AS purchase_receipt,
            pri.base_net_amount, pri.stock_qty, pr.posting_date
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.name = %(row_name)s
            AND pri.parent = %(purchase_receipt)s
            AND pr.docstatus = 1
            AND pr.company = %(company)s
            AND pri.item_code = %(item_code)s
            AND pri.warehouse = %(warehouse)s
            AND pri.stock_qty > 0
        LIMIT 1
        """,
        {
            "row_name": sle.get("voucher_detail_no"),
            "purchase_receipt": sle.get("voucher_no"),
            "company": doc.get("company"),
            "item_code": row.get("item_code"),
            "warehouse": _row_warehouse(doc, row),
        },
        as_dict=True,
    )
    if not receipt:
        return None

    source = receipt[0]
    cost = rounded(float(source.base_net_amount) / float(source.stock_qty), precision)
    return cost, _(
        "Purchase Receipt {0} row {1}; net cost excluding VAT per stock UOM on {2}; refreshed {3}"
    ).format(
        source.purchase_receipt,
        source.row_name,
        source.posting_date,
        now(),
    )


def _row_warehouse(doc: Document, row: Document) -> str:
    return cast(
        str,
        row.get("from_warehouse")
        or doc.get("set_from_warehouse")
        or row.get("warehouse")
        or doc.get("set_warehouse")
        or "",
    )


def _parse_item_names(value: str | list[str] | None) -> set[str]:
    if value in (None, ""):
        return set()
    parsed = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        frappe.throw(_("Material Request Items must be a list of row IDs."))
    return set(parsed)


def _require_fulfillment_role() -> None:
    if not _has_fulfillment_role():
        frappe.throw(_("Only Accounts User can refresh unit cost."), frappe.PermissionError)


def _has_fulfillment_role() -> bool:
    return frappe.session.user == "Administrator" or bool(FULFILLMENT_ROLES.intersection(frappe.get_roles()))


def _row_has_active_downstream(doc: Document, row_name: str) -> bool:
    child_links = (
        ("Purchase Order Item", "material_request_item"),
        ("Stock Entry Detail", "material_request_item"),
        ("Dispatch Transfer", "material_request_item"),
        ("Borrowed Item Resolution Item", "material_request_item"),
    )
    if any(
        frappe.db.exists(doctype, {fieldname: row_name, "docstatus": ("<", 2)})
        for doctype, fieldname in child_links
    ):
        return True
    return any(
        frappe.db.exists(
            doctype,
            {"material_request": doc.name, "docstatus": ("<", 2)},
        )
        for doctype in ("Asset Movement", "Asset Capitalization", "Quality Inspection")
    )


def _has_downstream_document(doc: Document) -> bool:
    return any(_row_has_active_downstream(doc, row.name) for row in doc.get("items"))
