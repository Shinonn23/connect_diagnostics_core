# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from frappe.tests import UnitTestCase
from jinja2 import Environment

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

# Print formats that resolve the Customer print configuration; the rest register
# themselves for the audit log with an explicit register_print call.
CONFIGURATION_PRINT_FORMATS = (
    "Abbreviated Tax Invoice And Receipt",
    "Credit Note",
    "Quotation",
    "Receipt",
    "Sales Order",
    "Tax Invoice Delivery Note and Invoice",
)

# Configuration formats whose language the sidebar can switch; the rest are fixed
# to one language and never emit the bilingual toggles.
LANGUAGE_SELECTABLE_CONFIGURATIONS = ("receipt", "abbreviated_tax_invoice")

# Formats that overlay an official government form image. The layout is absolute
# positioning over that scan, so semantic sectioning and the no-background-image
# rule -- both aimed at our own recreated layouts -- do not apply.
FORM_OVERLAY_PRINT_FORMATS = ("Withholding Tax Cert CD",)


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

    def test_every_print_format_reaches_the_audit_log(self) -> None:
        """Either the print context resolves it, or it calls register_print itself."""
        for print_format in load_print_formats():
            html = print_format["html"]
            resolves_configuration = print_format["name"] in CONFIGURATION_PRINT_FORMATS
            with self.subTest(name=print_format["name"]):
                if resolves_configuration:
                    self.assertRegex(html, r"get_\w*print_context\(")
                else:
                    self.assertIn("{{ register_print(doc) }}", html)

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

    def test_templates_use_semantic_document_elements(self) -> None:
        for print_format in load_print_formats():
            if print_format["name"] in FORM_OVERLAY_PRINT_FORMATS:
                continue
            html = print_format["html"].lower()
            self.assertIn("<header", html, print_format["name"])
            self.assertIn("<section", html, print_format["name"])
            self.assertIn("<footer", html, print_format["name"])

    def test_quotation_uses_customer_configuration_in_one_bilingual_format(self) -> None:
        path = PRINT_FORMAT_ROOT / "quotation/quotation.json"
        print_format = json.loads(path.read_text())
        html = print_format["html"]

        self.assertEqual(print_format["name"], "Quotation")
        self.assertIn("get_quotation_print_context(doc)", html)
        self.assertIn("print_context.customer_name", html)
        self.assertIn("for copy in print_context.copies", html)
        self.assertIn("print_context.show_thai", html)
        self.assertIn("print_context.show_english", html)
        self.assertIn("print_context.show_date", html)
        self.assertIn("print_context.validity_text", html)
        self.assertIn("print_context.delivery_terms", html)
        self.assertIn("print_context.sales_contact", html)
        self.assertIn("print_context.signatory.name", html)
        self.assertIn("print_context.signatory.caption", html)
        self.assertIn("print_context.validity_is_custom", html)
        self.assertIn("copy.label", html)
        self.assertIn('label("ใบเสนอราคา", "Quotation")', html)
        self.assertIn('label("กำหนดส่งมอบสินค้า", "Delivery Terms")', html)
        self.assertIn(".cdq-bilingual .cdq-company", print_format["css"])
        self.assertNotIn("ฟอร์มรูปแบบ", html)
        Environment().parse(html)

    def test_quotation_resolves_the_signatory_from_the_print_context_alone(self) -> None:
        """The Customer Sales Team chain and its template fallbacks are retired."""
        path = PRINT_FORMAT_ROOT / "quotation/quotation.json"
        html = json.loads(path.read_text())["html"]

        for retired in (
            "doc.sales_team",
            "custom_sales_contact_name",
            "custom_sales_contact_phone",
            "signatory.designation",
            '"90 วัน"',
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, html)

    def test_non_quotation_customer_formats_use_the_shared_print_context(self) -> None:
        expected_contexts = {
            "tax_invoice_delivery_note_and_invoice/tax_invoice_delivery_note_and_invoice.json": "tax_invoice",
            "abbreviated_tax_invoice_and_receipt/abbreviated_tax_invoice_and_receipt.json": "abbreviated_tax_invoice",
            "credit_note/credit_note.json": "tax_invoice",
            "receipt/receipt.json": "receipt",
            "sales_order/sales_order.json": "sales_order",
        }

        for relative_path, configuration in expected_contexts.items():
            with self.subTest(relative_path=relative_path):
                html = json.loads((PRINT_FORMAT_ROOT / relative_path).read_text())["html"]
                if configuration == "tax_invoice":
                    self.assertIn("get_sales_invoice_print_context(doc)", html)
                else:
                    self.assertIn(f'get_document_print_context(doc, "{configuration}")', html)
                self.assertIn("print_context.customer_name", html)
                self.assertIn("print_context.show_date", html)
                self.assertIn("for copy in print_context.copies", html)
                self.assertIn("copy.label", html)
                Environment().parse(html)

                if configuration in LANGUAGE_SELECTABLE_CONFIGURATIONS:
                    self.assertIn("print_context.show_thai", html)
                    self.assertIn("print_context.show_english", html)

        sales_invoice = json.loads(
            (
                PRINT_FORMAT_ROOT
                / "tax_invoice_delivery_note_and_invoice/tax_invoice_delivery_note_and_invoice.json"
            ).read_text()
        )
        self.assertIn("copy-{{ copy.kind }}", sales_invoice["html"])
        self.assertIn("traceability-line", sales_invoice["html"])
        self.assertNotIn("batch(7)", sales_invoice["html"])
        self.assertIn("current_print_page }}/{{ total_print_pages", sales_invoice["html"])
        self.assertIn("{% set total_print_pages = item_page_count %}", sales_invoice["html"])
        self.assertIn("{% set current_print_page = page_loop.index %}", sales_invoice["html"])
        self.assertIn("copy_loop.last and page_loop.last", sales_invoice["html"])
        self.assertNotIn("copy_loop.index - 1", sales_invoice["html"])
        self.assertIn('frappe.utils.format_time(doc.modified, "HH:mm:ss")', sales_invoice["html"])
        self.assertNotIn("frappe.utils.nowtime()", sales_invoice["html"])
        self.assertIn("{% if doc.docstatus == 1 %}", sales_invoice["html"])
        self.assertIn("copy-accounting", sales_invoice["css"])
        self.assertIn("overflow-wrap: anywhere", sales_invoice["css"])
        self.assertNotIn("text-overflow: ellipsis", sales_invoice["css"])
        self.assertNotIn("show_thai", sales_invoice["html"])
        self.assertNotIn("show_english", sales_invoice["html"])
        self.assertNotIn('class="en"', sales_invoice["html"])
        self.assertNotIn("cd-language-", sales_invoice["css"])

    def test_purchase_order_header_and_item_columns_match_current_layout(self) -> None:
        print_format = json.loads((PRINT_FORMAT_ROOT / "purchase_order/purchase_order.json").read_text())
        html = print_format["html"]
        css = print_format["css"]

        self.assertIn("shipping_address_display", html)
        self.assertIn("supplier_contact", html)
        self.assertIn("Contact:", html)
        self.assertNotIn("Reference", html)
        self.assertIn("eta_date", html)
        self.assertIn("ETA", html)
        self.assertIn("Incoterm", html)
        self.assertIn("Currency:", html)
        self.assertIn("col-item-code", html)
        self.assertIn("col-uom", html)
        self.assertNotIn("col-location", html)
        self.assertNotIn("col-discount", html)
        self.assertNotIn("line-location", html)
        self.assertNotIn("line-discount", html)
        self.assertNotIn("col-location", css)
        self.assertNotIn("col-discount", css)
        self.assertNotIn("line-location", css)
        self.assertNotIn("line-discount", css)
        Environment().parse(html)

    def test_shipment_box_label_metadata_and_layout(self) -> None:
        print_format = self._load_shipment_box_label()
        content = f"{print_format['html']}\n{print_format['css']}"

        self.assertEqual(print_format["name"], "Shipment Box Label")
        self.assertEqual(print_format["doc_type"], "Shipment")
        self.assertEqual(print_format["module"], "Connect Diagnostics Print")
        self.assertEqual(print_format["print_format_type"], "Jinja")
        self.assertEqual(print_format["pdf_generator"], "wkhtmltopdf")
        self.assertIn("size: 180mm 100mm", print_format["css"])
        self.assertIn("page-width: 180mm", print_format["css"])
        self.assertIn("page-height: 100mm", print_format["css"])
        self.assertIn("margin-top: 0mm", print_format["css"])
        self.assertIn("margin-right: 0mm", print_format["css"])
        self.assertIn("margin-bottom: 0mm", print_format["css"])
        self.assertIn("margin-left: 0mm", print_format["css"])
        self.assertIn("width: 179mm", print_format["css"])
        self.assertIn("height: 99mm", print_format["css"])
        self.assertIn("overflow-wrap: anywhere", print_format["css"])
        self.assertIn("word-break: break-word", print_format["css"])
        self.assertIn("/assets/connect_diagnostics_core/images/cd_logo_v2.jpg", content)
        self.assertIn('class="territory"', print_format["html"])
        self.assertIn("ผู้ส่ง", print_format["html"])
        self.assertIn("Sender", print_format["html"])
        self.assertIn("ผู้รับ", print_format["html"])
        self.assertIn("Recipient", print_format["html"])

    def test_shipment_box_label_renders_company_to_customer(self) -> None:
        rendered = self._render_shipment_box_label(
            values={
                ("Company", "Connect Diagnostics", "company_name"): "Connect Diagnostics Co., Ltd.",
                ("Customer", "CUST-001", "customer_name"): "Bangkok General Hospital",
                ("Customer", "CUST-001", "territory"): "Bangkok",
                ("Contact", "Receiver Contact", "mobile_no"): "081-234-5678",
            }
        )

        self.assertIn("Connect Diagnostics Co., Ltd.", rendered)
        self.assertIn("Bangkok General Hospital", rendered)
        self.assertIn('<div class="territory">Bangkok</div>', rendered)
        self.assertIn("โทร/Tel. 081-234-5678", rendered)

    def test_shipment_box_label_hides_empty_customer_territory(self) -> None:
        rendered = self._render_shipment_box_label(
            values={
                ("Company", "Connect Diagnostics", "company_name"): "Connect Diagnostics Co., Ltd.",
                ("Customer", "CUST-001", "customer_name"): "Customer without territory",
            }
        )

        self.assertNotIn('class="territory"', rendered)

    def test_shipment_box_label_uses_company_contact_snapshot_phone(self) -> None:
        rendered = self._render_shipment_box_label(
            pickup_contact="Sender Name<br>sender@example.com<br>02-347-0109",
            pickup_contact_name="Sender Contact",
            values={
                ("Contact", "Sender Contact", "mobile_no"): "089-999-9999",
            },
        )

        self.assertIn("โทร/Tel. 02-347-0109", rendered)
        self.assertNotIn("089-999-9999", rendered)

    def test_shipment_box_label_does_not_treat_email_snapshot_as_phone(self) -> None:
        rendered = self._render_shipment_box_label(
            pickup_contact="Sender Name<br>sender@example.com",
        )

        self.assertNotIn("โทร/Tel.", rendered)

    def test_shipment_box_label_preserves_address_line_separators(self) -> None:
        rendered = self._render_shipment_box_label(
            pickup_address="<p>1 Road<br>Bangkok 10220</p>",
            delivery_address="<div>99 Road</div><div>Bangkok 10110</div>",
        )

        self.assertIn("1 Road\nBangkok 10220", rendered)
        self.assertIn("99 Road\nBangkok 10110", rendered)
        self.assertNotIn("RoadBangkok", rendered)

    def test_shipment_box_label_hides_territory_for_non_customer_recipient(self) -> None:
        rendered = self._render_shipment_box_label(
            delivery_to_type="Supplier",
            delivery_supplier="SUP-001",
            values={
                ("Company", "Connect Diagnostics", "company_name"): "Connect Diagnostics Co., Ltd.",
                ("Supplier", "SUP-001", "supplier_name"): "Medical Supply Co., Ltd.",
                ("Customer", "SUP-001", "territory"): "Must not render",
            },
        )

        self.assertIn("Medical Supply Co., Ltd.", rendered)
        self.assertNotIn('class="territory"', rendered)
        self.assertNotIn("Must not render", rendered)

    def test_shipment_box_label_truncates_long_addresses(self) -> None:
        long_address = f"Address start {'long address segment ' * 20}UNBOUNDED_TAIL"
        rendered = self._render_shipment_box_label(
            pickup_address=long_address,
            delivery_address=long_address,
        )

        self.assertIn("Address start", rendered)
        self.assertIn("…", rendered)
        self.assertNotIn("UNBOUNDED_TAIL", rendered)

    @staticmethod
    def _load_shipment_box_label() -> dict[str, Any]:
        path = PRINT_FORMAT_ROOT / "shipment_box_label/shipment_box_label.json"
        return json.loads(path.read_text())

    def _render_shipment_box_label(
        self,
        *,
        delivery_to_type: str = "Customer",
        delivery_supplier: str = "",
        pickup_address: str = "1/57-58 Watcharaphon Road<br>Bangkok 10220",
        delivery_address: str = "99 Long recipient address<br>Bangkok 10110",
        pickup_contact: str = "",
        pickup_contact_name: str = "",
        values: dict[tuple[str, str, str], str] | None = None,
    ) -> str:
        class FakeDatabase:
            def __init__(self, stored_values: dict[tuple[str, str, str], str]) -> None:
                self.stored_values = stored_values

            def get_value(self, doctype: str, name: str, fieldname: str) -> str:
                return self.stored_values.get((doctype, name, fieldname), "")

        print_format = self._load_shipment_box_label()
        doc = {
            "name": "SHIP-0001",
            "pickup_from_type": "Company",
            "pickup_company": "Connect Diagnostics",
            "pickup_customer": "",
            "pickup_supplier": "",
            "pickup": "",
            "pickup_address_name": "Connect Diagnostics-Billing",
            "pickup_address": pickup_address,
            "pickup_contact_name": pickup_contact_name,
            "pickup_contact": pickup_contact,
            "delivery_to_type": delivery_to_type,
            "delivery_company": "",
            "delivery_customer": "CUST-001" if delivery_to_type == "Customer" else "",
            "delivery_supplier": delivery_supplier,
            "delivery_to": "",
            "delivery_address_name": "Recipient-Shipping",
            "delivery_address": delivery_address,
            "delivery_contact_name": "Receiver Contact",
            "delivery_contact": "",
        }
        environment = Environment(autoescape=True)

        return environment.from_string(print_format["html"]).render(
            doc=doc,
            frappe=SimpleNamespace(db=FakeDatabase(values or {})),
            # Registered as a Jinja method in hooks.py; a no-op here because the
            # harness renders outside a request.
            register_print=lambda *args, **kwargs: "",
        )
