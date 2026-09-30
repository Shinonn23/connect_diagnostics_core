# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any, cast

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.assets.doctype.asset.asset import make_sales_invoice
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint
from PIL import ImageFont
from pythainlp.util import bahttext

from connect_diagnostics_core.api.erpnext.print_configuration import get_document_print_context
from connect_diagnostics_core.api.erpnext.stock_traceability import get_item_traceability
from connect_diagnostics_core.setup import print_documents

ITEM_BODY_HEIGHT_MM = 69.54
ITEM_ROW_LINE_HEIGHT_MM = 6.15
ITEM_DESCRIPTION_WIDTH_MM = 107.93
ITEM_DESCRIPTION_PADDING_MM = 1.75 + 1.20
TRACEABILITY_FONT_SIZE_MM = 3.65
PRINT_DPI = 96
PRINT_FONT_PATH = Path(__file__).resolve().parents[2] / "public" / "fonts" / "THSarabun.ttf"


def _sales_invoice_layout(print_format: str) -> tuple[float, float, float, float, bool]:
    """Return body geometry for the selected Sales Invoice family format."""
    if print_format == "Credit Note":
        return (68.14, 4.45, 65.00 - 1.20 - 0.90, 3.75, True)
    return (
        ITEM_BODY_HEIGHT_MM,
        ITEM_ROW_LINE_HEIGHT_MM,
        ITEM_DESCRIPTION_WIDTH_MM - ITEM_DESCRIPTION_PADDING_MM,
        TRACEABILITY_FONT_SIZE_MM,
        False,
    )


class CustomSalesInvoice(SalesInvoice):
    custom_in_words_thai: str | None


def before_save(doc: CustomSalesInvoice, method: str) -> None:
    if doc.custom_in_words_thai:
        doc.custom_in_words_thai = bahttext(doc.rounded_total)


def validate_tax_invoice_readiness(doc: Document, method: str | None = None) -> None:
    """Warn when the Customer's tax details are incomplete at the point of issue.

    A Customer is sellable the moment Sales saves it, so this is where the Thai
    billing address, tax ID and branch code are surfaced — at the point the
    document that must carry them is submitted. The gap is flagged as a warning,
    not a hard block: the submit proceeds so operations are never held up, and the
    message tells Sales exactly what is still missing.
    """
    from connect_diagnostics_core.api.erpnext.customer import (
        MISSING,
        get_readiness_for_customer,
    )

    customer = str(doc.get("customer") or "").strip()
    if not customer:
        return

    readiness = get_readiness_for_customer(customer)
    if readiness.get("tax_invoice_readiness") != MISSING:
        return

    frappe.msgprint(
        _("{0} is not ready for a tax invoice: {1}").format(
            frappe.bold(doc.get("customer_name") or customer),
            readiness.get("customer_readiness_summary") or _("its tax details are incomplete"),
        ),
        title=_("Customer tax details incomplete"),
        indicator="orange",
    )


