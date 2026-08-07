# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import print_configuration
from connect_diagnostics_core.setup import print_documents

TEMPLATE = "Print Configuration Template"
CUSTOMER = "Customer"


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


class ResolverHarness(UnitTestCase):
    """Drive the resolver with controllable Template and Customer data."""

    def setUp(self) -> None:
        super().setUp()
        self.template_name = "Default"
        self.customer_scalars: dict[str, Any] = {}
        self.rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.copies: dict[tuple[str, str], list[dict[str, Any]]] = {}

        get_all = patch.object(print_configuration.frappe, "get_all", side_effect=self._get_all)
        db_get_value = patch.object(
            print_configuration.frappe.db, "get_value", side_effect=self._db_get_value
        )
        get_meta = patch.object(print_configuration.frappe, "get_meta", return_value=_AllFieldsMeta())
        register = patch("connect_diagnostics_core.api.frappe.print_log.register_print", return_value="")
        for patcher in (get_all, db_get_value, get_meta, register):
            patcher.start()
            self.addCleanup(patcher.stop)

    def set_template_row(self, document_key: str, **values: Any) -> None:
        self.rows[(TEMPLATE, document_key)] = [values]

    def set_template_copy(self, document_key: str, copy_key: str, **values: Any) -> None:
        self.copies.setdefault((TEMPLATE, document_key), []).append(
            {"copy_key": copy_key, "label": None, "count": 1, **values}
        )

    def set_customer_row(self, document_key: str, **values: Any) -> None:
        self.rows[(CUSTOMER, document_key)] = [values]

    def set_customer_copy(self, document_key: str, copy_key: str, **values: Any) -> None:
        self.copies.setdefault((CUSTOMER, document_key), []).append(
            {"copy_key": copy_key, "label": None, "count": 1, **values}
        )

    def _get_all(self, doctype: str, **kwargs: Any) -> list[dict[str, Any]]:
        filters = kwargs.get("filters") or {}
        key = (filters.get("parenttype", ""), filters.get("document_key", ""))
        if doctype == "Print Document Configuration":
            return [dict(row) for row in self.rows.get(key, [])]
        if doctype == "Print Copy Configuration":
            return [dict(row) for row in self.copies.get(key, [])]
        return []

    def _db_get_value(self, doctype: str, name: str, fieldname: Any, **kwargs: Any) -> Any:
        if fieldname == "print_configuration_template":
            return self.template_name
        return dict(self.customer_scalars) if kwargs.get("as_dict") else None


class _AllFieldsMeta:
    def has_field(self, fieldname: str) -> bool:
        return True


class TestRegistryDefaults(ResolverHarness):
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


