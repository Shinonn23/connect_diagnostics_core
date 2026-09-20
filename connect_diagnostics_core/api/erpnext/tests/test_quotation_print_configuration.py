# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import quotation

SALES_REPRESENTATIVE = {
    "employee_name": "ภานุพงษ์ ตั้งพรประเสริฐ",
    "cell_number": "090-660-5666",
    "approval_signature": "data:image/png;base64,sales-signature",
}


class FakeQuotation(dict[str, Any]):
    """Minimal mapping-compatible Quotation used by print-context unit tests."""


def _configuration(**overrides: Any) -> dict[str, Any]:
    """Return a resolved configuration with the fields every context needs."""
    return {
        "language": "Thai",
        "copies": [{"kind": "original", "label": "ต้นฉบับ"}],
        "edit_validity_text": 0,
        "validity_text": "",
        "quotation_delivery_terms": "",
        "quotation_signatory_type": quotation.quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
        "sales_representative_employee": "EMP-0001",
        **overrides,
    }


class TestQuotationPrintConfiguration(UnitTestCase):
    """Cover signatory resolution and the independent validity options.

    ``show_date`` and signatory type form the four print-sidebar combinations;
    validity and delivery terms remain document-level behavior.
    """

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_sales_representative_signs_with_name_and_caption(
        self, mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        """A Sales Representative's name and E-Signature print above ผู้เสนอราคา."""
        mocked_configuration.return_value = _configuration()
        doc = FakeQuotation(
            {
                "quotation_to": "Customer",
                "party_name": "CUST-0001",
                "transaction_date": "2026-06-15",
                "valid_till": "2026-09-13",
            }
        )

        context = quotation.get_quotation_print_context(cast(Document, doc))

        mocked_configuration.assert_called_once_with(doc, "quotation")
        self.assertEqual(context["signatory"]["name"], "ภานุพงษ์ ตั้งพรประเสริฐ")
        self.assertEqual(context["signatory"]["caption"], "ผู้เสนอราคา")
        self.assertEqual(context["validity_text"], "90 วัน นับถัดจากวันที่เสนอราคา")
        self.assertFalse(context["validity_is_custom"])
        mocked_get_value.assert_called_with(
            "Employee",
            "EMP-0001",
            ["employee_name", "cell_number", "approval_signature"],
            as_dict=True,
        )

    @patch.object(quotation, "get_document_print_context")
    def test_workflow_signatory_snapshot_is_used_for_name_signature_and_time(
        self, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(
            sales_representative_employee="",
            print_actions={
                "signatory": {
                    "employee": "EMP-SNAPSHOT",
                    "name": "Snapshot Signatory",
                    "signature": "data:image/png;base64,stored-signature",
                    "acted_at": "2026-09-05 10:30:00",
                }
            },
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(context["signatory"]["employee"], "EMP-SNAPSHOT")
        self.assertEqual(context["signatory"]["name"], "Snapshot Signatory")
        self.assertEqual(context["signatory"]["signature"], "data:image/png;base64,stored-signature")
        self.assertEqual(context["signatory"]["acted_at"], "2026-09-05 10:30:00")

    @patch.object(quotation, "_is_real_print_or_pdf_request", return_value=True)
    @patch.object(quotation, "get_document_print_context")
    def test_snapshot_without_signature_does_not_block_printing(
        self, mocked_configuration: MagicMock, _mocked_real_print: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(
            sales_representative_employee="",
            print_actions={
                "signatory": {
                    "employee": "EMP-SNAPSHOT",
                    "name": "No Signature Signatory",
                    "signature": "",
                    "acted_at": "2026-09-05 10:30:00",
                }
            },
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(context["signatory"]["name"], "No Signature Signatory")
        self.assertEqual(context["signatory"]["acted_at"], "2026-09-05 10:30:00")
        self.assertFalse(context["signatory"]["signature"])
        self.assertFalse(context["signatory"]["ready"])

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_managing_director_prints_a_blank_name_without_touching_the_database(
        self, mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        """Preview remains usable before a manager is selected."""
        mocked_configuration.return_value = _configuration(
            quotation_signatory_type=quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
            sales_representative_employee="",
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(context["signatory"]["name"], "")
        self.assertEqual(context["signatory"]["employee"], "")
        self.assertEqual(context["signatory"]["caption"], "กรรมการผู้จัดการ")
        mocked_get_value.assert_not_called()

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_managing_director_still_prints_the_sales_contact(
        self, _mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        """The Sales Contact remains the Quotation's representative."""
        mocked_configuration.return_value = _configuration(
            quotation_signatory_type=quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(context["signatory"]["name"], "")
        self.assertEqual(context["sales_contact"]["name"], "ภานุพงษ์ ตั้งพรประเสริฐ")
        self.assertEqual(context["sales_contact"]["phone"], "090-660-5666")

    @patch.object(
        quotation.company_api,
        "get_quotation_authorized_signatories",
        return_value=[
            {
                "employee": "EMP-MD",
                "name": "Managing Director",
                "signature": "data:image/png;base64,manager-signature",
                "ready": True,
            }
        ],
    )
    @patch.object(
        quotation.frappe.db,
        "get_value",
        return_value={
            "employee_name": "Managing Director",
            "cell_number": "",
            "approval_signature": "data:image/png;base64,manager-signature",
        },
    )
    @patch.object(quotation, "get_document_print_context")
    def test_managing_director_uses_the_selected_company_employee(
        self,
        mocked_configuration: MagicMock,
        mocked_get_value: MagicMock,
        _mocked_managers: MagicMock,
    ) -> None:
        mocked_configuration.return_value = _configuration(
            quotation_signatory_type=quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
            manager_signatory_employee="EMP-MD",
        )

        context = quotation.get_quotation_print_context(
            cast(Document, FakeQuotation({"company": "COMP-0001"}))
        )

        self.assertEqual(context["signatory"]["employee"], "EMP-MD")
        self.assertEqual(context["signatory"]["name"], "Managing Director")
        self.assertEqual(context["signatory"]["signature"], "data:image/png;base64,manager-signature")
        self.assertTrue(context["signatory"]["ready"])
        mocked_get_value.assert_called()

    @patch.object(quotation, "_is_real_print_or_pdf_request", return_value=True)
    @patch.object(quotation.company_api, "get_quotation_authorized_signatories", return_value=[])
    @patch.object(quotation, "get_document_print_context")
    def test_real_print_rejects_a_manager_outside_the_company_allow_list(
        self,
        mocked_configuration: MagicMock,
        _mocked_managers: MagicMock,
        _mocked_real_print: MagicMock,
    ) -> None:
        mocked_configuration.return_value = _configuration(
            quotation_signatory_type=quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
            manager_signatory_employee="EMP-MD",
        )

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(cast(Document, FakeQuotation({"company": "COMP-0001"})))

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_custom_validity_text_is_printed_verbatim(
        self, _mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        """Custom validity text stays independent of signatory selection."""
        mocked_configuration.return_value = _configuration(
            quotation_signatory_type=quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
            edit_validity_text=1,
            validity_text="1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
            quotation_delivery_terms="ส่งมอบภายใน 30 วัน",
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(context["validity_text"], "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า")
        self.assertTrue(context["validity_is_custom"])
        self.assertEqual(context["delivery_terms"], "ส่งมอบภายใน 30 วัน")

    @patch.object(quotation, "get_document_print_context")
    def test_custom_validity_override_requires_text(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = _configuration(
            edit_validity_text=1,
            validity_text="",
        )

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

    @patch.object(quotation, "get_document_print_context")
    def test_preview_remains_available_when_sales_representative_is_missing(
        self, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(sales_representative_employee="")

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertFalse(context["signatory"]["ready"])
        self.assertIn("required", context["signatory"]["reason"])

    @patch.object(quotation, "_is_real_print_or_pdf_request", return_value=True)
    @patch.object(quotation, "get_document_print_context")
    def test_real_print_requires_a_sales_representative(
        self, mocked_configuration: MagicMock, _mocked_real_print: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(sales_representative_employee="")

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

    @patch.object(quotation, "get_document_print_context")
    def test_unknown_signatory_type_is_rejected(self, mocked_configuration: MagicMock) -> None:
        mocked_configuration.return_value = _configuration(quotation_signatory_type="")

        with self.assertRaises(frappe.ValidationError):
            quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_caption_and_validity_follow_the_resolved_language(
        self, _mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(
            language="Thai / English",
            show_thai=True,
            show_english=True,
        )
        doc = FakeQuotation({"transaction_date": "2026-07-01", "valid_till": "2026-07-31"})

        context = quotation.get_quotation_print_context(cast(Document, doc))

        self.assertEqual(context["signatory"]["caption"], "ผู้เสนอราคา / Sales Representative")
        self.assertEqual(
            context["validity_text"],
            "30 วัน นับถัดจากวันที่เสนอราคา / 30 days from the quotation date",
        )
        self.assertTrue(context["show_thai"])
        self.assertTrue(context["show_english"])

    @patch.object(quotation, "get_document_print_context")
    @patch.object(quotation.frappe.db, "get_value", return_value=SALES_REPRESENTATIVE)
    def test_context_keeps_the_resolved_copies(
        self, _mocked_get_value: MagicMock, mocked_configuration: MagicMock
    ) -> None:
        mocked_configuration.return_value = _configuration(
            copies=[
                {"kind": "original", "label": "ต้นฉบับ 1/2"},
                {"kind": "original", "label": "ต้นฉบับ 2/2"},
                {"kind": "copy", "label": "สำเนา"},
            ],
        )

        context = quotation.get_quotation_print_context(cast(Document, FakeQuotation()))

        self.assertEqual(
            [copy["label"] for copy in context["copies"]],
            ["ต้นฉบับ 1/2", "ต้นฉบับ 2/2", "สำเนา"],
        )


class TestValidateSignatoryBeforeSubmit(UnitTestCase):
    def test_throws_when_sales_representative_type_has_no_employee(self) -> None:
        doc = FakeQuotation(
            {
                "quotation_signatory_type": quotation.quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
                "sales_representative_employee": "",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            quotation.validate_signatory_before_submit(cast(Document, doc))

    def test_throws_when_type_is_empty_since_it_defaults_to_sales_representative(self) -> None:
        doc = FakeQuotation({"quotation_signatory_type": "", "sales_representative_employee": ""})

        with self.assertRaises(frappe.ValidationError):
            quotation.validate_signatory_before_submit(cast(Document, doc))

    def test_passes_when_employee_is_set(self) -> None:
        doc = FakeQuotation(
            {
                "quotation_signatory_type": quotation.quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
                "sales_representative_employee": "EMP-0001",
            }
        )

        quotation.validate_signatory_before_submit(cast(Document, doc))

    def test_passes_for_managing_director_regardless_of_employee(self) -> None:
        doc = FakeQuotation(
            {
                "quotation_signatory_type": quotation.quotation_setup.SIGNATORY_MANAGING_DIRECTOR,
                "sales_representative_employee": "",
            }
        )

        quotation.validate_signatory_before_submit(cast(Document, doc))


class TestValidateDeliveryTermsBeforeSubmit(UnitTestCase):
    def test_throws_when_delivery_terms_is_empty(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            quotation.validate_delivery_terms_before_submit(cast(Document, FakeQuotation()))

    def test_passes_when_delivery_terms_is_set(self) -> None:
        doc = FakeQuotation({"quotation_delivery_terms": "60 วัน นับถัดจากวันที่ได้รับใบสั่งซื้อ"})

        quotation.validate_delivery_terms_before_submit(cast(Document, doc))
