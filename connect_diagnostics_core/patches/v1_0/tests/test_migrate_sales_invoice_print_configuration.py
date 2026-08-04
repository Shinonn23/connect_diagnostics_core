# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_sales_invoice_print_configuration


class TestMigrateSalesInvoicePrintConfiguration(UnitTestCase):
    def test_existing_records_receive_all_named_sales_invoice_selections(self) -> None:
        self.assertEqual(
            migrate_sales_invoice_print_configuration.SALES_INVOICE_PRINT_DEFAULTS,
            {
                "print_tax_invoice_original": 1,
                "print_tax_invoice_customer_copy": 1,
                "print_tax_invoice_accounting_copy": 1,
                "print_tax_invoice_sales_copy": 1,
                "show_tax_invoice_batch_serial": 1,
            },
        )
