# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import tds_guard


def make_document(doctype: str, **values: object) -> Document:
    return cast(Document, frappe._dict({"doctype": doctype, **values}))


class TestTDSGuard(UnitTestCase):
    def test_rejects_tds_values_on_business_documents(self) -> None:
        documents = (
            make_document("Customer", tax_withholding_category="TDS-India"),
            make_document("Supplier", tax_withholding_group="TDS Group"),
            make_document("Purchase Invoice", apply_tds=1),
            make_document("Sales Invoice", override_tax_withholding_entries=1),
            make_document("Payment Entry", tax_withholding_category="TDS-India"),
            make_document("Journal Entry", tax_withholding_entries=[frappe._dict(name="TDS-1")]),
            make_document("Item", sales_tax_withholding_category="TDS-India"),
            make_document("Lower Deduction Certificate", tax_withholding_category="TDS-India"),
        )

        with (
            patch.object(tds_guard, "_is_administrator", return_value=False),
            patch.object(tds_guard, "_is_setup_context", return_value=False),
            patch.object(tds_guard.frappe, "throw", side_effect=frappe.ValidationError) as mocked_throw,
        ):
            for document in documents:
                with self.subTest(doctype=document.doctype):
                    with self.assertRaises(frappe.ValidationError):
                        tds_guard.block_tds(document, "before_validate")

        self.assertEqual(mocked_throw.call_count, len(documents))

    def test_rejects_tds_category_nested_in_invoice_items(self) -> None:
        document = make_document(
            "Purchase Invoice",
            items=[frappe._dict(tax_withholding_category="TDS-India")],
        )

        with (
            patch.object(tds_guard, "_is_administrator", return_value=False),
            patch.object(tds_guard, "_is_setup_context", return_value=False),
            patch.object(tds_guard.frappe, "throw", side_effect=frappe.ValidationError),
        ):
            with self.assertRaises(frappe.ValidationError):
                tds_guard.block_tds(document, "before_validate")

    def test_allows_core_invoice_item_apply_tds_default(self) -> None:
        for doctype in ("Purchase Invoice Item", "Sales Invoice Item"):
            with self.subTest(doctype=doctype):
                document = make_document(doctype, apply_tds=1)
                with (
                    patch.object(tds_guard, "_is_administrator", return_value=False),
                    patch.object(tds_guard, "_is_setup_context", return_value=False),
                    patch.object(tds_guard.frappe, "throw") as mocked_throw,
                ):
                    tds_guard.block_tds(document, "before_validate")
                mocked_throw.assert_not_called()

    def test_administrator_can_repair_business_documents(self) -> None:
        with (
            patch.object(tds_guard, "_is_administrator", return_value=True),
            patch.object(tds_guard.frappe, "throw") as mocked_throw,
        ):
            tds_guard.block_tds(make_document("Payment Entry", apply_tds=1), "before_validate")
        mocked_throw.assert_not_called()

    def test_tds_master_remains_blocked_for_administrator(self) -> None:
        with (
            patch.object(tds_guard, "_is_administrator", return_value=True),
            patch.object(tds_guard, "_is_setup_context", return_value=False),
            patch.object(tds_guard.frappe, "throw", side_effect=frappe.ValidationError),
        ):
            with self.assertRaises(frappe.ValidationError):
                tds_guard.block_doctype(make_document("Tax Withholding Category"), "before_validate")

    def test_setup_context_allows_tds_master_migration(self) -> None:
        with (
            patch.object(tds_guard, "_is_setup_context", return_value=True),
            patch.object(tds_guard.frappe, "throw") as mocked_throw,
        ):
            tds_guard.block_doctype(make_document("Tax Withholding Category"), "before_validate")
        mocked_throw.assert_not_called()
