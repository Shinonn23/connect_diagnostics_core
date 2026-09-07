# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared types for Print Format-local sidebar setting declarations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import frappe

LANGUAGE_THAI = "Thai"
LANGUAGE_ENGLISH = "English"
LANGUAGE_BILINGUAL = "Thai / English"
LANGUAGE_OPTIONS = (LANGUAGE_THAI, LANGUAGE_ENGLISH, LANGUAGE_BILINGUAL)

KIND_ORIGINAL = "Original"
KIND_COPY = "Copy"


@dataclass(frozen=True)
class CopyDefinition:
    """One named page set within a printed document."""

    key: str
    label_th: str
    label_en: str
    kind: str
    default_count: int
    selection_mode: str = "count"
    always_include: bool = False
    custom_label: bool = False

    def label(self, language: str) -> str:
        if language == LANGUAGE_THAI:
            return self.label_th
        if language == LANGUAGE_ENGLISH:
            return self.label_en
        return f"{self.label_th} / {self.label_en}"


@dataclass(frozen=True)
class SidebarExtension:
    """Format-local sidebar fields and request defaults."""

    fields: tuple[dict[str, Any], ...] = ()
    values: Mapping[str, Any] = field(default_factory=dict)
    manager_signatories: tuple[Mapping[str, Any], ...] = ()


SidebarExtensionFactory = Callable[[str], SidebarExtension]


@dataclass(frozen=True)
class PrintDocument:
    """A Print Format and the request-only settings it owns."""

    key: str
    label: str
    print_formats: tuple[str, ...]
    doctypes: tuple[str, ...]
    language_selectable: bool
    offers_batch_serial: bool
    copies: tuple[CopyDefinition, ...]
    defaults: Mapping[str, Any] = field(default_factory=dict)
    extra_fields: tuple[str, ...] = ()
    document_fields: tuple[str, ...] = ()
    fixed_language: str = ""
    include_standard_sidebar_fields: bool = True
    sidebar_extension: SidebarExtensionFactory | None = None
    fallback_to_doctype: bool = True

    def copy(self, copy_key: str) -> CopyDefinition | None:
        return next((definition for definition in self.copies if definition.key == copy_key), None)


GENERIC_COPIES = (
    CopyDefinition("original", "ต้นฉบับ", "Original", KIND_ORIGINAL, 1),
    CopyDefinition("copy", "สำเนา", "Copy", KIND_COPY, 0),
)

TAX_INVOICE_COPIES = (
    CopyDefinition("original", "ต้นฉบับ (สำหรับลูกค้า)", "Original (Customer)", KIND_ORIGINAL, 1),
    CopyDefinition("customer", "สำเนา (สำหรับลูกค้า)", "Copy (Customer)", KIND_COPY, 1),
    CopyDefinition("accounting", "สำเนา (สำหรับฝ่ายบัญชี)", "Copy (Accounting)", KIND_COPY, 1),
    CopyDefinition("sales", "สำเนา (สำหรับฝ่ายขาย)", "Copy (Sales)", KIND_COPY, 1),
)


SALES_INVOICE_COPIES = (
    CopyDefinition(
        "company",
        "สำเนา (สำหรับบริษัท)",
        "Copy (Company)",
        KIND_COPY,
        1,
        always_include=True,
    ),
    CopyDefinition(
        "customer_original",
        "ต้นฉบับ (สำหรับลูกค้า)",
        "Original (Customer)",
        KIND_ORIGINAL,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "customer_copy",
        "สำเนา (สำหรับลูกค้า)",
        "Copy (Customer)",
        KIND_COPY,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "accounting_original",
        "ต้นฉบับ (สำหรับฝ่ายบัญชี)",
        "Original (Accounting)",
        KIND_ORIGINAL,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "accounting_copy",
        "สำเนา (สำหรับฝ่ายบัญชี)",
        "Copy (Accounting)",
        KIND_COPY,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "sales_original",
        "ต้นฉบับ (สำหรับฝ่ายขาย)",
        "Original (Sales)",
        KIND_ORIGINAL,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "sales_copy",
        "สำเนา (สำหรับฝ่ายขาย)",
        "Copy (Sales)",
        KIND_COPY,
        1,
        selection_mode="checkbox",
    ),
    CopyDefinition(
        "custom",
        "Custom Text",
        "Custom Text",
        KIND_COPY,
        1,
        selection_mode="checkbox",
        custom_label=True,
    ),
)


def sales_invoice_delivery_note_sidebar(docname: str) -> SidebarExtension:
    """Expose the delivery-note title switch only for linked invoices."""
    linked = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": docname, "delivery_note": ["is", "set"]},
        fields=["name"],
        limit=1,
    )
    if not linked:
        return SidebarExtension()
    return SidebarExtension(
        fields=(
            {
                "fieldname": "show_delivery_note",
                "label": "แสดงคำว่า ใบส่งของ",
                "fieldtype": "Check",
                "sales_invoice_delivery_note": True,
            },
        ),
        values={"show_delivery_note": 1},
    )
