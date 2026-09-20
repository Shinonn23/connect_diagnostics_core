# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only settings for the Thai abbreviated invoice Print Format."""

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    SALES_INVOICE_COPIES,
    PrintDocument,
)

PRINT_DOCUMENT = PrintDocument(
    key="abbreviated_tax_invoice",
    label="ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ",
    print_formats=("ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ",),
    doctypes=(),
    language_selectable=True,
    offers_batch_serial=False,
    copies=SALES_INVOICE_COPIES,
    defaults={"customer_print_name": ""},
)