class TestResolutionPrecedence(ResolverHarness):
    def test_template_row_overrides_the_registry_default(self) -> None:
        self.set_template_row("tax_invoice", show_date=0)

        resolved = print_configuration.resolve_configuration(sales_invoice(), "tax_invoice")

        self.assertEqual(resolved.values["show_date"], 0)
        self.assertEqual(resolved.sources["show_date"], print_documents.SOURCE_TEMPLATE)

    def test_customer_row_overrides_the_template_row(self) -> None:
        self.set_template_row("tax_invoice", show_date=0, show_batch_serial=1)
        self.set_customer_row("tax_invoice", show_date=1, show_batch_serial=0)

        resolved = print_configuration.resolve_configuration(sales_invoice(), "tax_invoice")

        self.assertEqual(resolved.values["show_date"], 1)
        self.assertEqual(resolved.values["show_batch_serial"], 0)
        self.assertEqual(resolved.sources["show_date"], print_documents.SOURCE_CUSTOMER)

    def test_customer_without_a_row_follows_the_template_live(self) -> None:
        self.set_template_row("receipt", show_date=0, language=print_documents.LANGUAGE_ENGLISH)

        resolved = print_configuration.resolve_configuration(
            FakeDocument(
                {
                    "doctype": "Payment Entry",
                    "name": "ACC-PAY-0001",
                    "party_type": "Customer",
                    "party": "CUST-0001",
                }
            ),
            "receipt",
        )

        self.assertEqual(resolved.values["show_date"], 0)
        self.assertEqual(resolved.values["language"], print_documents.LANGUAGE_ENGLISH)
        self.assertEqual(resolved.sources["language"], print_documents.SOURCE_TEMPLATE)

    def test_sidebar_override_beats_every_stored_value(self) -> None:
        self.set_template_row("tax_invoice", show_date=1)
        self.set_customer_row("tax_invoice", show_date=1)
        doc = sales_invoice()
        doc.flags.print_settings = {"cd_show_date": 0, "cd_copy_accounting": 3}

        resolved = print_configuration.resolve_configuration(doc, "tax_invoice")

        self.assertEqual(resolved.values["show_date"], 0)
        self.assertEqual(resolved.values["copy_accounting"], 3)
        self.assertEqual(resolved.sources["show_date"], print_documents.SOURCE_REQUEST)

    def test_blank_customer_scalar_does_not_shadow_the_default(self) -> None:
        self.customer_scalars = {"customer_print_name": "", "quotation_delivery_terms": "FOB Bangkok"}

        resolved = print_configuration.resolve_configuration(
            FakeDocument(
                {
                    "doctype": "Quotation",
                    "name": "SAL-QTN-0001",
                    "quotation_to": "Customer",
                    "party_name": "CUST-0001",
                }
            ),
            "quotation",
        )

        self.assertEqual(resolved.values["customer_print_name"], "")
        self.assertEqual(resolved.sources["customer_print_name"], print_documents.SOURCE_DEFAULT)
        self.assertEqual(resolved.values["quotation_delivery_terms"], "FOB Bangkok")
        self.assertEqual(resolved.sources["quotation_delivery_terms"], print_documents.SOURCE_CUSTOMER)

    def test_signatory_set_on_the_quotation_wins(self) -> None:
        self.customer_scalars = {"quotation_signatory_type": "Sales Representative"}

        resolved = print_configuration.resolve_configuration(
            FakeDocument(
                {
                    "doctype": "Quotation",
                    "name": "SAL-QTN-0001",
                    "quotation_to": "Customer",
                    "party_name": "CUST-0001",
                    "quotation_signatory_type": "Managing Director",
                }
            ),
            "quotation",
        )

        self.assertEqual(resolved.values["quotation_signatory_type"], "Managing Director")
        self.assertEqual(resolved.sources["quotation_signatory_type"], print_documents.SOURCE_DOCUMENT)


class TestPrintContext(ResolverHarness):
    def test_copies_expand_named_rows_into_page_sets(self) -> None:
        self.set_template_row("tax_invoice")
        for copy_key in ("original", "customer", "accounting", "sales"):
            self.set_template_copy("tax_invoice", copy_key, count=1)

        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(
            [copy["kind"] for copy in context["copies"]],
            ["original", "customer", "accounting", "sales"],
        )
        self.assertEqual(context["original_count"], 1)
        self.assertEqual(context["copy_count"], 3)

    def test_a_copy_count_of_zero_removes_that_page_set(self) -> None:
        self.set_template_row("tax_invoice")
        self.set_template_copy("tax_invoice", "original", count=1)
        self.set_template_copy("tax_invoice", "accounting", count=0)

        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertNotIn("accounting", [copy["kind"] for copy in context["copies"]])

    def test_a_repeated_copy_is_numbered(self) -> None:
        self.set_template_row("receipt")
        self.set_template_copy("receipt", "copy", count=2)

        context = print_configuration.get_document_print_context(
            FakeDocument(
                {
                    "doctype": "Payment Entry",
                    "name": "ACC-PAY-0001",
                    "party_type": "Customer",
                    "party": "CUST-0001",
                }
            ),
            "receipt",
        )

        labels = [copy["label"] for copy in context["copies"]]
        self.assertIn("สำเนา 1/2", labels)
        self.assertIn("สำเนา 2/2", labels)

    def test_tax_invoice_stays_thai_whatever_the_row_says(self) -> None:
        self.set_template_row("tax_invoice", language=print_documents.LANGUAGE_ENGLISH)

        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(context["language"], print_documents.LANGUAGE_THAI)
        self.assertTrue(context["show_thai"])
        self.assertFalse(context["show_english"])

    def test_disabled_document_throws(self) -> None:
        self.set_template_row("tax_invoice", enabled=0)

        with self.assertRaises(frappe.ValidationError):
            print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

    def test_customer_print_name_falls_back_to_the_document(self) -> None:
        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(context["customer_name"], "Bangkok Hospital")

    def test_context_always_yields_at_least_one_page_set(self) -> None:
        self.set_template_row("receipt")
        self.set_template_copy("receipt", "original", count=0)
        self.set_template_copy("receipt", "copy", count=0)

        context = print_configuration.get_document_print_context(
            FakeDocument(
                {
                    "doctype": "Payment Entry",
                    "name": "ACC-PAY-0001",
                    "party_type": "Customer",
                    "party": "CUST-0001",
                }
            ),
            "receipt",
        )

        self.assertEqual(len(context["copies"]), 1)

    def test_print_context_records_the_print(self) -> None:
        with patch(
            "connect_diagnostics_core.api.frappe.print_log.register_print", return_value=""
        ) as mocked_register:
            print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        mocked_register.assert_called_once()


