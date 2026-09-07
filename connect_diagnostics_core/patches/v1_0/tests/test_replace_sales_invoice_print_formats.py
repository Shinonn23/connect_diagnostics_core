# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import replace_sales_invoice_print_formats


class TestReplaceSalesInvoicePrintFormats(UnitTestCase):
    def test_renamed_thai_formats_map_to_spaced_names(self) -> None:
        self.assertEqual(
            replace_sales_invoice_print_formats.FORMAT_REPLACEMENTS["ใบกำกับภาษี-ใบแจ้งหนี้-ใบส่งของ"],
            "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
        )
        self.assertEqual(
            replace_sales_invoice_print_formats.FORMAT_REPLACEMENTS["ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ"],
            "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ",
        )

    @patch.object(replace_sales_invoice_print_formats.frappe, "clear_cache")
    @patch.object(replace_sales_invoice_print_formats.frappe, "delete_doc")
    @patch.object(replace_sales_invoice_print_formats.frappe.db, "exists", return_value=True)
    @patch.object(replace_sales_invoice_print_formats.frappe.db, "set_value")
    @patch.object(
        replace_sales_invoice_print_formats.frappe,
        "get_all",
        return_value=[
            {"name": "Sales Invoice-default_print_format", "value": "Tax Invoice Delivery Note and Invoice"}
        ],
    )
    @patch.object(replace_sales_invoice_print_formats.frappe, "reload_doc")
    def test_execute_replaces_defaults_and_removes_retired_formats(
        self,
        reload_doc: MagicMock,
        _get_all: MagicMock,
        set_value: MagicMock,
        exists: MagicMock,
        delete_doc: MagicMock,
        clear_cache: MagicMock,
    ) -> None:
        replace_sales_invoice_print_formats.execute()

        self.assertEqual(
            reload_doc.call_args_list,
            [
                call("Connect Diagnostics Print", "print_format", fixture, force=True)
                for fixture in replace_sales_invoice_print_formats.PRINT_FORMAT_FIXTURES
            ],
        )
        set_value.assert_called_once_with(
            "Property Setter",
            "Sales Invoice-default_print_format",
            "value",
            "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
            update_modified=False,
        )
        self.assertEqual(
            delete_doc.call_args_list,
            [
                call("Print Format", print_format, force=True, ignore_missing=True)
                for print_format in replace_sales_invoice_print_formats.FORMAT_REPLACEMENTS
            ],
        )
        clear_cache.assert_called_once_with(doctype="Sales Invoice")
