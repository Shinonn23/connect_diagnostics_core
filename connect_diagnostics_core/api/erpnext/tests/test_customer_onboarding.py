# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.erpnext import (
    customer,
    customer_credit_request,
    sales_invoice,
)
from connect_diagnostics_core.naming import customer as customer_naming
from connect_diagnostics_core.setup import customer as customer_setup
from connect_diagnostics_core.setup import customer_onboarding


class FakeDocument(frappe._dict):
    def __init__(
        self,
        values: dict[str, Any] | None = None,
        *,
        before: FakeDocument | None = None,
        is_new: bool = False,
    ) -> None:
        super().__init__(values or {})
        self._before = before
        self._is_new = is_new
        self.flags = frappe._dict()

    def append(self, fieldname: str, value: dict[str, Any]) -> FakeDocument:
        row = FakeDocument(value)
        self.setdefault(fieldname, []).append(row)
        return row

    def get_doc_before_save(self) -> FakeDocument | None:
        return self._before

    def is_new(self) -> bool:
        return bool(self._is_new)

    def set(self, fieldname: str, value: Any) -> None:
        self[fieldname] = value


class TestCustomerReadiness(UnitTestCase):
    def test_print_configuration_tab_holds_override_tables_not_flat_fields(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}

        self.assertEqual(fields["print_documents"]["fieldtype"], "Table")
        self.assertEqual(fields["print_documents"]["options"], "Print Document Configuration")
        self.assertEqual(fields["print_copies"]["fieldtype"], "Table")
        self.assertEqual(fields["print_copies"]["options"], "Print Copy Configuration")
        self.assertEqual(fields["print_documents_section"]["insert_after"], "customer_print_name")

        for retired in (
            "use_quotation",
            "use_tax_invoice",
            "use_delivery_note",
            "use_invoice",
            "use_abbreviated_tax_invoice",
            "use_receipt",
            "show_tax_invoice_date",
            "tax_invoice_language",
            "tax_invoice_original_count",
            "print_tax_invoice_original",
            "show_tax_invoice_batch_serial",
            "use_customer_po",
            # The onboarding queue and everything that fed it
            "customer_onboarding_section",
            "customer_onboarding_state",
            "correction_reason",
            "readiness_section",
            "quotation_readiness",
            "delivery_readiness",
            "tax_invoice_readiness",
            "email_readiness",
            "customer_readiness_summary",
            "no_delivery_required",
            "no_delivery_reason",
        ):
            with self.subTest(fieldname=retired):
                self.assertNotIn(retired, fields)

    def test_customer_keeps_its_own_scalar_print_defaults(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}

        self.assertEqual(fields["source_purchase_order_copy_required"]["default"], "0")
        self.assertEqual(fields["purchase_order_copy_count"]["default"], "1")
        self.assertEqual(fields["purchase_order_copy_count"]["non_negative"], 1)
        self.assertEqual(
            fields["purchase_order_copy_count"]["depends_on"],
            "eval:doc.source_purchase_order_copy_required",
        )
        self.assertEqual(fields["quotation_required"]["default"], "0")
        self.assertEqual(fields["quotation_signatory_type"]["default"], "Sales Representative")
        self.assertEqual(fields["quotation_delivery_terms"]["fieldtype"], "Small Text")
        for per_quotation in ("override_quotation_validity_text", "quotation_custom_validity_text"):
            with self.subTest(fieldname=per_quotation):
                self.assertNotIn(per_quotation, fields)

    def test_sales_order_print_date_field_is_retired(self) -> None:
        """Sales Order joined the print registry; the date is a per-document show_date."""
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}

        self.assertNotIn("print_date", fields)
        self.assertNotIn("legacy_print_preferences_section", fields)

    def test_customer_stores_a_template_link_and_print_name_default(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}

        self.assertEqual(fields["print_configuration_template"]["fieldtype"], "Link")
        self.assertEqual(fields["print_configuration_template"]["options"], "Print Configuration Template")
        self.assertEqual(fields["customer_print_name"]["fieldtype"], "Data")

    def test_tax_and_delivery_readiness_requires_matching_tax_address_and_contact(self) -> None:
        readiness = customer.build_readiness_values(
            customer={
                "customer_code": "CD-0001",
                "customer_name": "Readiness Customer",
                "customer_group": "Commercial",
                "territory": "Thailand",
                "tax_id": "0105555000001",
                "branch_code": "00000",
            },
            addresses=[
                {
                    "address_type": "Billing",
                    "address_line1": "1 Test Road",
                    "city": "Bangkok",
                    "county": "Pathum Wan",
                    "state": "Bangkok",
                    "pincode": "10330",
                    "country": "Thailand",
                    "tax_id": "0105555000001",
                    "branch_code": "00000",
                    "is_primary_address": 1,
                    "is_shipping_address": 1,
                    "disabled": 0,
                }
            ],
            contacts=[
                {
                    "full_name": "Customer Contact",
                    "mobile_no": "0812345678",
                    "is_primary_contact": 1,
                    "email_id": "contact@example.com",
                }
            ],
        )

        self.assertEqual(readiness["quotation_readiness"], customer.READY)
        self.assertEqual(readiness["tax_invoice_readiness"], customer.READY)
        self.assertEqual(readiness["delivery_readiness"], customer.READY)
        self.assertEqual(readiness["email_readiness"], customer.READY)


