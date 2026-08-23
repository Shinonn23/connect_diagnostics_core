# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

PRINT_FORMAT_ROOT = Path(__file__).parents[2] / "connect_diagnostics_print" / "print_format"
PRINT_FORMAT_FILES = (
    "abbreviated_tax_invoice_and_receipt/abbreviated_tax_invoice_and_receipt.json",
    "credit_note/credit_note.json",
    "goods_receipt/goods_receipt.json",
    "monthly_count_sheet/monthly_count_sheet.json",
    "purchase_order/purchase_order.json",
    "quotation/quotation.json",
    "receipt/receipt.json",
    "sales_order/sales_order.json",
    "shipment_box_label/shipment_box_label.json",
    "tax_invoice_delivery_note_and_invoice/tax_invoice_delivery_note_and_invoice.json",
    "withholding_tax_cert_cd/withholding_tax_cert_cd.json",
    "yearly_count_sheet/yearly_count_sheet.json",
)

# Formats that overlay an official government form image. The layout is absolute
# positioning over that scan, so semantic sectioning and the no-background-image
# rule -- both aimed at our own recreated layouts -- do not apply.
FORM_OVERLAY_PRINT_FORMATS = ("Withholding Tax Cert CD",)

# Shipment Box Label switches its printed paper size (75 x 100 mm / 100 x 180 mm)
# from the print sidebar. wkhtmltopdf only reads page-width/page-height off
# .print-format inside <style>, and that value can only be known at render time
# (it depends on the sidebar's print_settings), so the conditional block must
# live in the html field rather than the static css field.
DYNAMIC_STYLE_PRINT_FORMATS = ("Shipment Box Label",)


def load_print_formats() -> list[dict[str, Any]]:
    return [
        json.loads((PRINT_FORMAT_ROOT / relative_path).read_text()) for relative_path in PRINT_FORMAT_FILES
    ]


class TestPrintFormats(UnitTestCase):
    def test_print_format_json_files_are_valid(self) -> None:
        print_formats = load_print_formats()

        self.assertEqual(len(print_formats), 12)
        self.assertTrue(all(print_format["html"] for print_format in print_formats))
        self.assertTrue(all(print_format["css"] for print_format in print_formats))

    def test_app_owned_print_formats_are_editable_through_desk(self) -> None:
        for print_format in load_print_formats():
            with self.subTest(name=print_format["name"]):
                self.assertEqual(print_format["standard"], "No")

    def test_print_formats_belong_to_the_print_module(self) -> None:
        for print_format in load_print_formats():
            with self.subTest(name=print_format["name"]):
                self.assertEqual(print_format["module"], "Connect Diagnostics Print")

    def test_register_print_is_not_swallowed_by_a_leading_comment(self) -> None:
        for print_format in load_print_formats():
            html = print_format["html"]
            if "register_print(doc)" not in html:
                continue
            before = html[: html.index("{{ register_print(doc) }}")]
            with self.subTest(name=print_format["name"]):
                self.assertEqual(before.count("{#"), before.count("#}"))

    def test_configuration_print_formats_are_newer_than_their_pre_configuration_versions(self) -> None:
        previous_timestamps = {
            "Quotation": "2026-07-30 22:50:00.000000",
            "Tax Invoice Delivery Note and Invoice": "2026-07-13 02:55:13.159262",
            "Abbreviated Tax Invoice And Receipt": "2026-07-15 01:06:43.299275",
            "Receipt": "2026-07-03 15:30:00.000000",
        }

        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        for name, previous in previous_timestamps.items():
            with self.subTest(name=name):
                self.assertGreater(formats[name]["modified"], previous)

    def test_templates_do_not_define_money_macros(self) -> None:
        for print_format in load_print_formats():
            html = print_format["html"]
            self.assertNotIn("{% macro money", html, print_format["name"])
            self.assertNotIn("{% macro blank_zero", html, print_format["name"])

    def test_templates_do_not_contain_inline_style_blocks(self) -> None:
        for print_format in load_print_formats():
            if print_format["name"] in DYNAMIC_STYLE_PRINT_FORMATS:
                continue
            self.assertNotIn("<style", print_format["html"].lower(), print_format["name"])

    def test_css_field_contains_no_jinja(self) -> None:
        """Frappe appends print_format.css verbatim; only html is rendered.

        A tag left in css is emitted literally, which silently breaks whatever it
        was building -- a font URL, an asset path.
        """
        for print_format in load_print_formats():
            css = print_format["css"]
            with self.subTest(name=print_format["name"]):
                self.assertNotIn("{{", css)
                self.assertNotIn("{%", css)

    def test_templates_do_not_use_background_images(self) -> None:
        for print_format in load_print_formats():
            content = f"{print_format['html']}\n{print_format['css']}"
            if print_format["name"] not in FORM_OVERLAY_PRINT_FORMATS:
                self.assertNotIn("background-image:", content, print_format["name"])
            self.assertNotIn("--page-bg", content, print_format["name"])
            self.assertNotIn("/images/print_formats/", content, print_format["name"])

    # Content/wording assertions for specific templates were intentionally removed
    # here: those formats are edited live through Desk, and pinning exact strings
    # made every legitimate content edit fail CI. See connect_diagnostics_core/AGENTS.md's Testing section
    # for the rule this follows.
