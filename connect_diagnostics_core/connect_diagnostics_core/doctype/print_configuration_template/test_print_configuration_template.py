# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase


class TestPrintConfigurationTemplate(UnitTestCase):
    def test_template_has_the_six_customer_print_sections(self) -> None:
        definition = self._definition()
        fields = {field["fieldname"]: field for field in definition["fields"]}

        self.assertEqual(definition["autoname"], "field:template_name")
        self.assertEqual(definition["title_field"], "template_name")
        self.assertNotIn("quotation_form_preset", fields)
        for prefix, label in (
            ("quotation", "Quotation"),
            ("tax_invoice", "Tax Invoice"),
            ("delivery_note", "Delivery Note"),
            ("invoice", "Invoice"),
            ("abbreviated_tax_invoice", "Abbreviated Tax Invoice"),
            ("receipt", "Receipt"),
        ):
            with self.subTest(prefix=prefix):
                self.assertEqual(fields[f"{prefix}_section"]["label"], label)
                self.assertEqual(fields[f"use_{prefix}"]["default"], "1")
                self.assertEqual(fields[f"show_{prefix}_date"]["default"], "1")
                self.assertEqual(fields[f"{prefix}_language"]["default"], "Thai")
                self.assertEqual(
                    fields[f"{prefix}_language"].get("hidden", 0),
                    int(prefix == "tax_invoice"),
                )
                self.assertEqual(fields[f"{prefix}_original_count"]["default"], "1")
                self.assertEqual(fields[f"{prefix}_copy_count"]["default"], "0")

        for fieldname in (
            "show_tax_invoice_batch_serial",
            "print_tax_invoice_original",
            "print_tax_invoice_customer_copy",
            "print_tax_invoice_accounting_copy",
            "print_tax_invoice_sales_copy",
        ):
            with self.subTest(fieldname=fieldname):
                self.assertEqual(fields[fieldname]["default"], "1")

    @staticmethod
    def _definition() -> dict[str, Any]:
        path = Path(__file__).with_name("print_configuration_template.json")
        return json.loads(path.read_text())
