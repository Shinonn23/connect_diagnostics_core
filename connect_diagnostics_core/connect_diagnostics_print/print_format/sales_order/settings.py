# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only sidebar settings owned by the Sales Order Print Format."""

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    GENERIC_COPIES,
    LANGUAGE_THAI,
    PrintDocument,
)

PRINT_DOCUMENT = PrintDocument(
    key="sales_order",
    label="Sales Order",
    print_formats=("Sales Order",),
    doctypes=("Sales Order",),
    language_selectable=False,
    offers_batch_serial=False,
    copies=GENERIC_COPIES,
    defaults={"customer_print_name": ""},
    fixed_language=LANGUAGE_THAI,
)