class TestSidebarConfiguration(ResolverHarness):
    def _sidebar(self, doc: FakeDocument, print_format: str) -> dict[str, Any]:
        with (
            patch.object(print_configuration.frappe, "has_permission"),
            patch.object(print_configuration.frappe, "get_doc", return_value=doc),
        ):
            return print_configuration.get_sidebar_configuration(doc["doctype"], doc["name"], print_format)

    def test_sidebar_offers_one_control_per_named_copy(self) -> None:
        result = self._sidebar(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertIn("copy_original", fieldnames)
        self.assertIn("copy_accounting", fieldnames)
        self.assertIn("show_batch_serial", fieldnames)

    def test_sidebar_hides_language_for_a_thai_only_document(self) -> None:
        result = self._sidebar(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertNotIn("language", fieldnames)

    def test_sidebar_offers_language_where_it_is_selectable(self) -> None:
        doc = FakeDocument(
            {
                "doctype": "Payment Entry",
                "name": "ACC-PAY-0001",
                "party_type": "Customer",
                "party": "CUST-0001",
            }
        )

        result = self._sidebar(doc, "Receipt")

        fieldnames = [field["fieldname"] for field in result["data"]["fields"]]
        self.assertIn("language", fieldnames)
        self.assertNotIn("show_batch_serial", fieldnames)

    def test_sidebar_reports_where_each_value_came_from(self) -> None:
        self.set_template_row("tax_invoice", show_date=0)

        result = self._sidebar(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        self.assertEqual(result["data"]["sources"]["show_date"], print_documents.SOURCE_TEMPLATE)

    def test_sidebar_is_empty_for_an_unregistered_format(self) -> None:
        doc = FakeDocument({"doctype": "Sales Order", "name": "SAL-ORD-0001", "customer": "CUST-0001"})

        result = self._sidebar(doc, "Sales Order")

        self.assertEqual(result["data"]["fields"], [])

    def test_sidebar_is_empty_without_a_customer(self) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice", "name": "ACC-SINV-0001", "customer": ""})

        result = self._sidebar(doc, "Tax Invoice Delivery Note and Invoice")

        self.assertEqual(result["data"]["fields"], [])

    def test_sidebar_reports_a_disabled_document_instead_of_controls(self) -> None:
        self.set_template_row("tax_invoice", enabled=0)

        result = self._sidebar(sales_invoice(), "Tax Invoice Delivery Note and Invoice")

        self.assertEqual(result["data"]["fields"], [])
        self.assertIn("disabled", result["message"])

    def test_sidebar_checks_read_permission(self) -> None:
        doc = sales_invoice()
        with (
            patch.object(print_configuration.frappe, "has_permission") as mocked_permission,
            patch.object(print_configuration.frappe, "get_doc", return_value=doc),
        ):
            print_configuration.get_sidebar_configuration(
                "Sales Invoice", "ACC-SINV-0001", "Tax Invoice Delivery Note and Invoice"
            )

        mocked_permission.assert_called_once_with("Sales Invoice", "read", "ACC-SINV-0001", throw=True)


class TestRetiredSurface(UnitTestCase):
    def test_snapshot_fetch_helpers_are_gone(self) -> None:
        """Template values are inherited live; there is nothing left to copy."""
        self.assertFalse(hasattr(print_configuration, "fetch_template_defaults"))
        self.assertFalse(hasattr(print_configuration, "get_template_defaults"))

    def test_tax_invoice_special_case_helpers_are_gone(self) -> None:
        for attribute in (
            "_tax_invoice_copy_contexts",
            "TAX_INVOICE_COPY_DEFINITIONS",
            "TAX_INVOICE_SELECTION_FIELDS",
            "DOCUMENT_CONFIGURATION",
            "PRINT_FORMAT_CONFIGURATION",
            "CONFIGURATION_FIELDNAMES",
        ):
            with self.subTest(attribute=attribute):
                self.assertFalse(hasattr(print_configuration, attribute))
