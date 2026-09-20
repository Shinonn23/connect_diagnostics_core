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
