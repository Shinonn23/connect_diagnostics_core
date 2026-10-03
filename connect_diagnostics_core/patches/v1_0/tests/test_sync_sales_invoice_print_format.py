# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import sync_sales_invoice_print_format


class TestSyncSalesInvoicePrintFormat(UnitTestCase):
    @patch.object(sync_sales_invoice_print_format.frappe, "reload_doc")
    def test_execute_reloads_the_owned_sales_invoice_format(self, mocked_reload_doc: MagicMock) -> None:
        sync_sales_invoice_print_format.execute()

        mocked_reload_doc.assert_called_once_with(
            "Connect Diagnostics Print",
            "print_format",
            "ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ",
            force=True,
        )
