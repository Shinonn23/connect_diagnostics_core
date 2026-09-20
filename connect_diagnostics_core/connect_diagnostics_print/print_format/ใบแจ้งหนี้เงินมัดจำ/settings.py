# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only settings for the deposit-invoice Print Format."""

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    LANGUAGE_THAI,
    SALES_INVOICE_COPIES,
    PrintDocument,
)

PRINT_DOCUMENT = PrintDocument(
    key="deposit_invoice",
    label="ใบแจ้งหนี้เงินมัดจำ",
    print_formats=("ใบแจ้งหนี้เงินมัดจำ",),
    doctypes=(),
    language_selectable=False,
    offers_batch_serial=True,
    copies=SALES_INVOICE_COPIES,
    defaults={"customer_print_name": ""},
    fixed_language=LANGUAGE_THAI,
    fallback_to_doctype=False,
)