def get_sales_invoice_print_context(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build the selected Sales Invoice print context with traceability-aware pagination."""
    print_format = str(frappe.form_dict.get("format") or "").strip()
    configuration = print_documents.resolve_document_key("Sales Invoice", print_format) or "tax_invoice"
    print_context = get_document_print_context(doc, configuration)
    (
        body_height_mm,
        row_line_height_mm,
        description_width_mm,
        traceability_font_size_mm,
        compact_traceability,
    ) = _sales_invoice_layout(print_format)
    if configuration in {"tax_invoice", "full_receipt"}:
        print_context["show_delivery_note"] = bool(
            cint(print_context.get("show_delivery_note")) and _has_delivery_note(doc)
        )
    else:
        print_context["show_delivery_note"] = False
    items = [
        _prepare_print_item(
            row,
            print_context["show_batch_serial"],
            description_width_mm,
            traceability_font_size_mm,
            compact_traceability,
        )
        for row in cast(list[Any], doc.get("items") or [])
    ]
    item_pages = _paginate_items(items, body_height_mm, row_line_height_mm)
    return {
        "print_context": print_context,
        "item_pages": item_pages,
        "item_page_count": len(item_pages),
    }


def _has_delivery_note(doc: Document | Mapping[str, Any]) -> bool:
    """Return whether any Sales Invoice item is linked to a Delivery Note."""
    return any(str(row.get("delivery_note") or "").strip() for row in (doc.get("items") or []))


def _prepare_print_item(
    row: Any,
    show_batch_serial: bool,
    description_width_mm: float,
    traceability_font_size_mm: float,
    compact_traceability: bool,
) -> dict[str, Any]:
    item = _row_as_dict(row)
    traceability = (
        get_item_traceability(item)
        if show_batch_serial
        else {"batch_nos": [], "serial_nos": [], "records": []}
    )
    traceability_lines = _traceability_lines(traceability)
    item["traceability_lines"] = traceability_lines
    if compact_traceability:
        traceability_text = " | ".join(f"{trace['label']}: {trace['value']}" for trace in traceability_lines)
        traceability_line_count = (
            _display_line_count(traceability_text, traceability_font_size_mm, description_width_mm)
            if traceability_text
            else 0
        )
    else:
        traceability_line_count = sum(
            _display_line_count(
                f"{trace['label']}: {trace['value']}",
                traceability_font_size_mm,
                description_width_mm,
            )
            for trace in traceability_lines
        )
    item["line_count"] = 1 + traceability_line_count
    return item


def _traceability_lines(traceability: dict[str, Any]) -> list[dict[str, str]]:
    records = cast(list[dict[str, str]], traceability.get("records") or [])
    if not records:
        records = [
            {"batch_no": batch_no, "serial_no": ""}
            for batch_no in cast(list[str], traceability.get("batch_nos") or [])
        ]
        records.extend(
            {"batch_no": "", "serial_no": serial_no}
            for serial_no in cast(list[str], traceability.get("serial_nos") or [])
        )

    lines: list[dict[str, str]] = []
    for record in records:
        batch_no = record.get("batch_no", "")
        serial_no = record.get("serial_no", "")
        if batch_no and serial_no:
            lines.append({"label": "Batch / SN", "value": f"{batch_no} / {serial_no}"})
        elif batch_no:
            lines.append({"label": "Batch", "value": batch_no})
        elif serial_no:
            lines.append({"label": "SN", "value": serial_no})
    return lines


def _display_line_count(value: str, font_size_mm: float, width_mm: float) -> int:
    text = unescape(str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    font = _print_font(font_size_mm)
    width_px = _mm_to_px(width_mm)
    return sum(_wrapped_line_count(line, font, width_px) for line in text.split("\n")) or 1


def _wrapped_line_count(value: str, font: ImageFont.FreeTypeFont, width_px: float) -> int:
    if not value:
        return 1

    line_count = 1
    line_width = 0.0
    for character in value:
        character_width = float(font.getlength(character))
        if line_width and line_width + character_width > width_px:
            line_count += 1
            line_width = character_width
        else:
            line_width += character_width
    return line_count


def _mm_to_px(value_mm: float) -> float:
    return value_mm / 25.4 * PRINT_DPI


@lru_cache(maxsize=4)
def _print_font(size_mm: float) -> ImageFont.FreeTypeFont:
    size_px = max(round(_mm_to_px(size_mm)), 1)
    return ImageFont.truetype(str(PRINT_FONT_PATH), size_px)


def _body_line_capacity(body_height_mm: float, row_line_height_mm: float) -> int:
    return max(int((body_height_mm - 0.215) // row_line_height_mm), 1)


def _paginate_items(
    items: list[dict[str, Any]], body_height_mm: float, row_line_height_mm: float
) -> list[list[dict[str, Any]]]:
    if not items:
        return [[]]

    pages: list[list[dict[str, Any]]] = []
    current_page: list[dict[str, Any]] = []
    current_lines = 0
    page_line_capacity = _body_line_capacity(body_height_mm, row_line_height_mm)
    for item in items:
        line_count = max(int(item["line_count"]), 1)
        if current_page and current_lines + line_count > page_line_capacity:
            pages.append(current_page)
            current_page = []
            current_lines = 0
        current_page.append(item)
        current_lines += line_count
        if current_lines >= page_line_capacity:
            pages.append(current_page)
            current_page = []
            current_lines = 0

    if current_page:
        pages.append(current_page)
    return pages


def _row_as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    as_dict = getattr(row, "as_dict", None)
    if callable(as_dict):
        return cast(dict[str, Any], as_dict())
    return dict(vars(row))


def _demo_sale_context(allocation: str) -> tuple[Any, Any, Any, Any]:
    row = frappe.db.get_value(
        "Material Request Fulfillment Allocation",
        allocation,
        [
            "name",
            "parent",
            "lifecycle_state",
            "resolved_asset",
            "fixed_asset_item",
            "current_sales_invoice",
            "sale_attempt",
            "asset_reservation",
            "dispatch_transfer",
        ],
        as_dict=True,
        for_update=True,
    )
    if not row or row.lifecycle_state != "Delivered" or not row.resolved_asset:
        frappe.throw(_("Only a delivered Demo allocation with a resolved Asset can be sold."))
    plan = frappe.db.get_value(
        "Material Request Fulfillment",
        row.parent,
        ["name", "material_request", "company", "status"],
        as_dict=True,
        for_update=True,
    )
    if not plan or plan.status != "Planned":
        frappe.throw(_("The linked Fulfillment is no longer active."))
    mr = frappe.db.get_value(
        "Material Request",
        plan.material_request,
        ["company", "docstatus", "request_usage"],
        as_dict=True,
        for_update=True,
    )
    if not mr or mr.docstatus != 1 or mr.request_usage != "Customer Demo" or mr.company != plan.company:
        frappe.throw(_("The linked request is not an active Demo request."))
    asset = frappe.db.get_value(
        "Asset",
        row.resolved_asset,
        ["name", "company", "docstatus", "status", "asset_quantity", "item_code"],
        as_dict=True,
        for_update=True,
    )
    if (
        not asset
        or asset.company != plan.company
        or asset.docstatus != 1
        or asset.status in {"Sold", "Scrapped"}
        or asset.asset_quantity != 1
        or asset.item_code != row.fixed_asset_item
    ):
        frappe.throw(_("The resolved Asset is no longer eligible for sale."))
    transfer = frappe.db.get_value(
        "Dispatch Transfer",
        row.dispatch_transfer,
        ["name", "parent", "asset", "fulfillment_allocation"],
        as_dict=True,
        for_update=True,
    )
    dispatch = frappe.db.get_value(
        "Dispatch",
        transfer.parent if transfer else "",
        ["name", "company", "docstatus", "dispatch_type", "delivery_status"],
        as_dict=True,
        for_update=True,
    )
    if (
        not transfer
        or not dispatch
        or transfer.fulfillment_allocation != allocation
        or transfer.asset != row.resolved_asset
        or dispatch.company != plan.company
        or dispatch.docstatus != 1
        or dispatch.dispatch_type != "Outbound"
        or dispatch.delivery_status != "Delivered"
    ):
        frappe.throw(_("A delivered Outbound Dispatch is required before sale."))
    reservation = frappe.db.get_value(
        "Demo Asset Reservation",
        row.asset_reservation,
        ["name", "asset", "fulfillment_allocation", "status"],
        as_dict=True,
        for_update=True,
    )
    if (
        not reservation
        or reservation.asset != row.resolved_asset
        or reservation.fulfillment_allocation != allocation
        or reservation.status != "Consumed"
    ):
        frappe.throw(_("The allocation reservation must be consumed before sale."))
    return_movements = frappe.get_all(
        "Asset Movement",
        filters={
            "reference_doctype": "Dispatch",
            "reference_name": dispatch.name,
            "purpose": "Receipt",
            "docstatus": ("<", 2),
        },
        pluck="name",
        order_by="name asc",
    )
    blocked_movements = []
    for name in return_movements:
        frappe.db.get_value("Asset Movement", name, "name", for_update=True)
        movement_item = frappe.db.get_value(
            "Asset Movement Item",
            {"parent": name, "asset": row.resolved_asset},
            "name",
            for_update=True,
        )
        if movement_item:
            blocked_movements.append(name)
    if blocked_movements:
        frappe.throw(_("A started return movement blocks this sale."))
    return_dispatches = frappe.get_all(
        "Dispatch",
        filters={"original_dispatch": dispatch.name, "dispatch_type": "Return", "docstatus": ("<", 2)},
        pluck="name",
        order_by="name asc",
    )
    blocked_dispatches = []
    for name in return_dispatches:
        frappe.db.get_value("Dispatch", name, "name", for_update=True)
        return_transfer = frappe.db.get_value(
            "Dispatch Transfer",
            {"parent": name, "fulfillment_allocation": allocation},
            "name",
            for_update=True,
        )
        if return_transfer:
            blocked_dispatches.append(name)
    if blocked_dispatches:
        frappe.throw(_("A started return Dispatch blocks this sale."))
    successors = frappe.get_all(
        "Demo Asset Reservation",
        filters={"asset": row.resolved_asset, "status": "Active"},
        fields=["name", "fulfillment_allocation"],
        order_by="name asc",
    )
    successors = [
        frappe.db.get_value(
            "Demo Asset Reservation",
            candidate.name,
            ["name", "fulfillment_allocation"],
            as_dict=True,
            for_update=True,
        )
        for candidate in successors
    ]
    if any(candidate and candidate.fulfillment_allocation != allocation for candidate in successors):
        frappe.throw(_("A successor reservation blocks this sale."))
    return row, plan, asset, dispatch


@frappe.whitelist(methods=["POST"])
def create_demo_sales_invoice(allocation: str, customer: str) -> dict[str, Any]:
    if not set(frappe.get_roles()) & {"Accounts User", "Accounts Manager", "System Manager"}:
        frappe.throw(_("Accounts access is required to sell a Demo Asset."), frappe.PermissionError)
    if not frappe.has_permission("Sales Invoice", "create"):
        frappe.throw(_("Sales Invoice create permission is required."), frappe.PermissionError)
    if not frappe.has_permission("Customer", "read", customer):
        frappe.throw(_("Customer read permission is required."), frappe.PermissionError)
    locked = frappe.db.get_value(
        "Material Request Fulfillment Allocation",
        allocation,
        ["name", "current_sales_invoice", "sale_attempt"],
        as_dict=True,
        for_update=True,
    )
    if not locked:
        frappe.throw(_("The Demo allocation does not exist."))
    if locked.current_sales_invoice:
        current = frappe.db.get_value(
            "Sales Invoice",
            locked.current_sales_invoice,
            [
                "name",
                "docstatus",
                "customer",
                "demo_fulfillment_allocation",
                "demo_sale_attempt",
                "demo_sale_operation_id",
            ],
            as_dict=True,
            for_update=True,
        )
        if (
            current
            and current.docstatus < 2
            and current.customer == customer
            and current.demo_fulfillment_allocation == allocation
            and current.demo_sale_attempt == locked.sale_attempt
            and current.demo_sale_operation_id == f"demo-sale:{allocation}:{locked.sale_attempt}"
        ):
            return {"data": current.name, "message": _("Demo Sales Invoice already exists.")}
        frappe.throw(_("The current Demo sale attempt is inconsistent and must be reviewed."))
    row, plan, asset, dispatch = _demo_sale_context(allocation)
    attempt = int(row.sale_attempt or 0) + 1
    operation_id = f"demo-sale:{allocation}:{attempt}"
    existing = frappe.db.get_value("Sales Invoice", {"demo_sale_operation_id": operation_id}, "name")
    if existing:
        return {"data": existing, "message": _("Demo Sales Invoice already exists.")}
    invoice = cast(Document, make_sales_invoice(asset.name, asset.item_code, plan.company, 1))
    invoice.set("customer", customer)
    invoice.run_method("set_missing_values")
    invoice.set("update_stock", 0)
    invoice.set("demo_fulfillment_allocation", allocation)
    invoice.set("demo_outbound_dispatch", dispatch.name)
    invoice.set("demo_sale_attempt", attempt)
    invoice.set("demo_sale_operation_id", operation_id)
    if len(invoice.get("items") or []) != 1:
        frappe.throw(_("Demo Asset sale must contain exactly one invoice item."))
    item = invoice.get("items")[0]
    if item.get("item_code") != asset.item_code or item.get("qty") != 1 or item.get("asset") != asset.name:
        frappe.throw(_("Demo Asset sale provenance does not match the fixed Asset."))
    if not frappe.db.get_value("Item", asset.item_code, "is_fixed_asset"):
        frappe.throw(_("The sale item must be a fixed-asset Item."))
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("The selected Customer does not exist."))
    invoice.insert()
    frappe.db.set_value(
        "Material Request Fulfillment Allocation",
        allocation,
        {"current_sales_invoice": invoice.name, "sale_attempt": attempt},
        update_modified=False,
    )
    return {"data": invoice.name, "message": _("Demo Sales Invoice draft created.")}


def validate_demo_sales_invoice(doc: Document, method: str | None = None) -> None:
    if not doc.get("demo_fulfillment_allocation"):
        return
    row, plan, asset, dispatch = _demo_sale_context(cast(str, doc.get("demo_fulfillment_allocation")))
    if (
        doc.get("demo_sale_attempt") != row.sale_attempt
        or doc.get("demo_sale_operation_id") != f"demo-sale:{row.name}:{doc.get('demo_sale_attempt')}"
        or doc.get("demo_outbound_dispatch") != dispatch.name
        or not doc.get("customer")
        or doc.get("update_stock")
        or row.current_sales_invoice != doc.name
    ):
        frappe.throw(_("Demo Sales Invoice provenance is invalid."))
    items = cast(list[Any], doc.get("items") or [])
    if (
        len(items) != 1
        or items[0].get("item_code") != asset.item_code
        or items[0].get("asset") != asset.name
        or items[0].get("qty") != 1
        or not items[0].get("is_fixed_asset")
        or not frappe.db.get_value("Item", asset.item_code, "is_fixed_asset")
    ):
        frappe.throw(_("Demo Sales Invoice must contain the exact fixed Asset item and quantity one."))
    if doc.get("company") != plan.company or not frappe.db.exists("Customer", doc.get("customer")):
        frappe.throw(_("Demo Sales Invoice company or Customer is invalid."))


def on_submit_demo_sales_invoice(doc: Document, method: str) -> None:
    if not doc.get("demo_fulfillment_allocation"):
        return
    allocation = frappe.db.get_value(
        "Material Request Fulfillment Allocation",
        doc.get("demo_fulfillment_allocation"),
        ["name", "current_sales_invoice", "sale_attempt", "lifecycle_state", "resolved_asset"],
        as_dict=True,
        for_update=True,
    )
    if (
        not allocation
        or allocation.current_sales_invoice != doc.name
        or allocation.sale_attempt != doc.get("demo_sale_attempt")
        or allocation.lifecycle_state != "Delivered"
        or doc.get("demo_sale_operation_id") != f"demo-sale:{allocation.name}:{allocation.sale_attempt}"
        or frappe.db.get_value("Asset", allocation.resolved_asset, "status", for_update=True) != "Sold"
    ):
        frappe.throw(_("The Demo sale result no longer matches its current allocation attempt."))
    frappe.db.set_value(
        "Material Request Fulfillment Allocation",
        allocation.name,
        {
            "current_sales_invoice": doc.name,
            "sale_attempt": doc.get("demo_sale_attempt"),
            "lifecycle_state": "Sold",
        },
        update_modified=False,
    )


def on_cancel_demo_sales_invoice(doc: Document, method: str) -> None:
    if not doc.get("demo_fulfillment_allocation"):
        return
    allocation = frappe.db.get_value(
        "Material Request Fulfillment Allocation",
        doc.get("demo_fulfillment_allocation"),
        ["name", "current_sales_invoice", "sale_attempt", "lifecycle_state", "resolved_asset"],
        as_dict=True,
        for_update=True,
    )
    if (
        not allocation
        or allocation.current_sales_invoice != doc.name
        or allocation.sale_attempt != doc.get("demo_sale_attempt")
        or allocation.lifecycle_state != "Sold"
        or doc.get("demo_sale_operation_id") != f"demo-sale:{allocation.name}:{allocation.sale_attempt}"
        or frappe.db.get_value("Asset", allocation.resolved_asset, "status", for_update=True) == "Sold"
    ):
        frappe.throw(_("Only the current Demo sale attempt can restore its allocation."))
    frappe.db.set_value(
        "Material Request Fulfillment Allocation",
        allocation.name,
        {"current_sales_invoice": None, "lifecycle_state": "Delivered"},
        update_modified=False,
    )
