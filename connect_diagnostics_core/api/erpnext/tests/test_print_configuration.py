# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import print_configuration
from connect_diagnostics_core.setup import print_documents


class FakeDocument(frappe._dict):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        super().__init__(values or {})
        self.flags = frappe._dict()


def sales_invoice(**overrides: Any) -> FakeDocument:
    return FakeDocument(
        {
            "doctype": "Sales Invoice",
            "name": "ACC-SINV-0001",
            "customer": "CUST-0001",
            "customer_name": "Bangkok Hospital",
            **overrides,
        }
    )


def payment_entry(**overrides: Any) -> FakeDocument:
    return FakeDocument(
        {
            "doctype": "Payment Entry",
            "name": "ACC-PAY-0001",
            "party_type": "Customer",
            "party": "CUST-0001",
            **overrides,
        }
    )


class ContextHarness(UnitTestCase):
    """Exercise the print context with the audit-log write stubbed out."""

    def setUp(self) -> None:
        super().setUp()
        register = patch("connect_diagnostics_core.api.frappe.print_log.register_print", return_value="")
        register.start()
        self.addCleanup(register.stop)


class TestRegistryDefaults(UnitTestCase):
    def test_defaults_come_from_the_registry(self) -> None:
        document = print_documents.DOCUMENT_BY_KEY["quotation"]

        defaults = print_configuration.get_default_configuration(document)

        self.assertEqual(defaults["enabled"], 1)
        self.assertEqual(defaults["show_date"], 1)
        self.assertEqual(defaults["language"], print_documents.LANGUAGE_THAI)
        self.assertEqual(defaults["copy_original"], 1)
        self.assertEqual(defaults["copy_copy"], 0)

    def test_tax_invoice_defaults_print_all_four_named_copies(self) -> None:
        document = print_documents.DOCUMENT_BY_KEY["tax_invoice"]

        defaults = print_configuration.get_default_configuration(document)

        self.assertEqual(defaults["copy_original"], 1)
        self.assertEqual(defaults["copy_customer"], 1)
        self.assertEqual(defaults["copy_accounting"], 1)
        self.assertEqual(defaults["copy_sales"], 1)
        self.assertEqual(defaults["show_batch_serial"], 1)

    def test_unknown_configuration_is_rejected(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            print_configuration.resolve_configuration(sales_invoice(), "invoice")


class TestPrintContext(ContextHarness):
    def test_copies_expand_named_rows_into_page_sets(self) -> None:
        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(
            [copy["kind"] for copy in context["copies"]],
            ["original", "customer", "accounting", "sales"],
        )
        self.assertEqual(context["original_count"], 1)
        self.assertEqual(context["copy_count"], 3)

    def test_a_sidebar_copy_count_of_zero_removes_that_page_set(self) -> None:
        doc = sales_invoice()
        doc.flags.print_settings = {"cd_copy_accounting": 0}

        context = print_configuration.get_document_print_context(doc, "tax_invoice")

        self.assertNotIn("accounting", [copy["kind"] for copy in context["copies"]])

    def test_a_repeated_copy_is_numbered(self) -> None:
        doc = payment_entry()
        doc.flags.print_settings = {"cd_copy_copy": 2}

        context = print_configuration.get_document_print_context(doc, "receipt")

        labels = [copy["label"] for copy in context["copies"]]
        self.assertIn("สำเนา 1/2", labels)
        self.assertIn("สำเนา 2/2", labels)

    def test_tax_invoice_stays_thai_whatever_the_sidebar_says(self) -> None:
        doc = sales_invoice()
        doc.flags.print_settings = {"cd_language": print_documents.LANGUAGE_ENGLISH}

        context = print_configuration.get_document_print_context(doc, "tax_invoice")

        self.assertEqual(context["language"], print_documents.LANGUAGE_THAI)
        self.assertTrue(context["show_thai"])
        self.assertFalse(context["show_english"])

    def test_customer_print_name_falls_back_to_the_document(self) -> None:
        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(context["customer_name"], "Bangkok Hospital")

    def test_a_sidebar_print_name_overrides_the_document(self) -> None:
        doc = sales_invoice()
        doc.flags.print_settings = {"cd_customer_print_name": "BKK Hospital (Print)"}

        context = print_configuration.get_document_print_context(doc, "tax_invoice")

        self.assertEqual(context["customer_name"], "BKK Hospital (Print)")

    def test_context_always_yields_at_least_one_page_set(self) -> None:
        doc = payment_entry()
        doc.flags.print_settings = {"cd_copy_original": 0, "cd_copy_copy": 0}

        context = print_configuration.get_document_print_context(doc, "receipt")

        self.assertEqual(len(context["copies"]), 1)

    def test_signatory_set_on_the_quotation_is_used(self) -> None:
        doc = FakeDocument(
            {
                "doctype": "Quotation",
                "name": "SAL-QTN-0001",
                "quotation_signatory_type": "Managing Director",
            }
        )

        context = print_configuration.get_document_print_context(doc, "quotation")

        self.assertEqual(context["quotation_signatory_type"], "Managing Director")

    def test_print_context_records_the_print(self) -> None:
        with patch(
            "connect_diagnostics_core.api.frappe.print_log.register_print", return_value=""
        ) as mocked_register:
            print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        mocked_register.assert_called_once()


class TestPrintOptions(UnitTestCase):
    """The sidebar controls come from the registry only, with no Customer data."""

    def _options(self, doc: FakeDocument, print_format: str) -> dict[str, Any]:
        with patch.object(print_configuration.frappe, "has_permission"):
            return print_configuration.get_print_options(doc["doctype"], doc["name"], print_format)

    def test_offers_one_control_per_named_copy(self) -> None:
        result = self._options(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertIn("copy_original", fieldnames)
        self.assertIn("copy_accounting", fieldnames)
        self.assertIn("show_batch_serial", fieldnames)

    def test_hides_language_for_a_thai_only_document(self) -> None:
        result = self._options(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertNotIn("language", fieldnames)

    def test_offers_language_where_it_is_selectable(self) -> None:
        result = self._options(payment_entry(), "Receipt")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertIn("language", fieldnames)
        self.assertNotIn("show_batch_serial", fieldnames)

    def test_includes_registry_default_values(self) -> None:
        result = self._options(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        self.assertEqual(result["data"]["values"]["copy_original"], 1)

    @patch.object(
        print_configuration.company_api,
        "get_quotation_authorized_signatories",
        return_value=[
            {
                "employee": "EMP-MANAGER",
                "name": "Managing Director",
                "ready": True,
            },
            {
                "employee": "EMP-NO-SIGNATURE",
                "name": "Second Manager",
                "ready": False,
            },
        ],
    )
    @patch.object(
        print_configuration.frappe.db,
        "get_value",
        return_value={"company": "COMP-0001", "quotation_signatory_type": "Managing Director"},
    )
    def test_quotation_sidebar_exposes_signatory_and_company_managers(
        self, _get_value: MagicMock, _get_managers: MagicMock
    ) -> None:
        quotation_doc = FakeDocument({"doctype": "Quotation", "name": "SAL-QTN-0001"})
        result = self._options(quotation_doc, "Quotation")

        fields = {field["fieldname"]: field for field in result["data"]["fields"]}
        self.assertIn("quotation_signatory_type", fields)
        self.assertIn("manager_signatory_employee", fields)
        self.assertTrue(fields["manager_signatory_employee"]["options"].startswith("\n"))
        self.assertEqual(
            fields["manager_signatory_employee"]["option_labels"]["EMP-MANAGER"],
            "Managing Director",
        )
        self.assertEqual(result["data"]["values"]["quotation_signatory_type"], "Managing Director")
        self.assertEqual(len(result["data"]["manager_signatories"]), 2)

    def test_empty_for_an_unregistered_format(self) -> None:
        doc = FakeDocument({"doctype": "Delivery Note", "name": "MAT-DN-0001"})

        result = self._options(doc, "Delivery Note")

        self.assertEqual(result["data"]["fields"], [])

    def test_checks_read_permission(self) -> None:
        with patch.object(print_configuration.frappe, "has_permission") as mocked_permission:
            print_configuration.get_print_options(
                "Sales Invoice", "ACC-SINV-0001", "Tax Invoice Delivery Note and Invoice"
            )

        mocked_permission.assert_called_once_with("Sales Invoice", "read", "ACC-SINV-0001", throw=True)


class TestRetiredSurface(UnitTestCase):
    def test_customer_template_resolution_is_gone(self) -> None:
        """Print options are chosen per print; nothing resolves from a Customer."""
        for attribute in (
            "get_sidebar_configuration",
            "get_document_enabled_map",
            "_customer_from_document",
            "_customer_template",
            "_customer_scalars",
            "_template_rows",
            "_customer_rows",
        ):
            with self.subTest(attribute=attribute):
                self.assertFalse(hasattr(print_configuration, attribute))
