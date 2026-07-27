# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

PRINT_FORMAT_ROOT = Path(__file__).parents[2] / "connect_diagnostics_core" / "print_format"
PRINT_FORMAT_FILES = (
    "abbreviated_tax_invoice_and_receipt/abbreviated_tax_invoice_and_receipt.json",
    "goods_receipt/goods_receipt.json",
    "purchase_order/purchase_order.json",
    "quotation/quotation.json",
    "receipt/receipt.json",
    "sales_order/sales_order.json",
    "tax_invoice_delivery_note_and_invoice/tax_invoice_delivery_note_and_invoice.json",
)


def load_print_formats() -> list[dict[str, Any]]:
    return [
        json.loads((PRINT_FORMAT_ROOT / relative_path).read_text()) for relative_path in PRINT_FORMAT_FILES
    ]


class TestPrintFormats(UnitTestCase):
    def test_print_format_json_files_are_valid(self) -> None:
        print_formats = load_print_formats()

        self.assertEqual(len(print_formats), 7)
        self.assertTrue(all(print_format["html"] for print_format in print_formats))
        self.assertTrue(all(print_format["css"] for print_format in print_formats))

    def test_templates_do_not_define_money_macros(self) -> None:
        for print_format in load_print_formats():
            html = print_format["html"]
            self.assertNotIn("{% macro money", html, print_format["name"])
            self.assertNotIn("{% macro blank_zero", html, print_format["name"])

    def test_templates_do_not_contain_inline_style_blocks(self) -> None:
        for print_format in load_print_formats():
            self.assertNotIn("<style", print_format["html"].lower(), print_format["name"])

    def test_templates_do_not_use_background_images(self) -> None:
        for print_format in load_print_formats():
            content = f"{print_format['html']}\n{print_format['css']}"
            self.assertNotIn("background-image:", content, print_format["name"])
            self.assertNotIn("--page-bg", content, print_format["name"])
            self.assertNotIn("/images/print_formats/", content, print_format["name"])

    def test_templates_use_semantic_document_elements(self) -> None:
        for print_format in load_print_formats():
            html = print_format["html"].lower()
            self.assertIn("<header", html, print_format["name"])
            self.assertIn("<section", html, print_format["name"])
            self.assertIn("<footer", html, print_format["name"])
