# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_configuration_template, print_documents


class FakeTemplate(frappe._dict):
    """Stand in for a Template document while its rows are being built."""

    def append(self, fieldname: str, values: dict[str, Any]) -> None:
        self.setdefault(fieldname, []).append(FakeRow(values))


class FakeRow(frappe._dict):
    def set(self, key: str, value: Any) -> None:
        self[key] = value


def seeded_template(policy_name: str) -> FakeTemplate:
    template = FakeTemplate()
    # ty: ignore[invalid-argument-type] - FakeTemplate stands in for a Document
    print_configuration_template.seed_registry_rows(cast(Document, template))
    print_configuration_template._apply_policy(
        cast(Document, template), print_configuration_template.POLICY_TEMPLATES[policy_name]
    )
    return template


def rows_by_document(template: FakeTemplate) -> dict[str, FakeRow]:
    return {str(row["document_key"]): row for row in template["print_documents"]}


class TestPolicyTemplates(UnitTestCase):
    def test_every_policy_covers_the_whole_registry(self) -> None:
        for policy_name in print_configuration_template.POLICY_TEMPLATES:
            with self.subTest(policy=policy_name):
                rows = rows_by_document(seeded_template(policy_name))

                self.assertEqual(
                    set(rows),
                    {document.key for document in print_documents.PRINT_DOCUMENTS},
                )

    def test_tax_invoice_only_prints_neither_receipt(self) -> None:
        rows = rows_by_document(seeded_template("Tax Invoice Only"))

        self.assertEqual(rows["tax_invoice"]["enabled"], 1)
        self.assertEqual(rows["receipt"]["enabled"], 0)
        self.assertEqual(rows["abbreviated_tax_invoice"]["enabled"], 0)
        self.assertEqual(rows["tax_invoice"]["show_date"], 1)

    def test_tax_invoice_and_receipt_omits_the_date(self) -> None:
        rows = rows_by_document(seeded_template("Tax Invoice and Receipt"))

        self.assertEqual(rows["receipt"]["enabled"], 1)
        self.assertEqual(rows["abbreviated_tax_invoice"]["enabled"], 0)
        for document_key, row in rows.items():
            with self.subTest(document=document_key):
                self.assertEqual(row["show_date"], 0)

    def test_abbreviated_policy_prints_the_short_form(self) -> None:
        rows = rows_by_document(seeded_template("Tax Invoice and Abbreviated Receipt"))

        self.assertEqual(rows["abbreviated_tax_invoice"]["enabled"], 1)
        self.assertEqual(rows["receipt"]["enabled"], 0)
        self.assertEqual(rows["tax_invoice"]["show_date"], 1)

    def test_a_policy_never_touches_the_copy_rows(self) -> None:
        """Copies stay at their registry defaults; a policy only names documents."""
        template = seeded_template("Tax Invoice and Receipt")

        counts = {
            (str(row["document_key"]), str(row["copy_key"])): row["count"]
            for row in template["print_copies"]
        }
        self.assertEqual(counts[("tax_invoice", "original")], 1)
        self.assertEqual(counts[("quotation", "copy")], 0)
