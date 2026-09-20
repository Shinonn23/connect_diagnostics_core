# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from frappe import _
from frappe.model.document import Document
from pythainlp.util import bahttext

from connect_diagnostics_core.api.erpnext.print_configuration import get_document_print_context
from connect_diagnostics_core.api.erpnext.stock_traceability import get_item_traceability

ITEM_BODY_LINE_CAPACITY = 10


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
    """Build the Sales Invoice print context with traceability-aware pagination."""
    print_context = get_document_print_context(doc, "tax_invoice")
    items = [
        _prepare_print_item(row, print_context["show_batch_serial"])
        for row in cast(list[Any], doc.get("items") or [])
    ]
    item_pages = _paginate_items(items)
    return {
        "print_context": print_context,
        "item_pages": item_pages,
        "item_page_count": len(item_pages),
    }


def _prepare_print_item(row: Any, show_batch_serial: bool) -> dict[str, Any]:
    item = _row_as_dict(row)
    traceability = (
        get_item_traceability(item)
        if show_batch_serial
        else {"batch_nos": [], "serial_nos": [], "records": []}
    )
    traceability_lines = _traceability_lines(traceability)
    item["traceability_lines"] = traceability_lines
    item["line_count"] = 1 + sum(_display_line_count(trace["value"]) for trace in traceability_lines)
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


def _display_line_count(value: str) -> int:
    traceability_chars_per_line = 48
    return max((len(value) + traceability_chars_per_line - 1) // traceability_chars_per_line, 1)


def _paginate_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not items:
        return [[]]

    pages: list[list[dict[str, Any]]] = []
    current_page: list[dict[str, Any]] = []
    current_lines = 0
    for item in items:
        line_count = max(int(item["line_count"]), 1)
        if current_page and current_lines + line_count > ITEM_BODY_LINE_CAPACITY:
            pages.append(current_page)
            current_page = []
            current_lines = 0
        current_page.append(item)
        current_lines += line_count
        if current_lines >= ITEM_BODY_LINE_CAPACITY:
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
