# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import quotation


class FakeQuotation(dict[str, Any]):
    """Minimal mapping-compatible Quotation used by print-context unit tests."""


class TestQuotationPrintConfiguration(UnitTestCase):
    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe, "get_all", return_value=["Customer Sales Person"])
    @patch.object(quotation.frappe.db, "get_value")
    def test_context_uses_customer_configuration_and_sales_team(
        self,
        mocked_get_value: MagicMock,
        _mocked_get_all: MagicMock,
        mocked_configuration: MagicMock,
    ) -> None:
        mocked_configuration.return_value = {
            "language": "Thai / English",
            "original_count": 2,
            "copy_count": 1,
            "copies": [
                {"kind": "original", "label": "ต้นฉบับ / Original 1/2"},
                {"kind": "original", "label": "ต้นฉบับ / Original 2/2"},
                {"kind": "copy", "label": "สำเนา / Copy"},
            ],
            "override_quotation_validity_text": 0,
            "quotation_delivery_terms": "Delivery within 30 days",
            "quotation_signatory_type": "Sales Representative",
        }
        mocked_get_value.side_effect = [
            "EMP-0001",
            {
                "employee_name": "Narin Sales",
                "designation": "Sales Executive",
                "cell_number": "081-234-5678",
            },
            "EMP-0001",
            {
                "employee_name": "Narin Sales",
                "designation": "Sales Executive",
                "cell_number": "081-234-5678",
            },
        ]
        doc = FakeQuotation(
            {
                "quotation_to": "Customer",
                "party_name": "CUST-0001",
                "transaction_date": "2026-07-01",
                "valid_till": "2026-07-31",
            }
        )

        context = quotation.get_quotation_print_context(cast(Document, doc))

        mocked_configuration.assert_called_once_with(doc, "quotation")
        self.assertEqual(
            context["validity_text"],
            "30 วัน นับถัดจากวันที่เสนอราคา / 30 days from the quotation date",
        )
        self.assertEqual(context["delivery_terms"], "Delivery within 30 days")
        self.assertEqual(context["signatory"]["name"], "Narin Sales")
        self.assertEqual(context["sales_contact"]["phone"], "081-234-5678")
        self.assertEqual(
            [copy["label"] for copy in context["copies"]],
            ["ต้นฉบับ / Original 1/2", "ต้นฉบับ / Original 2/2", "สำเนา / Copy"],
        )

    @patch.object(quotation, "get_document_print_context")
    def test_custom_validity_text_is_printed_verbatim(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = {
            "language": "Thai",
            "original_count": 1,
            "copy_count": 0,
            "copies": [{"kind": "original", "label": "ต้นฉบับ"}],
            "override_quotation_validity_text": 1,
            "quotation_custom_validity_text": "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
            "quotation_delivery_terms": "ส่งมอบภายใน 30 วัน",
            "quotation_signatory_type": "",
        }

        with (
            patch.object(quotation, "_sales_contact_details", return_value={}),
            patch.object(quotation, "_signatory_details", return_value={}),
        ):
            context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(
            context["validity_text"],
            "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
        )
        self.assertEqual(context["delivery_terms"], "ส่งมอบภายใน 30 วัน")

    @patch.object(quotation, "get_document_print_context")
    def test_custom_validity_override_requires_text(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = {
            "language": "Thai",
            "original_count": 1,
            "copy_count": 0,
            "copies": [{"kind": "original", "label": "ต้นฉบับ"}],
            "override_quotation_validity_text": 1,
            "quotation_custom_validity_text": "",
            "quotation_signatory_type": "",
        }

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value")
    def test_managing_director_uses_company_configuration(
        self, mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = {
            "language": "English",
            "original_count": 1,
            "copy_count": 0,
            "copies": [{"kind": "original", "label": "Original"}],
            "override_quotation_validity_text": 0,
            "quotation_delivery_terms": "",
            "quotation_signatory_type": "Managing Director",
        }
        mocked_get_value.side_effect = [
            "EMP-MD",
            {
                "employee_name": "Managing Director",
                "designation": "Managing Director",
                "cell_number": "02-000-0000",
            },
            "",
        ]
        doc = FakeQuotation({"company": "Connect Diagnostics"})

        context = quotation.get_quotation_print_context(cast(Document, doc))

        self.assertEqual(context["signatory"]["name"], "Managing Director")
        mocked_get_value.assert_any_call(
            "Company", "Connect Diagnostics", "quotation_authorized_signatory_employee"
        )

    @patch.object(quotation, "get_document_print_context")
    def test_language_flags_come_from_customer_configuration(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = {
            "language": "Thai / English",
            "original_count": 1,
            "copy_count": 0,
            "copies": [{"kind": "original", "label": "ต้นฉบับ / Original"}],
            "override_quotation_validity_text": 0,
            "quotation_delivery_terms": "",
            "quotation_signatory_type": "",
            "show_thai": True,
            "show_english": True,
        }

        with (
            patch.object(quotation, "_sales_contact_details", return_value={}),
            patch.object(quotation, "_signatory_details", return_value={}),
        ):
            context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertTrue(context["show_thai"])
        self.assertTrue(context["show_english"])

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value")
    def test_managing_director_uses_quotation_authorized_signatory_employee_override(
        self, mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = {
            "language": "English",
            "original_count": 1,
            "copy_count": 0,
            "copies": [{"kind": "original", "label": "Original"}],
            "override_quotation_validity_text": 0,
            "quotation_delivery_terms": "",
            "quotation_signatory_type": "Managing Director",
            "quotation_authorized_signatory_employee": "EMP-OVERRIDE",
        }
        mocked_get_value.return_value = {
            "employee_name": "Override Signatory",
            "designation": "Acting Director",
            "cell_number": "08-999-9999",
        }
        doc = FakeQuotation(
            {
                "company": "Connect Diagnostics",
                "quotation_signatory_type": "Managing Director",
                "quotation_authorized_signatory_employee": "EMP-OVERRIDE",
            }
        )

        context = quotation.get_quotation_print_context(cast(Document, doc))

        self.assertEqual(context["signatory"]["name"], "Override Signatory")
        mocked_get_value.assert_any_call(
            "Employee", "EMP-OVERRIDE", ["employee_name", "designation", "cell_number"], as_dict=True
        )

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe, "get_all", return_value=[])
    def test_sales_representative_requires_customer_sales_team(
        self, _mocked_get_all: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = {
            "language": "Thai",
            "copies": [{"kind": "original", "label": "ต้นฉบับ"}],
            "override_quotation_validity_text": 0,
            "quotation_delivery_terms": "",
            "quotation_signatory_type": "Sales Representative",
        }

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(
                cast(Document, FakeQuotation({"quotation_to": "Customer", "party_name": "CUST-0001"}))
            )
