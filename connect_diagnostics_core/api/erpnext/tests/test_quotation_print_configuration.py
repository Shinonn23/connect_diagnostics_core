# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import quotation
from connect_diagnostics_core.setup import company as company_setup
from connect_diagnostics_core.setup import quotation as quotation_setup


class FakeQuotation(dict[str, Any]):
    def __init__(self, values: dict[str, Any], *, is_new: bool = False) -> None:
        super().__init__(values)
        self._is_new = is_new

    def is_new(self) -> bool:
        return self._is_new

    def set(self, fieldname: str, value: Any) -> None:
        self[fieldname] = value


class TestQuotationPrintConfiguration(UnitTestCase):
    def test_setup_fields_are_audited_and_editable_after_submit(self) -> None:
        fields = {field["fieldname"]: field for field in quotation_setup.CUSTOM_FIELDS["Quotation"]}

        self.assertEqual(
            fields["quotation_print_configuration_section"]["fieldtype"],
            "Tab Break",
        )
        for fieldname in quotation_setup.PRINT_CONFIGURATION_FIELDNAMES:
            with self.subTest(fieldname=fieldname):
                self.assertNotIn("default", fields[fieldname])
                self.assertEqual(fields[fieldname]["allow_on_submit"], 1)

        self.assertEqual(
            quotation_setup.PROPERTY_SETTERS["Quotation"], [(None, "track_changes", "1", "Check")]
        )
        company_field = company_setup.CUSTOM_FIELDS["Company"][0]
        self.assertEqual(company_field["options"], "Employee")

    @patch.object(quotation.frappe.db, "get_value", return_value="EMP-0001")
    def test_new_quotation_defaults_to_form_01(self, _mocked_get_value: MagicMock) -> None:
        doc = FakeQuotation(
            {
                "company": "Connect Diagnostics",
                "sales_team": [FakeQuotation({"sales_person": "Sales Person A"})],
                "quotation_delivery_terms": "Delivery within 30 days",
            },
            is_new=True,
        )

        quotation.before_validate(cast(Document, doc))

        self.assertEqual(doc["quotation_form_preset"], "Form 01")
        self.assertEqual(doc["show_quotation_date"], 1)
        self.assertEqual(doc["quotation_signatory_type"], "Sales Representative")
        self.assertEqual(doc["quotation_validity_mode"], "Valid Till")
        self.assertEqual(doc["quotation_sales_representative"], "Sales Person A")
        self.assertEqual(doc["quotation_language"], "Thai")
        self.assertEqual(doc["quotation_original_count"], 1)
        self.assertEqual(doc["quotation_copy_count"], 0)

    @patch.object(quotation.frappe.db, "get_value", return_value="EMP-0001")
    def test_modified_preset_values_become_custom(self, _mocked_get_value: MagicMock) -> None:
        doc = FakeQuotation(
            {
                "quotation_form_preset": "Form 01",
                "show_quotation_date": 0,
                "quotation_signatory_type": "Sales Representative",
                "quotation_sales_representative": "Sales Person A",
                "quotation_validity_mode": "Valid Till",
                "quotation_delivery_terms": "Delivery within 30 days",
                "quotation_language": "Thai",
                "quotation_original_count": 1,
                "quotation_copy_count": 0,
            }
        )

        quotation.before_validate(cast(Document, doc))

        self.assertEqual(doc["quotation_form_preset"], "Custom")

    @patch.object(quotation.frappe, "get_all", return_value=["Customer Sales Person"])
    @patch.object(quotation.frappe.db, "get_value")
    @patch.object(quotation.frappe, "has_permission")
    def test_customer_snapshot_uses_customer_defaults_and_first_sales_person(
        self,
        mocked_has_permission: MagicMock,
        mocked_get_value: MagicMock,
        _mocked_get_all: MagicMock,
    ) -> None:
        mocked_get_value.return_value = {
            "quotation_form_preset": "Form 04",
            "show_quotation_date": 1,
            "quotation_signatory_type": "Managing Director",
            "quotation_validity_mode": "Custom Text",
            "quotation_custom_validity_text": "One year from approval",
            "quotation_delivery_terms": "Delivery within 45 days",
            "quotation_language": "Thai / English",
            "quotation_original_count": 2,
            "quotation_copy_count": 1,
        }

        result = quotation.get_print_configuration_defaults("CUST-0001")

        self.assertEqual(result["data"]["quotation_form_preset"], "Form 04")
        self.assertEqual(result["data"]["quotation_custom_validity_text"], "One year from approval")
        self.assertEqual(result["data"]["quotation_delivery_terms"], "Delivery within 45 days")
        self.assertEqual(
            result["data"]["quotation_sales_representative"],
            "Customer Sales Person",
        )
        mocked_has_permission.assert_any_call("Quotation", "create", throw=True)
        mocked_has_permission.assert_any_call("Customer", "read", "CUST-0001", throw=True)

    @patch.object(quotation.frappe.db, "get_value", return_value=None)
    def test_sales_person_requires_employee(self, _mocked_get_value: MagicMock) -> None:
        doc = FakeQuotation(
            {
                "quotation_form_preset": "Custom",
                "quotation_signatory_type": "Sales Representative",
                "quotation_sales_representative": "Unlinked Sales Person",
                "quotation_validity_mode": "Valid Till",
                "quotation_delivery_terms": "Delivery within 30 days",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            quotation.before_validate(cast(Document, doc))

    @patch.object(quotation.frappe.db, "get_value")
    def test_print_context_uses_employee_and_generates_originals_and_copies(
        self,
        mocked_get_value: MagicMock,
    ) -> None:
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
                "quotation_language": "Thai / English",
                "show_quotation_date": 1,
                "quotation_validity_mode": "Valid Till",
                "quotation_delivery_terms": "Delivery within 30 days",
                "transaction_date": "2026-07-01",
                "valid_till": "2026-07-31",
                "quotation_signatory_type": "Sales Representative",
                "quotation_sales_representative": "Sales Person A",
                "quotation_original_count": 2,
                "quotation_copy_count": 1,
            }
        )

        context = quotation.get_quotation_print_context(cast(Document, doc))

        self.assertEqual(
            context["validity_text"],
            "30 วัน นับถัดจากวันที่เสนอราคา / 30 days from the quotation date",
        )
        self.assertEqual(context["signatory"]["name"], "Narin Sales")
        self.assertEqual(context["sales_contact"]["phone"], "081-234-5678")
        self.assertEqual(
            [copy["label"] for copy in context["copies"]],
            ["ต้นฉบับ / Original 1/2", "ต้นฉบับ / Original 2/2", "สำเนา / Copy"],
        )

    def test_custom_validity_text_is_printed_verbatim(self) -> None:
        doc = FakeQuotation(
            {
                "quotation_language": "Thai",
                "show_quotation_date": 0,
                "quotation_validity_mode": "Custom Text",
                "quotation_custom_validity_text": "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
                "quotation_delivery_terms": "ส่งมอบภายใน 30 วัน",
                "quotation_original_count": 1,
                "quotation_copy_count": 0,
            }
        )

        with (
            patch.object(quotation, "_signatory_details", return_value={}),
            patch.object(quotation, "_sales_contact_details", return_value={}),
        ):
            context = quotation.get_quotation_print_context(cast(Document, doc))

        self.assertFalse(context["show_date"])
        self.assertEqual(
            context["validity_text"],
            "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
        )
        self.assertEqual(context["delivery_terms"], "ส่งมอบภายใน 30 วัน")

    def test_language_flags_cover_thai_english_and_bilingual(self) -> None:
        expected_flags = {
            "Thai": (True, False),
            "English": (False, True),
            "Thai / English": (True, True),
        }

        for language, expected in expected_flags.items():
            with (
                self.subTest(language=language),
                patch.object(quotation, "_signatory_details", return_value={}),
                patch.object(quotation, "_sales_contact_details", return_value={}),
            ):
                context = quotation.get_quotation_print_context(
                    cast(
                        Document,
                        FakeQuotation(
                            {
                                "quotation_language": language,
                                "quotation_original_count": 1,
                                "quotation_copy_count": 0,
                            }
                        ),
                    )
                )

                self.assertEqual(
                    (context["show_thai"], context["show_english"]),
                    expected,
                )

    @patch.object(quotation.frappe.db, "get_value", return_value="EMP-0001")
    def test_delivery_terms_are_required(self, _mocked_get_value: MagicMock) -> None:
        doc = FakeQuotation(
            {
                "quotation_form_preset": "Custom",
                "quotation_signatory_type": "Sales Representative",
                "quotation_sales_representative": "Sales Person A",
                "quotation_validity_mode": "Valid Till",
                "quotation_delivery_terms": "",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            quotation.before_validate(cast(Document, doc))
