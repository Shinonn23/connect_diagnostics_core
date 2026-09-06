# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_invoice


class TestSalesInvoicePrint(UnitTestCase):
    @patch.object(sales_invoice, "get_document_print_context")
    def test_selected_print_format_resolves_its_configuration(self, mocked_context: MagicMock) -> None:
        mocked_context.return_value = {"show_batch_serial": False}
        doc = frappe._dict({"doctype": "Sales Invoice", "items": []})

        with patch.object(
            frappe.local,
            "form_dict",
            frappe._dict(format="Abbreviated Tax Invoice And Receipt"),
        ):
            sales_invoice.get_sales_invoice_print_context(doc)

        mocked_context.assert_called_once_with(doc, "abbreviated_tax_invoice")

    @patch.object(sales_invoice, "get_item_traceability")
    @patch.object(sales_invoice, "get_document_print_context")
    def test_item_pages_keep_traceability_items_together(
        self, mocked_context: MagicMock, mocked_traceability: MagicMock
    ) -> None:
        mocked_context.return_value = {"show_batch_serial": True}
        mocked_traceability.side_effect = [
            {"batch_nos": [], "serial_nos": []},
            {"batch_nos": ["B-1"], "serial_nos": ["SN-1"]},
            {"batch_nos": [], "serial_nos": []},
        ]
        doc = frappe._dict(
            {
                "items": [
                    {"idx": 1, "item_code": "ITEM-1"},
                    {"idx": 2, "item_code": "ITEM-2"},
                    {"idx": 3, "item_code": "ITEM-3"},
                ]
            }
        )

        result = sales_invoice.get_sales_invoice_print_context(doc)

        self.assertEqual(result["item_page_count"], 1)
        self.assertEqual([item["idx"] for item in result["item_pages"][0]], [1, 2, 3])
        self.assertEqual(
            result["item_pages"][0][1]["traceability_lines"],
            [
                {"label": "Batch", "value": "B-1"},
                {"label": "SN", "value": "SN-1"},
            ],
        )

    @patch.object(sales_invoice, "get_item_traceability")
    @patch.object(sales_invoice, "get_document_print_context")
    def test_page_capacity_starts_a_new_page_before_item(
        self, mocked_context: MagicMock, mocked_traceability: MagicMock
    ) -> None:
        mocked_context.return_value = {"show_batch_serial": True}
        mocked_traceability.return_value = {"batch_nos": [], "serial_nos": []}
        doc = frappe._dict({"items": [{"idx": idx} for idx in range(1, 13)]})

        result = sales_invoice.get_sales_invoice_print_context(doc)

        self.assertEqual(result["item_page_count"], 2)
        self.assertEqual([item["idx"] for item in result["item_pages"][0]], list(range(1, 12)))
        self.assertEqual([item["idx"] for item in result["item_pages"][1]], [12])

    @patch.object(sales_invoice, "get_item_traceability")
    @patch.object(sales_invoice, "get_document_print_context")
    def test_page_capacity_uses_measured_traceability_height(
        self, mocked_context: MagicMock, mocked_traceability: MagicMock
    ) -> None:
        mocked_context.return_value = {"show_batch_serial": True}
        mocked_traceability.side_effect = [
            {"records": [{"batch_no": "x" * 400, "serial_no": ""}]},
            *({"batch_nos": [], "serial_nos": []} for _ in range(10)),
        ]
        doc = frappe._dict(
            {
                "items": [
                    {"idx": 1, "item_code": "ITEM-1"},
                    *({"idx": idx} for idx in range(2, 12)),
                ]
            }
        )

        result = sales_invoice.get_sales_invoice_print_context(doc)

        first_item = result["item_pages"][0][0]
        self.assertGreater(first_item["line_count"], 1)
        self.assertLess(len(result["item_pages"][0]), 11)
        self.assertEqual(sum(item["line_count"] for item in result["item_pages"][0]), 11)

    @patch.object(sales_invoice, "get_item_traceability")
    @patch.object(sales_invoice, "get_document_print_context")
    def test_traceability_renders_one_line_per_record_without_joining_values(
        self, mocked_context: MagicMock, mocked_traceability: MagicMock
    ) -> None:
        mocked_context.return_value = {"show_batch_serial": True}
        mocked_traceability.return_value = {
            "batch_nos": ["B-1", "B-2"],
            "serial_nos": ["SN-1", "SN-2"],
            "records": [
                {"batch_no": "B-1", "serial_no": "SN-1"},
                {"batch_no": "B-2", "serial_no": "SN-2"},
            ],
        }

        result = sales_invoice.get_sales_invoice_print_context(
            frappe._dict({"items": [{"idx": 1, "item_code": "ITEM-1"}]})
        )

        self.assertEqual(
            result["item_pages"][0][0]["traceability_lines"],
            [
                {"label": "Batch / SN", "value": "B-1 / SN-1"},
                {"label": "Batch / SN", "value": "B-2 / SN-2"},
            ],
        )
