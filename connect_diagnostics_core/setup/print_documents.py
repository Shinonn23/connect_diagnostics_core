# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Registry loader for Print Format-local sidebar setting declarations."""

from __future__ import annotations

from importlib import import_module
from typing import cast

from connect_diagnostics_core.connect_diagnostics_print.print_format.sales_order.settings import (
    PRINT_DOCUMENT as SALES_ORDER,
)
from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    GENERIC_COPIES,
    KIND_COPY,
    KIND_ORIGINAL,
    LANGUAGE_BILINGUAL,
    LANGUAGE_ENGLISH,
    LANGUAGE_OPTIONS,
    LANGUAGE_THAI,
    TAX_INVOICE_COPIES,
    CopyDefinition,
    PrintDocument,
)
from connect_diagnostics_core.connect_diagnostics_print.print_format.shipment_box_label.settings import (
    PRINT_DOCUMENT as SHIPMENT_BOX_LABEL,
)

SOURCE_DEFAULT = "Default"
SOURCE_DOCUMENT = "This document"
SOURCE_REQUEST = "This print"


def _load_print_document(module: str) -> PrintDocument:
    """Load one local declaration, including formats with Thai package names."""
    return cast(PrintDocument, import_module(module).PRINT_DOCUMENT)


QUOTATION = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสนอราคา.settings"
)
RECEIPT = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน.settings"
)
TAX_INVOICE = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ.settings"
)
ABBREVIATED_TAX_INVOICE = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ.settings"
)
FULL_RECEIPT = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ.settings"
)
DEPOSIT_INVOICE = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบแจ้งหนี้เงินมัดจำ.settings"
)
THAI_CREDIT_NOTE = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบลดหนี้.settings"
)
THAI_DEBIT_NOTE = _load_print_document(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเพิ่มหนี้.settings"
)

# Each format owns its declaration; this tuple only makes the installed
# declarations discoverable to the generic resolver.
PRINT_DOCUMENTS: tuple[PrintDocument, ...] = (
    QUOTATION,
    SALES_ORDER,
    TAX_INVOICE,
    ABBREVIATED_TAX_INVOICE,
    FULL_RECEIPT,
    DEPOSIT_INVOICE,
    THAI_CREDIT_NOTE,
    THAI_DEBIT_NOTE,
    RECEIPT,
    SHIPMENT_BOX_LABEL,
)

DOCUMENT_BY_KEY: dict[str, PrintDocument] = {document.key: document for document in PRINT_DOCUMENTS}


def get_document(key: str) -> PrintDocument | None:
    """Return the registered document, including a format-local declaration."""
    return DOCUMENT_BY_KEY.get(key)


def resolve_document_key(doctype: str, print_format: str = "") -> str:
    """Return the configured key, preferring the selected Print Format."""
    if print_format:
        for document in PRINT_DOCUMENTS:
            if print_format in document.print_formats:
                return document.key
    for document in PRINT_DOCUMENTS:
        if document.fallback_to_doctype and doctype in document.doctypes:
            return document.key
    return ""


def default_language(document: PrintDocument) -> str:
    """Return the initial language while honouring a format's fixed language."""
    return document.fixed_language or LANGUAGE_THAI
