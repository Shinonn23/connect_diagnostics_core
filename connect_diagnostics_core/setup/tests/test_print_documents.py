# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_documents


class TestPrintDocumentRegistry(UnitTestCase):
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
                self.assertEqual(document.copies[0].kind, print_documents.KIND_ORIGINAL)
                self.assertGreaterEqual(document.copies[0].default_count, 1)

    def test_resolve_document_key_prefers_the_print_format(self) -> None:
        # Sales Invoice carries two formats; only the format name separates them.
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "Abbreviated Tax Invoice And Receipt"),
            "abbreviated_tax_invoice",
        )
        self.assertEqual(
            print_documents.resolve_document_key("Sales Invoice", "Tax Invoice Delivery Note and Invoice"),
            "tax_invoice",
        )

    def test_resolve_document_key_falls_back_to_the_doctype(self) -> None:
        self.assertEqual(print_documents.resolve_document_key("Sales Invoice"), "tax_invoice")
        self.assertEqual(print_documents.resolve_document_key("Payment Entry"), "receipt")
        self.assertEqual(print_documents.resolve_document_key("Quotation"), "quotation")

    def test_resolve_document_key_returns_empty_for_unregistered_input(self) -> None:
        self.assertEqual(print_documents.resolve_document_key("Sales Order"), "")
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
            ["original", "customer", "accounting", "sales"],
        )

    def test_copy_label_follows_the_requested_language(self) -> None:
        definition = print_documents.GENERIC_COPIES[0]

        self.assertEqual(definition.label(print_documents.LANGUAGE_THAI), "ต้นฉบับ")
        self.assertEqual(definition.label(print_documents.LANGUAGE_ENGLISH), "Original")
        self.assertEqual(definition.label(print_documents.LANGUAGE_BILINGUAL), "ต้นฉบับ / Original")

    def test_scalar_defaults_cover_every_scalar_field(self) -> None:
        self.assertLessEqual(set(print_documents.SCALAR_FIELDS), set(print_documents.SCALAR_DEFAULTS))

    def test_customer_stores_only_its_own_quotation_defaults(self) -> None:
        """Validity wording describes one offer, so Customer must not carry it."""
        self.assertEqual(
            set(print_documents.QUOTATION_CUSTOMER_FIELDS),
            {"quotation_signatory_type", "quotation_delivery_terms"},
        )
        for fieldname in ("override_quotation_validity_text", "quotation_custom_validity_text"):
            with self.subTest(fieldname=fieldname):
                self.assertNotIn(fieldname, print_documents.SCALAR_FIELDS)
                self.assertIn(fieldname, print_documents.SCALAR_DEFAULTS)
                self.assertIn(fieldname, print_documents.QUOTATION_EXTRA_FIELDS)

    def test_quotation_carries_the_signatory_on_the_document(self) -> None:
        self.assertEqual(
            set(print_documents.QUOTATION_DOCUMENT_FIELDS),
            {
                "quotation_signatory_type",
                "sales_representative_employee",
                "override_quotation_validity_text",
                "quotation_custom_validity_text",
            },
        )
