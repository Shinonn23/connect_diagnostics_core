# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Single source of truth for the documents the print configuration covers.

Every other part of the print configuration derives from ``PRINT_DOCUMENTS``:
the print sidebar controls and the Jinja print context. Print options are chosen
per print in the sidebar; there is no stored per-Customer configuration. Adding a
document type is a change here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass

from connect_diagnostics_core.setup import quotation as quotation_setup

LANGUAGE_THAI = "Thai"
LANGUAGE_ENGLISH = "English"
LANGUAGE_BILINGUAL = "Thai / English"
LANGUAGE_OPTIONS = (LANGUAGE_THAI, LANGUAGE_ENGLISH, LANGUAGE_BILINGUAL)

KIND_ORIGINAL = "Original"
KIND_COPY = "Copy"

SOURCE_DEFAULT = "Default"
SOURCE_DOCUMENT = "This document"
SOURCE_REQUEST = "This print"


@dataclass(frozen=True)
class CopyDefinition:
    """One named page set within a printed document."""

    key: str
    label_th: str
    label_en: str
    kind: str
    default_count: int

    def label(self, language: str) -> str:
        if language == LANGUAGE_THAI:
            return self.label_th
        if language == LANGUAGE_ENGLISH:
            return self.label_en
        return f"{self.label_th} / {self.label_en}"


@dataclass(frozen=True)
class PrintDocument:
    """A document type the Customer print configuration can control."""

    key: str
    label: str
    print_formats: tuple[str, ...]
    doctypes: tuple[str, ...]
    language_selectable: bool
    offers_batch_serial: bool
    copies: tuple[CopyDefinition, ...]
    extra_fields: tuple[str, ...] = ()
    document_fields: tuple[str, ...] = ()
    fixed_language: str = ""

    def copy(self, copy_key: str) -> CopyDefinition | None:
        return next((definition for definition in self.copies if definition.key == copy_key), None)


GENERIC_COPIES = (
    CopyDefinition(
        key="original",
        label_th="ต้นฉบับ",
        label_en="Original",
        kind=KIND_ORIGINAL,
        default_count=1,
    ),
    CopyDefinition(
        key="copy",
        label_th="สำเนา",
        label_en="Copy",
        kind=KIND_COPY,
        default_count=0,
    ),
)

TAX_INVOICE_COPIES = (
    CopyDefinition(
        key="original",
        label_th="ต้นฉบับ (สำหรับลูกค้า)",
        label_en="Original (Customer)",
        kind=KIND_ORIGINAL,
        default_count=1,
    ),
    CopyDefinition(
        key="customer",
        label_th="สำเนา (สำหรับลูกค้า)",
        label_en="Copy (Customer)",
        kind=KIND_COPY,
        default_count=1,
    ),
    CopyDefinition(
        key="accounting",
        label_th="สำเนา (สำหรับฝ่ายบัญชี)",
        label_en="Copy (Accounting)",
        kind=KIND_COPY,
        default_count=1,
    ),
    CopyDefinition(
        key="sales",
        label_th="สำเนา (สำหรับฝ่ายขาย)",
        label_en="Copy (Sales)",
        kind=KIND_COPY,
        default_count=1,
    ),
)

# Quotation values the print sidebar may override for one request. Validity
# text and delivery terms are filled in on the document itself and are no
# longer overridable per print -- signatory type and the request-only manager
# selection are the Quotation-specific sidebar controls.
QUOTATION_EXTRA_FIELDS = ("quotation_signatory_type", "manager_signatory_employee")

# Set on the transaction itself, not on Customer or Template. A non-empty value
# on the document wins over the resolved default.
QUOTATION_DOCUMENT_FIELDS = (
    "quotation_signatory_type",
    "sales_representative_employee",
    "edit_validity_text",
    "validity_text",
    "quotation_delivery_terms",
)

PRINT_DOCUMENTS: tuple[PrintDocument, ...] = (
    PrintDocument(
        key="quotation",
        label="Quotation",
        print_formats=("Quotation",),
        doctypes=("Quotation",),
        language_selectable=True,
        offers_batch_serial=False,
        copies=GENERIC_COPIES,
        extra_fields=QUOTATION_EXTRA_FIELDS,
        document_fields=QUOTATION_DOCUMENT_FIELDS,
    ),
    PrintDocument(
        key="sales_order",
        label="Sales Order",
        print_formats=("Sales Order",),
        doctypes=("Sales Order",),
        language_selectable=False,
        offers_batch_serial=False,
        copies=GENERIC_COPIES,
        fixed_language=LANGUAGE_THAI,
    ),
    PrintDocument(
        key="tax_invoice",
        label="Tax Invoice",
        print_formats=("Tax Invoice Delivery Note and Invoice",),
        doctypes=("Sales Invoice",),
        language_selectable=False,
        offers_batch_serial=True,
        copies=TAX_INVOICE_COPIES,
        fixed_language=LANGUAGE_THAI,
    ),
    PrintDocument(
        key="abbreviated_tax_invoice",
        label="Abbreviated Tax Invoice",
        print_formats=("Abbreviated Tax Invoice And Receipt",),
        doctypes=(),
        language_selectable=True,
        offers_batch_serial=False,
        copies=GENERIC_COPIES,
    ),
    PrintDocument(
        key="receipt",
        label="Receipt",
        print_formats=("Receipt",),
        doctypes=("Payment Entry",),
        language_selectable=True,
        offers_batch_serial=False,
        copies=GENERIC_COPIES,
    ),
)

DOCUMENT_BY_KEY: dict[str, PrintDocument] = {document.key: document for document in PRINT_DOCUMENTS}

# Registry defaults for every resolved scalar, including the Quotation values
# that only the document itself carries. Chosen per print in the sidebar; there
# is no stored per-Customer configuration.
SCALAR_DEFAULTS: dict[str, object] = {
    "customer_print_name": "",
    "quotation_signatory_type": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
    "manager_signatory_employee": "",
    "edit_validity_text": 0,
    "validity_text": "",
    "quotation_delivery_terms": "",
}


def get_document(key: str) -> PrintDocument | None:
    """Return the registered document for a configuration key."""
    return DOCUMENT_BY_KEY.get(key)


def resolve_document_key(doctype: str, print_format: str = "") -> str:
    """Return the configuration key for a print format, falling back to the DocType."""
    if print_format:
        for document in PRINT_DOCUMENTS:
            if print_format in document.print_formats:
                return document.key
    for document in PRINT_DOCUMENTS:
        if doctype in document.doctypes:
            return document.key
    return ""


def default_language(document: PrintDocument) -> str:
    """Return the language a document starts from, honouring a fixed language."""
    return document.fixed_language or LANGUAGE_THAI
