# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only settings for the Thai tax-invoice Print Format."""

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    LANGUAGE_THAI,
    SALES_INVOICE_COPIES,
    PrintDocument,
    sales_invoice_delivery_note_sidebar,
)

PRINT_DOCUMENT = PrintDocument(
    key="tax_invoice",
    label="ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
    print_formats=("ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",),
    doctypes=("Sales Invoice",),
    language_selectable=False,
    offers_batch_serial=True,
    copies=SALES_INVOICE_COPIES,
    defaults={"customer_print_name": "", "show_delivery_note": 1},
    fixed_language=LANGUAGE_THAI,
    extra_fields=("show_delivery_note",),
    sidebar_extension=sales_invoice_delivery_note_sidebar,
)
