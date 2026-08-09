# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_documents


class TestPrintConfigurationTemplate(UnitTestCase):
    def test_template_carries_the_two_registry_tables(self) -> None:
        fields = self._fields()

        self.assertEqual(fields["print_documents"]["fieldtype"], "Table")
        self.assertEqual(fields["print_documents"]["options"], "Print Document Configuration")
        self.assertEqual(fields["print_copies"]["fieldtype"], "Table")
        self.assertEqual(fields["print_copies"]["options"], "Print Copy Configuration")

    def test_template_is_named_after_its_title(self) -> None:
        definition = self._definition()

        self.assertEqual(definition["autoname"], "field:template_name")
        self.assertEqual(definition["title_field"], "template_name")
        self.assertEqual(definition["module"], "Connect Diagnostics Print")

    def test_flat_per_document_fields_are_gone(self) -> None:
        fields = self._fields()

        for prefix in (
            "quotation",
            "tax_invoice",
            "delivery_note",
            "invoice",
            "abbreviated_tax_invoice",
            "receipt",
        ):
            for suffix in ("_section", "_language", "_original_count", "_copy_count"):
                with self.subTest(fieldname=f"{prefix}{suffix}"):
                    self.assertNotIn(f"{prefix}{suffix}", fields)
            with self.subTest(fieldname=f"use_{prefix}"):
                self.assertNotIn(f"use_{prefix}", fields)

        for fieldname in (
            "show_tax_invoice_batch_serial",
            "print_tax_invoice_original",
            "print_tax_invoice_customer_copy",
            "print_tax_invoice_accounting_copy",
            "print_tax_invoice_sales_copy",
        ):
            with self.subTest(fieldname=fieldname):
                self.assertNotIn(fieldname, fields)

    def test_per_customer_scalars_live_on_customer_not_here(self) -> None:
        """A Template is shared policy; these are one customer's own defaults."""
        fields = self._fields()

        for fieldname in print_documents.SCALAR_FIELDS:
            with self.subTest(fieldname=fieldname):
                self.assertNotIn(fieldname, fields)

    def test_child_doctypes_expose_the_registry_shape(self) -> None:
        document_fields = self._child_fields("print_document_configuration")
        copy_fields = self._child_fields("print_copy_configuration")

        self.assertEqual(document_fields["document_key"]["read_only"], 1)
        self.assertEqual(document_fields["enabled"]["default"], "1")
        self.assertEqual(
            document_fields["language"]["options"],
            "\n".join(print_documents.LANGUAGE_OPTIONS),
        )
        self.assertEqual(copy_fields["copy_key"]["read_only"], 1)
        self.assertEqual(copy_fields["kind"]["options"], "Original\nCopy")
        self.assertEqual(copy_fields["count"]["non_negative"], 1)

    @staticmethod
    def _definition() -> dict[str, Any]:
        path = Path(__file__).with_name("print_configuration_template.json")
        return json.loads(path.read_text())

    def _fields(self) -> dict[str, dict[str, Any]]:
        return {field["fieldname"]: field for field in self._definition()["fields"]}

    @staticmethod
    def _child_fields(slug: str) -> dict[str, dict[str, Any]]:
        path = Path(__file__).parents[1] / slug / f"{slug}.json"
        definition = json.loads(path.read_text())
        return {field["fieldname"]: field for field in definition["fields"]}
