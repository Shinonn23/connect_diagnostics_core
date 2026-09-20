# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Attach the source Purchase Order copy to a Customer's tax invoice PDF.

Some Customers only accept goods with a copy of the Purchase Order we placed
with our supplier, which proves where the goods came from. The Customer records
that in ``source_purchase_order_copy_required``; the Sales Invoice lists the
Purchase Orders in its ``source_purchase_orders`` table, one row per order, each
naming either a linked Purchase Order or, for one raised before ERPNext, an
attached file, with its own copy count.

**The copy is concatenated as extra PDF pages, never rendered inside the tax
invoice format.** Nesting was tried and does not work: the ``Purchase Order``
format's CSS sets ``@page``, ``html, body`` and ``.print-format`` globally and
would rewrite the invoice's own page geometry, and its template calls
``register_print``, which would write a Print Log row claiming a Purchase Order
was sent to a supplier every time a Customer's invoice printed. Rendering each
document independently and joining the PDFs avoids both.

This therefore covers the PDF channel only. The Print button hands HTML to the
browser, which cannot join a PDF, so the Sales Invoice form offers a separate
button to print the copy — see ``public/js/custom/sales_invoice/doctype.js``.

Rendering the Purchase Order deliberately bypasses its print permission. The
copy is a page the Customer is meant to receive with the invoice, so anyone
allowed to print the invoice is allowed to produce it; requiring Purchase Order
print rights would instead stop sales staff from downloading their own invoices.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe.utils import cint
from pypdf import PdfWriter

from connect_diagnostics_core.api.erpnext import print_configuration
from connect_diagnostics_core.setup import print_documents

SOURCE_PRINT_FORMAT = "Purchase Order"
TAX_INVOICE_CONFIGURATION = "tax_invoice"
PDF_SIGNATURE = b"%PDF"


def append_source_copy(doctype: str, name: str, print_format: str | None = None) -> None:
    """Append the required source Purchase Order copies to the response PDF.

    Fail-open like the print audit: a Customer must still receive their invoice
    when the copy cannot be produced, so any failure is logged with context and
    the invoice PDF is returned unchanged.
    """
    try:
        _append_source_copy(doctype, name, print_format)
    except Exception:
        frappe.log_error(
            title="Source Purchase Order copy not attached",
            message=(
                f"doctype={doctype} name={name} print_format={print_format}\n\n{frappe.get_traceback()}"
            ),
        )


def _append_source_copy(doctype: str, name: str, print_format: str | None) -> None:
    if print_documents.resolve_document_key(doctype, _text(print_format)) != TAX_INVOICE_CONFIGURATION:
        return

    invoice_pdf = _response_pdf()
    if not invoice_pdf:
        return

    doc = cast(Document, frappe.get_doc(doctype, name))
    values = print_configuration.get_document_configuration(doc, TAX_INVOICE_CONFIGURATION)
    if not cint(values.get("source_purchase_order_copy_required")):
        return

    default_copies = max(cint(values.get("purchase_order_copy_count")), 0)
    joined = _join_source_copies(doc, invoice_pdf, default_copies)
    if joined is None:
        return

    frappe.local.response.filecontent = joined


def _join_source_copies(doc: Document, invoice_pdf: bytes, default_copies: int) -> bytes | None:
    """Append every row's source copy to the invoice, in table order.

    A row with a blank copy count falls back to the Customer's default count, so a
    Customer that always wants the same number of copies need not repeat it per row.
    Returns the joined PDF, or ``None`` when nothing was appended.
    """
    writer = PdfWriter()
    writer.append(BytesIO(invoice_pdf))
    appended = False

    for row in cast(Sequence[Any], doc.get("source_purchase_orders") or ()):
        copies = _row_copies(row, default_copies)
        if copies <= 0:
            continue
        source_pdf = _row_pdf(row)
        if not source_pdf:
            continue
        for _copy in range(copies):
            writer.append(BytesIO(source_pdf))
        appended = True

    if not appended:
        writer.close()
        return None

    buffer = BytesIO()
    writer.write(buffer)
    writer.close()
    return buffer.getvalue()


def _row_copies(row: Any, default_copies: int) -> int:
    raw = _row_value(row, "copies")
    if raw in (None, ""):
        return default_copies
    return max(cint(raw), 0)


def _row_pdf(row: Any) -> bytes | None:
    """Return one row's source copy as PDF bytes, from its order or its file."""
    purchase_order = _text(_row_value(row, "purchase_order"))
    if purchase_order:
        return _render_purchase_order(purchase_order)

    attachment = _text(_row_value(row, "purchase_order_file"))
    return _attached_pdf(attachment) if attachment else None


def _row_value(row: Any, fieldname: str) -> Any:
    getter = getattr(row, "get", None)
    return getter(fieldname) if callable(getter) else getattr(row, fieldname, None)


def _render_purchase_order(purchase_order: str) -> bytes:
    """Render the app's Purchase Order format for a document the Customer receives."""
    previous = frappe.flags.ignore_print_permissions
    frappe.flags.ignore_print_permissions = True
    try:
        return cast(
            bytes,
            frappe.get_print(
                "Purchase Order",
                purchase_order,
                SOURCE_PRINT_FORMAT,
                as_pdf=True,
            ),
        )
    finally:
        frappe.flags.ignore_print_permissions = previous


def _attached_pdf(file_url: str) -> bytes | None:
    """Return an attached file's bytes, but only when it really is a PDF.

    A scanned order can be uploaded as an image, which cannot be concatenated.
    Those stay a manual print step rather than silently producing nothing.
    """
    if not frappe.db.exists("File", {"file_url": file_url}):
        return None

    content = cast(Any, frappe.get_doc("File", {"file_url": file_url}).get_content())
    if isinstance(content, bytes) and content.startswith(PDF_SIGNATURE):
        return content
    return None


def _join(invoice_pdf: bytes, source_pdf: bytes, copies: int) -> bytes:
    writer = PdfWriter()
    writer.append(BytesIO(invoice_pdf))
    for _copy in range(copies):
        writer.append(BytesIO(source_pdf))

    joined = BytesIO()
    writer.write(joined)
    writer.close()
    return joined.getvalue()


def _response_pdf() -> bytes | None:
    response = getattr(frappe.local, "response", None)
    if response is None or _text(response.get("type")) != "pdf":
        return None
    content = response.get("filecontent")
    return content if isinstance(content, bytes) and content.startswith(PDF_SIGNATURE) else None


def _text(value: Any) -> str:
    return str(value or "").strip()