class TestCustomerOnboardingValidation(UnitTestCase):
    @patch.object(customer.frappe.db, "set_value")
    @patch.object(customer.frappe, "rename_doc")
    def test_customer_code_rename_preserves_business_customer_name(
        self,
        mocked_rename_doc: MagicMock,
        mocked_set_value: MagicMock,
    ) -> None:
        doc = FakeDocument(
            {"name": "CD-OLD-001", "customer_name": "Example Hospital"},
        )
        doc.flags = frappe._dict(customer_code_rename_to="CD-001")

        customer.on_update(cast(Document, doc))

        mocked_rename_doc.assert_called_once_with(
            "Customer", "CD-OLD-001", "CD-001", force=True, show_alert=False
        )
        mocked_set_value.assert_called_once_with(
            "Customer", "CD-001", "customer_name", "Example Hospital", update_modified=False
        )

    def test_manual_customer_code_becomes_document_name(self) -> None:
        doc = FakeDocument({"customer_code": "  CD-0001  ", "naming_series": "", "name": ""})

        customer_naming.prepare_customer_naming(doc)

        customer_naming.set_customer_code(doc)

        self.assertEqual(doc.customer_code, "CD-0001")
        self.assertEqual(doc.name, "CD-0001")
        self.assertEqual(doc.naming_series, "")

    def test_legacy_customer_series_function_is_retained_during_deprecation(self) -> None:
        self.assertEqual(
            customer_naming.series_for_customer(
                SimpleNamespace(customer_type="Company", customer_group="Government")
            ),
            "4H.###",
        )

    @patch.object(customer.frappe, "get_list", return_value=[])
    def test_customer_link_search_returns_only_active_customers(self, mocked_get_list: MagicMock) -> None:
        customer.customer_query("Customer", "CD", "name", 0, 20, {"customer_group": "Commercial"})

        self.assertEqual(
            mocked_get_list.call_args.kwargs["filters"],
            {"customer_group": "Commercial", "disabled": 0},
        )


class TestCustomerCreditLimit(UnitTestCase):
    def test_any_enabled_customer_may_ask_for_credit(self) -> None:
        customer_doc = FakeDocument({"name": "CD-0001", "disabled": 0})

        result = customer_credit_request._get_eligible_customer(
            "CD-0001", customer=cast(Document, customer_doc)
        )

        self.assertIs(result, customer_doc)

    def test_a_government_hospital_uses_the_same_credit_request(self) -> None:
        """GOV. HOSPITAL credit used to be set behind the scenes during onboarding."""
        customer_doc = FakeDocument({"name": "4H001", "disabled": 0, "customer_group": "GOV. HOSPITAL"})

        result = customer_credit_request._get_eligible_customer(
            "4H001", customer=cast(Document, customer_doc)
        )

        self.assertIs(result, customer_doc)

    def test_a_disabled_customer_cannot_ask_for_credit(self) -> None:
        customer_doc = FakeDocument({"name": "CD-0002", "disabled": 1})

        with self.assertRaises(frappe.ValidationError):
            customer_credit_request._get_eligible_customer("CD-0002", customer=cast(Document, customer_doc))

    def test_approved_credit_request_updates_the_cd_company_limit(self) -> None:
        customer_doc = FakeDocument(
            {"credit_limits": [FakeDocument({"company": "CD Company", "credit_limit": 1000})]}
        )

        customer_credit_request._set_customer_credit_limit(cast(Document, customer_doc), "CD Company", 5000)

        credit_limits = cast(list[FakeDocument], customer_doc["credit_limits"])
        self.assertEqual(credit_limits[0].credit_limit, 5000)
        self.assertEqual(credit_limits[0].bypass_credit_limit_check, 0)


