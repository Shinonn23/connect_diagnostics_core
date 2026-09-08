# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from importlib import import_module

from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_print.print_format.sales_order import (
    settings as sales_order_settings,
)
from connect_diagnostics_core.connect_diagnostics_print.print_format.shipment_box_label import (
    settings as shipment_settings,
)
from connect_diagnostics_core.setup import print_documents

quotation_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสนอราคา.settings"
)
receipt_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน.settings"
)
tax_invoice_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบกำกับภาษี_ใบแจ้งหนี้_ใบส่งของ.settings"
)
abbreviated_tax_invoice_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน_ใบกำกับภาษีอย่างย่อ.settings"
)
full_receipt_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเสร็จรับเงิน_ใบกำกับภาษี_ใบส่งของ.settings"
)
deposit_invoice_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบแจ้งหนี้เงินมัดจำ.settings"
)
thai_credit_note_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบลดหนี้.settings"
)
thai_debit_note_settings = import_module(
    "connect_diagnostics_core.connect_diagnostics_print.print_format.ใบเพิ่มหนี้.settings"
)


class TestPrintDocumentRegistry(UnitTestCase):
    def test_registry_loads_print_format_local_declarations(self) -> None:
        self.assertEqual(
            print_documents.PRINT_DOCUMENTS,
            (
                quotation_settings.PRINT_DOCUMENT,
                sales_order_settings.PRINT_DOCUMENT,
                tax_invoice_settings.PRINT_DOCUMENT,
                abbreviated_tax_invoice_settings.PRINT_DOCUMENT,
                full_receipt_settings.PRINT_DOCUMENT,
                deposit_invoice_settings.PRINT_DOCUMENT,
                thai_credit_note_settings.PRINT_DOCUMENT,
                thai_debit_note_settings.PRINT_DOCUMENT,
                receipt_settings.PRINT_DOCUMENT,
                shipment_settings.PRINT_DOCUMENT,
            ),
        )

    def test_document_keys_are_unique(self) -> None:
        keys = [document.key for document in print_documents.PRINT_DOCUMENTS]

        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(print_documents.DOCUMENT_BY_KEY))

    def test_no_print_format_maps_to_two_documents(self) -> None:
        seen: dict[str, str] = {}

        for document in print_documents.PRINT_DOCUMENTS:
            for print_format in document.print_formats:
                with self.subTest(print_format=print_format):
                    self.assertNotIn(print_format, seen)
                seen[print_format] = document.key

    def test_no_doctype_maps_to_two_documents(self) -> None:
        seen: dict[str, str] = {}

        for document in print_documents.PRINT_DOCUMENTS:
            for doctype in document.doctypes:
                with self.subTest(doctype=doctype):
                    self.assertNotIn(doctype, seen)
                seen[doctype] = document.key

    def test_copy_keys_are_unique_within_a_document(self) -> None:
        for document in print_documents.PRINT_DOCUMENTS:
            keys = [definition.key for definition in document.copies]
            with self.subTest(document=document.key):
                self.assertEqual(len(keys), len(set(keys)))
                self.assertTrue(keys)

    def test_every_document_starts_with_an_original_copy(self) -> None:
        for document in print_documents.PRINT_DOCUMENTS:
            with self.subTest(document=document.key):
                if document.copies[0].always_include:
                    self.assertGreaterEqual(document.copies[0].default_count, 1)
                else:
                    self.assertEqual(document.copies[0].kind, print_documents.KIND_ORIGINAL)
                    self.assertGreaterEqual(document.copies[0].default_count, 1)

    def test_resolve_document_key_prefers_the_print_format(self) -> None:
        # Sales Invoice formats are separated by their exact Print Format name.
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบเสร็จรับเงิน ใบกำกับภาษีอย่างย่อ"),
            "abbreviated_tax_invoice",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ"),
            "tax_invoice",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบเสร็จรับเงิน ใบกำกับภาษี ใบส่งของ"),
            "full_receipt",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบแจ้งหนี้เงินมัดจำ"),
            "deposit_invoice",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบลดหนี้"),
            "thai_credit_note",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "ใบเพิ่มหนี้"),
            "thai_debit_note",
        )

    def test_resolve_document_key_falls_back_to_the_doctype(self) -> None:
        self.assertEqual(print_documents.resolve_document_key("Sales Invoice"), "tax_invoice")
        self.assertEqual(print_documents.resolve_document_key("Sales Invoice", "Credit Note"), "tax_invoice")
        self.assertEqual(print_documents.resolve_document_key("Payment Entry"), "receipt")
        self.assertEqual(print_documents.resolve_document_key("Quotation"), "quotation")

    def test_resolve_document_key_uses_renamed_thai_formats(self) -> None:
        self.assertEqual(
            print_documents.resolve_document_key("Quotation", "ใบเสนอราคา"),
            "quotation",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Payment Entry", "ใบเสร็จรับเงิน"),
            "receipt",
        )

    def test_resolve_document_key_returns_empty_for_unregistered_input(self) -> None:
        self.assertEqual(print_documents.resolve_document_key("Delivery Note"), "")
        self.assertEqual(print_documents.resolve_document_key("Purchase Order", "Purchase Order"), "")

    def test_retired_document_types_are_not_registered(self) -> None:
        self.assertNotIn("invoice", print_documents.DOCUMENT_BY_KEY)
        self.assertNotIn("delivery_note", print_documents.DOCUMENT_BY_KEY)

    def test_tax_invoice_is_thai_only_and_offers_batch_serial(self) -> None:
        tax_invoice = print_documents.DOCUMENT_BY_KEY["tax_invoice"]

        self.assertFalse(tax_invoice.language_selectable)
        self.assertEqual(tax_invoice.fixed_language, print_documents.LANGUAGE_THAI)
        self.assertTrue(tax_invoice.offers_batch_serial)
        self.assertEqual(
            [definition.key for definition in tax_invoice.copies],
            [
                "company",
                "customer_original",
                "customer_copy",
                "accounting_original",
                "accounting_copy",
                "sales_original",
                "sales_copy",
                "custom",
            ],
        )

    def test_copy_label_follows_the_requested_language(self) -> None:
        definition = print_documents.GENERIC_COPIES[0]

        self.assertEqual(definition.label(print_documents.LANGUAGE_THAI), "ต้นฉบับ")
        self.assertEqual(definition.label(print_documents.LANGUAGE_ENGLISH), "Original")
        self.assertEqual(definition.label(print_documents.LANGUAGE_BILINGUAL), "ต้นฉบับ / Original")

    def test_quotation_document_only_scalar_defaults_are_present(self) -> None:
        """Validity and delivery terms are document fields, not sidebar overrides."""
        quotation = print_documents.DOCUMENT_BY_KEY["quotation"]
        for fieldname in ("edit_validity_text", "validity_text", "quotation_delivery_terms"):
            with self.subTest(fieldname=fieldname):
                self.assertIn(fieldname, quotation.defaults)
                self.assertIn(fieldname, quotation.document_fields)
                self.assertNotIn(fieldname, quotation.extra_fields)

    def test_quotation_carries_the_signatory_on_the_document(self) -> None:
        quotation = print_documents.DOCUMENT_BY_KEY["quotation"]
        self.assertEqual(
            set(quotation.document_fields),
            {
                "quotation_signatory_type",
                "sales_representative_employee",
                "edit_validity_text",
                "validity_text",
                "quotation_delivery_terms",
            },
        )

    def test_quotation_manager_signatory_is_request_only(self) -> None:
        quotation = print_documents.DOCUMENT_BY_KEY["quotation"]
        self.assertIn("manager_signatory_employee", quotation.extra_fields)
        self.assertEqual(quotation.defaults["manager_signatory_employee"], "")

    def test_shipment_label_only_resolves_for_its_selected_format(self) -> None:
        self.assertEqual(
            print_documents.resolve_document_key("Shipment", "Shipment Box Label"),
            "shipment_box_label",
        )
        self.assertEqual(print_documents.resolve_document_key("Shipment", "Another Shipment Format"), "")
