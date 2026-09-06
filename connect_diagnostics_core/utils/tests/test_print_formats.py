# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_action_fields

PRINT_FORMAT_ROOT = Path(__file__).parents[2] / "connect_diagnostics_print" / "print_format"
PRINT_FORMAT_FILES = (
    "ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ.json",
    "ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ/ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ.json",
    "ใบแจ้งหนี้เงินมัดจำ/ใบแจ้งหนี้เงินมัดจำ.json",
    "ใบเพิ่มหนี้/ใบเพิ่มหนี้.json",
    "ใบลดหนี้/ใบลดหนี้.json",
    "goods_receipt/goods_receipt.json",
    "material_issue/material_issue.json",
    "material_request/material_request.json",
    "monthly_count_sheet/monthly_count_sheet.json",
    "purchase_order/purchase_order.json",
    "quotation/quotation.json",
    "receipt/receipt.json",
    "sales_order/sales_order.json",
    "shipment_box_label/shipment_box_label.json",
    "ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ/ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ.json",
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
TAX_INVOICE_FORMAT = "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ"
ABBREVIATED_TAX_INVOICE_FORMAT = "ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ"
CREDIT_NOTE_FORMAT = "ใบลดหนี้"
THAI_INVOICE_FORMATS = (
    ABBREVIATED_TAX_INVOICE_FORMAT,
    "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ",
    "ใบแจ้งหนี้เงินมัดจำ",
    "ใบเพิ่มหนี้",
    CREDIT_NOTE_FORMAT,
    TAX_INVOICE_FORMAT,
)
DELIVERY_NOTE_TITLE_FORMATS = (
    "ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ/ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ.json",
    "ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ/ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ.json",
)


def load_print_formats() -> list[dict[str, Any]]:
    return [
        json.loads((PRINT_FORMAT_ROOT / relative_path).read_text()) for relative_path in PRINT_FORMAT_FILES
    ]


class TestPrintFormats(UnitTestCase):
    def test_print_format_json_files_are_valid(self) -> None:
        print_formats = load_print_formats()

        self.assertEqual(len(print_formats), 17)
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

    def test_app_owned_print_formats_use_chrome_renderer(self) -> None:
        for print_format in load_print_formats():
            with self.subTest(name=print_format["name"]):
                self.assertEqual(print_format["pdf_generator"], "chrome")

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
            TAX_INVOICE_FORMAT: "2026-07-13 02:55:13.159262",
            ABBREVIATED_TAX_INVOICE_FORMAT: "2026-07-15 01:06:43.299275",
            "Receipt": "2026-07-03 15:30:00.000000",
        }

        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        for name, previous in previous_timestamps.items():
            with self.subTest(name=name):
                self.assertGreater(formats[name]["modified"], previous)

    def test_delivery_note_title_formats_use_the_request_context_and_updated_metadata(self) -> None:
        for relative_path in DELIVERY_NOTE_TITLE_FORMATS:
            print_format = json.loads((PRINT_FORMAT_ROOT / relative_path).read_text())
            with self.subTest(name=print_format["name"]):
                self.assertIn("print_context.show_delivery_note", print_format["html"])
                self.assertIn("/ใบส่งของ", print_format["html"])
                self.assertIn("overflow-wrap: anywhere", print_format["css"])
                self.assertGreater(print_format["modified"], "2026-09-06 16:52:40.948966")

    def test_invoice_signature_footers_keep_notes_in_the_single_summary_term(self) -> None:
        expected_names = {
            "ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ/ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ.json": "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ",
            "ใบแจ้งหนี้เงินมัดจำ/ใบแจ้งหนี้เงินมัดจำ.json": "ใบแจ้งหนี้เงินมัดจำ",
            "ใบเพิ่มหนี้/ใบเพิ่มหนี้.json": "ใบเพิ่มหนี้",
            "ใบลดหนี้/ใบลดหนี้.json": "ใบลดหนี้",
            "ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ.json": "ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ",
            "ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ/ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ.json": "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
        }
        for relative_path, expected_name in expected_names.items():
            print_format = json.loads((PRINT_FORMAT_ROOT / relative_path).read_text())
            html = print_format["html"]
            with self.subTest(name=print_format["name"]):
                self.assertEqual(print_format["name"], expected_name)
                self.assertNotIn("_", print_format["name"])
                self.assertNotIn("-", print_format["name"])
                self.assertEqual(html.count('<div class="summary-term">'), 1)
                self.assertIn("terms-heading", html)
                self.assertIn("signature-only-footer", html)
                self.assertIn("signature-company", html)
                self.assertIn("current_print_page", html)
                self.assertNotIn('<div class="approval-notes">', html)
                self.assertNotIn('<div class="approval-column">', html)

                if relative_path in DELIVERY_NOTE_TITLE_FORMATS:
                    self.assertIn("delivery-signatures", html)
                    self.assertIn("compact-signatures", html)
                    self.assertIn("{% if print_context.show_delivery_note %}", html)
                elif print_format["name"] == CREDIT_NOTE_FORMAT:
                    self.assertIn("three-signatures", html)

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

    def test_invoice_item_cells_override_global_print_padding(self) -> None:
        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        invoice_formats = (
            ABBREVIATED_TAX_INVOICE_FORMAT,
            TAX_INVOICE_FORMAT,
        )
        for name in invoice_formats:
            with self.subTest(name=name):
                css = formats[name]["css"]
                self.assertIn(".cd-invoice .item-lines td", css)
                self.assertIn("padding: 0 !important;", css)
                self.assertIn("padding-right: 1.05mm !important;", css)
                self.assertIn("--cd-fs-label", css)
                self.assertIn("grand-total", formats[name]["html"])

        transaction_formats = (
            "Goods Receipt",
            "Purchase Order",
            "Quotation",
            "Receipt",
            "Sales Order",
        )
        for name in transaction_formats:
            with self.subTest(name=name):
                print_format = formats[name]
                self.assertIn("font-size: 3.85mm !important;", print_format["css"])
                self.assertIn("font-size: 2.55mm !important;", print_format["css"])
                self.assertIn("font-size: 4.00mm !important;", print_format["css"])
                self.assertIn("font-size: 5.821mm !important;", print_format["css"])
                self.assertIn("Grand Total", print_format["html"])

        for name in ("ใบแจ้งหนี้เงินมัดจำ", "ใบเพิ่มหนี้", CREDIT_NOTE_FORMAT):
            with self.subTest(name=name):
                print_format = formats[name]
                self.assertIn("--cd-fs-label", print_format["css"])
                self.assertIn("grand-total", print_format["html"])

        content_pagination = {
            ABBREVIATED_TAX_INVOICE_FORMAT: "get_sales_invoice_print_context",
            CREDIT_NOTE_FORMAT: "get_sales_invoice_print_context",
            "Goods Receipt": 'get_print_item_pages(doc, "goods_receipt")',
            "Purchase Order": 'get_print_item_pages(doc, "purchase_order", 29.0)',
            "Quotation": 'get_print_item_pages(doc, "quotation")',
            "Receipt": "get_sales_invoice_print_context",
            "Sales Order": 'get_print_item_pages(doc, "sales_order")',
            TAX_INVOICE_FORMAT: "get_sales_invoice_print_context",
        }
        for name, pagination_call in content_pagination.items():
            with self.subTest(name=name):
                html = formats[name]["html"]
                self.assertIn(pagination_call, html)
                self.assertNotIn("| batch(10)", html)
                self.assertNotIn("| batch(9)", html)
                self.assertNotIn("line_count > 10", html)
                self.assertNotIn("item_count > 10", html)

    def test_templates_do_not_use_background_images(self) -> None:
        for print_format in load_print_formats():
            content = f"{print_format['html']}\n{print_format['css']}"
            if print_format["name"] not in FORM_OVERLAY_PRINT_FORMATS:
                self.assertNotIn("background-image:", content, print_format["name"])
            self.assertNotIn("--page-bg", content, print_format["name"])
            self.assertNotIn("/images/print_formats/", content, print_format["name"])

    def test_action_slots_bind_to_employee_backed_print_context(self) -> None:
        expected_actions = {
            ABBREVIATED_TAX_INVOICE_FORMAT: ("received", "delivered", "authorized", "checked"),
            TAX_INVOICE_FORMAT: ("received", "delivered", "authorized", "checked"),
            "Receipt": ("received", "delivered", "authorized", "checked"),
            CREDIT_NOTE_FORMAT: ("return_received", "warehouse_checked", "authorized"),
            "Goods Receipt": ("received", "checked", "authorized"),
            "Material Request": ("submit", "checked", "authorized"),
            "Material Issue": ("submit", "checked", "authorized"),
            "Purchase Order": ("ordered", "authorized"),
            "Sales Order": ("prepared", "checked", "authorized"),
            "Quotation": ("signatory",),
            "Withholding Tax Cert CD": ("signed",),
        }
        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        for name, action_keys in expected_actions.items():
            html = formats[name]["html"]
            with self.subTest(name=name):
                self.assertIn("action-signature-image", html)
                self.assertNotIn("____", html)
                for action_key in action_keys:
                    self.assertTrue(
                        f'print_actions["{action_key}"]' in html
                        or f'print_actions.get("{action_key}", {{}})' in html
                    )
                if formats[name]["doc_type"] == "Sales Invoice":
                    self.assertIn("{% set print_actions = get_print_action_context(doc) %}", html)
                    self.assertNotIn("print_context.print_actions", html)
                    self.assertNotIn('class="th total-en"', html)

        for name in expected_actions:
            doctype = formats[name]["doc_type"]
            registered = {action.key for action in print_action_fields.get_actions(doctype)}
            self.assertTrue(
                set(expected_actions[name]).issubset(registered),
                f"{name}: missing action mapping for {doctype}",
            )

    def test_action_slots_do_not_fallback_to_document_owner(self) -> None:
        expected_formats = (
            ABBREVIATED_TAX_INVOICE_FORMAT,
            TAX_INVOICE_FORMAT,
            "Receipt",
            CREDIT_NOTE_FORMAT,
            "Purchase Order",
            "Quotation",
            "Material Request",
            "Material Issue",
            "Withholding Tax Cert CD",
        )
        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        for name in expected_formats:
            with self.subTest(name=name):
                self.assertNotIn("frappe.get_fullname(doc.owner)", formats[name]["html"])

    def test_signature_slots_have_a_visible_snapshot_or_fallback_line(self) -> None:
        expected_slots = {
            ABBREVIATED_TAX_INVOICE_FORMAT: 2,
            "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ": 6,
            "ใบแจ้งหนี้เงินมัดจำ": 2,
            "ใบเพิ่มหนี้": 2,
            TAX_INVOICE_FORMAT: 6,
            "Receipt": 4,
            CREDIT_NOTE_FORMAT: 3,
            "Goods Receipt": 3,
            "Purchase Order": 2,
            "Sales Order": 3,
            "Quotation": 1,
            "Withholding Tax Cert CD": 1,
            "Material Request": 3,
            "Material Issue": 3,
        }
        formats = {print_format["name"]: print_format for print_format in load_print_formats()}
        date_caption_classes = (
            "date-caption",
            "approval-date-label",
            "signature-date-caption",
            "order-date-caption",
            "sign_date_caption",
        )

        for name, slot_count in expected_slots.items():
            print_format = formats[name]
            html = print_format["html"]
            css = print_format["css"]
            compact_css = "".join(css.split())
            with self.subTest(name=name):
                if name in THAI_INVOICE_FORMATS:
                    self.assertEqual(html.count("signature_row(") - 1, slot_count)
                    self.assertEqual(html.count("action-signature-image"), 1)
                else:
                    self.assertEqual(html.count("signature-placeholder"), slot_count)
                    self.assertEqual(html.count("action-signature-image"), slot_count)
                self.assertIn("signature-role", html)
                self.assertTrue(any(marker in html for marker in date_caption_classes))
                if name in THAI_INVOICE_FORMATS:
                    self.assertIn(".signature-only-footer", css)
                    self.assertIn("border-bottom", css)
                    self.assertIn("object-fit: contain", css)
                else:
                    self.assertIn("border:0!important", css.replace(" ", ""))
                    if name != "Withholding Tax Cert CD":
                        self.assertTrue("object-fit:contain" in css or "object-fit: contain" in css)
                    self.assertTrue("transform:scale(1)" in css or "transform: scale(1)" in css)
                    if name != "Withholding Tax Cert CD":
                        if name in ("Material Request", "Material Issue"):
                            self.assertIn("width: 36mm !important", css)
                            self.assertIn("height: 10.5mm !important", css)
                            self.assertIn("object-fit: contain !important", css)
                            self.assertIn("width: 36mm !important", css)
                            self.assertIn("height: 0 !important", css)
                        else:
                            self.assertIn("width:36mm!important", compact_css)
                            self.assertTrue(
                                "height:10.5mm!important" in compact_css
                                or "height:10.50mm!important" in compact_css
                            )
                            self.assertIn("object-fit:contain!important", compact_css)
                            self.assertIn("height:0!important", compact_css)

    # Content/wording assertions for specific templates were intentionally removed
    # here: those formats are edited live through Desk, and pinning exact strings
    # made every legitimate content edit fail CI. See connect_diagnostics_core/AGENTS.md's Testing section
    # for the rule this follows.