class TestSellingImmediately(UnitTestCase):
    """A Customer is sellable the moment Sales saves it."""

    def test_saving_a_customer_does_not_disable_it(self) -> None:
        doc = FakeDocument({"customer_code": " CD-0001 "}, is_new=True)

        customer.before_validate(cast(Document, doc))

        self.assertEqual(doc["customer_code"], "CD-0001")
        self.assertNotIn("disabled", doc)

    def test_the_customer_workflow_is_gone(self) -> None:
        self.assertFalse(hasattr(customer_onboarding, "CUSTOMER_WORKFLOW_NAME"))
        self.assertFalse(hasattr(customer_onboarding, "DUPLICATE_VERIFIER_ROLE"))
        self.assertFalse(hasattr(customer, "_validate_onboarding_transition"))
        self.assertFalse(hasattr(customer, "refresh_linked_customer_readiness"))

    def test_address_and_contact_no_longer_rewrite_every_customer(self) -> None:
        """Readiness is calculated on demand, so nothing hooks Address or Contact."""
        self.assertNotIn("Address", hooks.doc_events)
        self.assertNotIn("Contact", hooks.doc_events)


class TestCustomerCodeFreeze(UnitTestCase):
    def _rename_attempt(self, has_transactions: bool) -> FakeDocument:
        previous = FakeDocument({"customer_code": "CD-OLD"})
        doc = FakeDocument({"name": "CD-OLD", "customer_code": "CD-NEW"}, before=previous)
        with (
            patch.object(customer, "_has_transactions", return_value=has_transactions),
            patch.object(customer.frappe.db, "exists", return_value=False),
        ):
            customer._validate_customer_code_change(cast(Document, doc), cast(Document, previous))
        return doc

    def test_a_code_can_still_be_corrected_before_the_first_transaction(self) -> None:
        doc = self._rename_attempt(has_transactions=False)

        self.assertEqual(doc.flags.get("customer_code_rename_to"), "CD-NEW")

    def test_a_code_freezes_once_the_customer_has_transactions(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            self._rename_attempt(has_transactions=True)


class TestTaxInvoiceGate(UnitTestCase):
    """Incomplete tax details warn at issue time; they never block the submit."""

    def _submit(self, readiness: dict[str, str]) -> MagicMock:
        doc = FakeDocument({"customer": "CD-0001", "customer_name": "Bangkok Hospital"})
        with (
            patch.object(customer, "get_readiness_for_customer", return_value=readiness),
            patch.object(sales_invoice.frappe, "msgprint") as msgprint,
        ):
            sales_invoice.validate_tax_invoice_readiness(cast(Document, doc))
        return msgprint

    def test_a_ready_customer_submits_without_a_warning(self) -> None:
        msgprint = self._submit({"tax_invoice_readiness": customer.READY})

        msgprint.assert_not_called()

    def test_an_incomplete_customer_is_warned_with_what_is_missing(self) -> None:
        msgprint = self._submit(
            {
                "tax_invoice_readiness": customer.MISSING,
                "customer_readiness_summary": "Tax Invoice: Customer Tax ID",
            }
        )

        msgprint.assert_called_once()
        self.assertIn("Customer Tax ID", msgprint.call_args.args[0])

    def test_an_invoice_without_a_customer_is_left_alone(self) -> None:
        doc = FakeDocument({"customer": ""})

        sales_invoice.validate_tax_invoice_readiness(cast(Document, doc))
