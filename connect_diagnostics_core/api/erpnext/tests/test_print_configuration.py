# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase
from PIL import Image, ImageDraw

from connect_diagnostics_core.api.erpnext import print_configuration
from connect_diagnostics_core.setup import print_action_fields, print_documents


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

    def test_print_context_exposes_action_slots(self) -> None:
        context = print_configuration.get_document_print_context(sales_invoice(), "tax_invoice")

        self.assertEqual(
            set(context["print_actions"]),
            {action.key for action in print_action_fields.get_actions("Sales Invoice")},
        )
        self.assertEqual(context["print_actions"]["authorized"]["name"], "")
        self.assertIsNone(context["print_actions"]["authorized"]["acted_at"])


class TestPrintActionContext(UnitTestCase):
    @patch.object(
        print_configuration.frappe,
        "get_all",
        return_value=[
            {
                "name": "EMP-0001",
                "employee_name": "Approved Employee",
                "quotation_signature": "data:image/png;base64,signature",
            }
        ],
    )
    def test_resolves_employee_name_and_signature_in_one_query(self, get_all: MagicMock) -> None:
        action_at = "2026-09-04 09:15:00"
        doc = sales_invoice(
            received_by="EMP-0001",
            received_at=action_at,
            received_signature="data:image/png;base64,stored-signature",
            owner="owner@example.com",
        )

        context = print_configuration.get_print_action_context(doc)

        self.assertEqual(context["received"]["name"], "Approved Employee")
        self.assertEqual(context["received"]["signature"], "data:image/png;base64,stored-signature")
        self.assertEqual(context["received"]["acted_at"], action_at)
        get_all.assert_called_once_with(
            "Employee",
            filters={"name": ["in", ["EMP-0001"]]},
            fields=["name", "employee_name"],
        )

    @patch.object(
        print_configuration.frappe,
        "get_all",
        return_value=[
            {
                "name": "EMP-0001",
                "employee_name": "Approved Employee",
                "quotation_signature": "data:image/png;base64,current-signature",
            }
        ],
    )
    def test_does_not_use_the_employee_signature_when_the_snapshot_is_empty(
        self, _get_all: MagicMock
    ) -> None:
        context = print_configuration.get_print_action_context(
            sales_invoice(received_by="EMP-0001", received_at="2026-09-04 09:15:00")
        )

        self.assertEqual(context["received"]["name"], "Approved Employee")
        self.assertEqual(context["received"]["signature"], "")

    @patch.object(
        print_configuration.frappe,
        "get_all",
        return_value=[{"name": "EMP-0001", "employee_name": "Approved Employee"}],
    )
    def test_signature_widget_placeholder_is_rendered_as_missing_signature(self, _get_all: MagicMock) -> None:
        context = print_configuration.get_print_action_context(
            sales_invoice(
                received_by="EMP-0001",
                received_at="2026-09-04 09:15:00",
                received_signature="/assets/frappe/images/signature-placeholder.png",
            )
        )

        self.assertEqual(context["received"]["name"], "Approved Employee")
        self.assertEqual(context["received"]["signature"], "")

    @patch.object(
        print_configuration.frappe,
        "get_all",
        return_value=[{"name": "EMP-0001", "employee_name": "Submitter"}],
    )
    def test_checked_action_uses_submit_snapshot_for_the_standard_flow(self, _get_all: MagicMock) -> None:
        context = print_configuration.get_print_action_context(
            sales_invoice(
                submit_by="EMP-0001",
                submit_at="2026-09-04 09:15:00",
                submit_signature="data:image/png;base64,submit-signature",
            )
        )

        self.assertEqual(context["checked"], context["submit"])

    def test_does_not_infer_an_action_from_owner(self) -> None:
        context = print_configuration.get_print_action_context(
            sales_invoice(owner="owner@example.com", modified_by="owner@example.com")
        )

        self.assertEqual(context["received"]["employee"], "")
        self.assertEqual(context["received"]["name"], "")
        self.assertEqual(context["received"]["signature"], "")

    def test_crops_signature_canvas_and_removes_capture_baseline_for_print(self) -> None:
        image = Image.new("RGBA", (240, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.line((75, 25, 145, 55), fill=(80, 80, 80, 255), width=3)
        draw.line((20, 80, 220, 80), fill=(80, 80, 80, 255), width=2)
        source = BytesIO()
        image.save(source, format="PNG")
        signature = "data:image/png;base64," + base64.b64encode(source.getvalue()).decode("ascii")

        prepared = print_configuration.prepare_signature_for_print(signature)
        result = Image.open(BytesIO(base64.b64decode(prepared.split(",", 1)[1]))).convert("RGBA")
        alpha = result.getchannel("A")

        self.assertLess(result.width, image.width)
        self.assertLess(result.height, image.height)
        for y in range(result.height):
            self.assertLess(
                sum(cast(int, alpha.getpixel((x, y))) > 8 for x in range(result.width)),
                result.width // 2,
            )


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
