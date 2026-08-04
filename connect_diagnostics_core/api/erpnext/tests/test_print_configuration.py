# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import print_configuration


class FakeDocument(frappe._dict):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        super().__init__(values or {})
        self.flags = frappe._dict()


class TestPrintConfiguration(UnitTestCase):
    def test_default_configuration_includes_all_document_sections(self) -> None:
        defaults = print_configuration.get_default_configuration()

        for prefix in print_configuration.DOCUMENT_CONFIGURATION:
            with self.subTest(prefix=prefix):
                self.assertEqual(defaults[f"use_{prefix}"], 1)
                self.assertEqual(defaults[f"show_{prefix}_date"], 1)
                self.assertEqual(defaults[f"{prefix}_language"], "Thai")
                self.assertEqual(defaults[f"{prefix}_original_count"], 1)
                self.assertEqual(defaults[f"{prefix}_copy_count"], 0)
        self.assertEqual(
            [defaults[fieldname] for fieldname in print_configuration.TAX_INVOICE_SELECTION_FIELDS],
            [1, 1, 1, 1, 1],
        )

    @patch.object(print_configuration.frappe, "get_doc")
    @patch.object(print_configuration.frappe, "has_permission")
    def test_template_defaults_return_only_supported_configuration_fields(
        self, mocked_has_permission: MagicMock, mocked_get_doc: MagicMock
    ) -> None:
        template = FakeDocument(
            {
                "customer_print_name": "Bangkok Hospital",
                "show_quotation_date": 0,
                "quotation_language": "English",
                "unrelated_field": "ignored",
            }
        )
        mocked_get_doc.return_value = template

        result = print_configuration.get_template_defaults("Hospital English")

        self.assertEqual(
            result,
            {
                "data": {
                    "customer_print_name": "Bangkok Hospital",
                    "show_quotation_date": 0,
                    "quotation_language": "English",
                },
                "message": "Print configuration defaults loaded from Template.",
            },
        )
        mocked_has_permission.assert_called_once_with(
            "Print Configuration Template", "read", "Hospital English", throw=True
        )

    @patch.object(print_configuration, "get_document_configuration")
    @patch.object(print_configuration.frappe, "get_doc")
    @patch.object(print_configuration.frappe, "has_permission")
    def test_sidebar_is_limited_to_the_current_print_format(
        self,
        mocked_has_permission: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_configuration: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice", "customer": "CUST-0001"})
        mocked_get_doc.return_value = doc
        mocked_configuration.return_value = print_configuration.get_default_configuration()

        result = print_configuration.get_sidebar_configuration(
            "Sales Invoice", "SINV-0001", "Tax Invoice Delivery Note and Invoice"
        )

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertIn("show_tax_invoice_date", fieldnames)
        self.assertIn("print_tax_invoice_original", fieldnames)
        self.assertIn("print_tax_invoice_customer_copy", fieldnames)
        self.assertIn("print_tax_invoice_accounting_copy", fieldnames)
        self.assertIn("print_tax_invoice_sales_copy", fieldnames)
        self.assertIn("show_tax_invoice_batch_serial", fieldnames)
        self.assertNotIn("tax_invoice_language", fieldnames)
        self.assertNotIn("tax_invoice_original_count", fieldnames)
        self.assertNotIn("show_delivery_note_date", fieldnames)
        self.assertNotIn("quotation_delivery_terms", fieldnames)
        mocked_has_permission.assert_called_once_with("Sales Invoice", "read", "SINV-0001", throw=True)
        mocked_configuration.assert_called_once_with(doc, "tax_invoice")

    @patch.object(print_configuration, "get_document_configuration")
    @patch.object(print_configuration.frappe, "get_doc")
    @patch.object(print_configuration.frappe, "has_permission")
    def test_sidebar_hides_options_when_document_is_disabled(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_configuration: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice", "customer": "CUST-0001"})
        mocked_get_doc.return_value = doc
        mocked_configuration.return_value = {
            **print_configuration.get_default_configuration(),
            "use_tax_invoice": 0,
        }

        result = print_configuration.get_sidebar_configuration(
            "Sales Invoice", "SINV-0001", "Tax Invoice Delivery Note and Invoice"
        )

        self.assertEqual(result["data"], {"fields": [], "values": {}})
        self.assertEqual(result["message"], "Tax Invoice is disabled for this Customer.")

    @patch.object(print_configuration.frappe, "get_meta")
    @patch.object(print_configuration.frappe.db, "get_value")
    def test_customer_defaults_and_transient_sidebar_override_are_merged(
        self, mocked_get_value: MagicMock, mocked_get_meta: MagicMock
    ) -> None:
        mocked_get_meta.return_value = SimpleNamespace(has_field=lambda _fieldname: True)
        mocked_get_value.return_value = {
            "customer_print_name": "Customer Default Name",
            "show_tax_invoice_date": 0,
            "tax_invoice_language": "English",
            "print_tax_invoice_original": 1,
            "print_tax_invoice_customer_copy": 1,
            "print_tax_invoice_accounting_copy": 0,
            "print_tax_invoice_sales_copy": 0,
            "show_tax_invoice_batch_serial": 1,
        }
        doc = FakeDocument(
            {
                "doctype": "Sales Invoice",
                "customer": "CUST-0001",
                "customer_name": "ERPNext Customer Name",
            }
        )
        doc.flags.print_settings = {
            "cd_customer_print_name": "One-time Print Name",
            "cd_show_tax_invoice_date": 1,
        }

        context = print_configuration.get_document_print_context(cast(Document, doc), "tax_invoice")

        self.assertEqual(context["customer_name"], "One-time Print Name")
        self.assertTrue(context["show_date"])
        self.assertEqual(context["language"], "Thai")
        self.assertTrue(context["show_thai"])
        self.assertFalse(context["show_english"])
        self.assertEqual(context["original_count"], 1)
        self.assertEqual(context["copy_count"], 1)
        self.assertEqual(
            context["copies"],
            [
                {"kind": "original", "label": "ต้นฉบับ (สำหรับลูกค้า)"},
                {"kind": "customer", "label": "สำเนา (สำหรับลูกค้า)"},
            ],
        )
        self.assertTrue(context["show_batch_serial"])

    @patch.object(print_configuration, "get_document_configuration")
    def test_tax_invoice_sidebar_selection_falls_back_to_original_when_all_are_off(
        self, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = {
            **print_configuration.get_default_configuration(),
            "print_tax_invoice_original": 0,
            "print_tax_invoice_customer_copy": 0,
            "print_tax_invoice_accounting_copy": 0,
            "print_tax_invoice_sales_copy": 0,
        }

        context = print_configuration.get_document_print_context(
            cast(Document, FakeDocument({"doctype": "Sales Invoice"})), "tax_invoice"
        )

        self.assertEqual(context["copies"], [{"kind": "original", "label": "ต้นฉบับ (สำหรับลูกค้า)"}])

    @patch.object(print_configuration, "get_document_configuration")
    def test_disabled_document_cannot_build_print_context(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = {
            **print_configuration.get_default_configuration(),
            "use_tax_invoice": 0,
        }

        with self.assertRaises(frappe.ValidationError):
            print_configuration.get_document_print_context(
                cast(Document, FakeDocument({"doctype": "Sales Invoice"})), "tax_invoice"
            )

    @patch.object(print_configuration.frappe, "get_meta")
    @patch.object(print_configuration.frappe.db, "get_value")
    def test_missing_customer_fields_fall_back_without_querying_unknown_columns(
        self, mocked_get_value: MagicMock, mocked_get_meta: MagicMock
    ) -> None:
        mocked_get_meta.return_value = SimpleNamespace(has_field=lambda _fieldname: False)
        doc = FakeDocument(
            {
                "doctype": "Sales Invoice",
                "customer": "CUST-0001",
                "customer_name": "ERPNext Customer Name",
            }
        )

        context = print_configuration.get_document_print_context(cast(Document, doc), "tax_invoice")

        self.assertEqual(context["customer_name"], "ERPNext Customer Name")
        self.assertTrue(context["show_date"])
        mocked_get_value.assert_not_called()

    @patch.object(print_configuration, "get_template_defaults")
    @patch.object(print_configuration.frappe, "get_doc")
    @patch.object(print_configuration.frappe, "has_permission")
    def test_fetch_template_defaults_checks_customer_write_permission(
        self,
        mocked_has_permission: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_template_defaults: MagicMock,
    ) -> None:
        mocked_get_doc.return_value = FakeDocument({"print_configuration_template": "Hospital English"})
        mocked_template_defaults.return_value = {"data": {}, "message": ""}

        print_configuration.fetch_template_defaults("CUST-0001")

        mocked_has_permission.assert_called_once_with("Customer", "write", "CUST-0001", throw=True)
        mocked_template_defaults.assert_called_once_with("Hospital English")
