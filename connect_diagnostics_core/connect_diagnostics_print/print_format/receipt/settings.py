# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only sidebar settings owned by the Receipt Print Format."""

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    GENERIC_COPIES,
    PrintDocument,
)

PRINT_DOCUMENT = PrintDocument(
    key="receipt",
    label="Receipt",
    print_formats=("Receipt",),
    doctypes=("Payment Entry",),
    language_selectable=True,
    offers_batch_serial=False,
    copies=GENERIC_COPIES,
    defaults={"customer_print_name": ""},
)
