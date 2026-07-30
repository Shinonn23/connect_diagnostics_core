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
from connect_diagnostics_core.api.erpnext import customer, customer_credit_request, item
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


def _item_search_sql_call(mocked_sql: MagicMock) -> tuple[str, dict[str, Any]]:
    for sql_call in reversed(mocked_sql.call_args_list):
        query = cast(str, sql_call.args[0])
        if "FROM `tabItem` i" in query:
            return query, cast(dict[str, Any], sql_call.args[1])
    raise AssertionError("Item search SQL was not executed.")


class TestCustomerReadiness(UnitTestCase):
    def test_onboarding_fields_are_grouped_in_dedicated_tab(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}
        onboarding_layout = [
            ("customer_onboarding_section", "portal_users", "Tab Break"),
            ("customer_onboarding_state", "customer_onboarding_section", "Link"),
            ("correction_reason", "customer_onboarding_state", "Small Text"),
            ("readiness_section", "correction_reason", "Section Break"),
            ("quotation_readiness", "readiness_section", "Select"),
            ("delivery_readiness", "quotation_readiness", "Select"),
            ("tax_invoice_readiness", "delivery_readiness", "Select"),
            ("email_readiness", "tax_invoice_readiness", "Select"),
            ("customer_readiness_summary", "email_readiness", "Small Text"),
            ("no_delivery_required", "customer_readiness_summary", "Check"),
            ("no_delivery_reason", "no_delivery_required", "Small Text"),
            ("document_preferences_section", "no_delivery_reason", "Tab Break"),
        ]

        for fieldname, insert_after, fieldtype in onboarding_layout:
            with self.subTest(fieldname=fieldname):
                self.assertEqual(fields[fieldname]["insert_after"], insert_after)
                self.assertEqual(fields[fieldname]["fieldtype"], fieldtype)

    def test_document_preferences_have_fixed_per_document_defaults(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}
        insert_after = "document_preferences_section"

        for prefix, label, use_fieldname in customer_setup.DOCUMENT_PREFERENCES:
            section_fieldname = f"{prefix}_document_preferences_section"
            show_date_fieldname = f"show_{prefix}_date"
            language_fieldname = f"{prefix}_language"
            column_fieldname = f"{prefix}_document_preferences_column"
            original_count_fieldname = f"{prefix}_original_count"
            copy_count_fieldname = f"{prefix}_copy_count"
            depends_on = f"eval:doc.{use_fieldname}"

            with self.subTest(prefix=prefix):
                self.assertEqual(fields[section_fieldname]["label"], label)
                self.assertEqual(fields[section_fieldname]["insert_after"], insert_after)
                self.assertEqual(fields[use_fieldname]["default"], "1")
                self.assertEqual(fields[show_date_fieldname]["default"], "1")
                self.assertEqual(fields[show_date_fieldname]["depends_on"], depends_on)
                self.assertEqual(fields[language_fieldname]["options"], "Thai\nEnglish\nThai / English")
                self.assertEqual(fields[language_fieldname]["default"], "Thai")
                self.assertEqual(fields[language_fieldname]["depends_on"], depends_on)
                self.assertEqual(fields[column_fieldname]["depends_on"], depends_on)
                self.assertEqual(fields[original_count_fieldname]["default"], "1")
                self.assertEqual(fields[original_count_fieldname]["non_negative"], 1)
                self.assertEqual(fields[original_count_fieldname]["depends_on"], depends_on)
                self.assertEqual(fields[copy_count_fieldname]["default"], "0")
                self.assertEqual(fields[copy_count_fieldname]["non_negative"], 1)
                self.assertEqual(fields[copy_count_fieldname]["depends_on"], depends_on)

            insert_after = copy_count_fieldname

        self.assertEqual(
            fields["purchase_order_copy_preferences_section"]["insert_after"],
            insert_after,
        )
        self.assertEqual(fields["use_customer_po"]["default"], "1")
        self.assertEqual(fields["purchase_order_copy_count"]["default"], "1")
        self.assertEqual(fields["purchase_order_copy_count"]["non_negative"], 1)
        self.assertEqual(
            fields["purchase_order_copy_count"]["depends_on"],
            "eval:doc.use_customer_po",
        )
        self.assertEqual(
            fields["print_date"]["label"],
            "Legacy Global Print Date (Current Print Formats)",
        )

    def test_quotation_customer_defaults_match_form_01(self) -> None:
        fields = {field["fieldname"]: field for field in customer_setup.CUSTOM_FIELDS["Customer"]}

        self.assertEqual(fields["quotation_form_preset"]["default"], "Form 01")
        self.assertEqual(fields["show_quotation_date"]["label"], "Show Quotation Date")
        self.assertEqual(fields["quotation_signatory_type"]["default"], "Sales Representative")
        self.assertEqual(fields["quotation_validity_mode"]["default"], "Valid Till")
        self.assertEqual(
            fields["quotation_delivery_terms"]["mandatory_depends_on"],
            "eval:doc.use_quotation",
        )
        self.assertEqual(
            fields["quotation_custom_validity_text"]["depends_on"],
            "eval:doc.use_quotation && doc.quotation_validity_mode=='Custom Text'",
        )

    def test_quotation_delivery_terms_are_required_when_quotation_is_enabled(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            customer._validate_quotation_delivery_terms(
                cast(Document, FakeDocument({"use_quotation": 1, "quotation_delivery_terms": ""}))
            )

        customer._validate_quotation_delivery_terms(
            cast(Document, FakeDocument({"use_quotation": 0, "quotation_delivery_terms": ""}))
        )

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

    def test_no_delivery_requires_a_reason_before_becoming_not_applicable(self) -> None:
        values = {
            "customer_code": "CD-0002",
            "customer_name": "No Delivery Customer",
            "customer_group": "Commercial",
            "territory": "Thailand",
            "tax_id": "0105555000002",
            "branch_code": "00000",
            "no_delivery_required": 1,
            "no_delivery_reason": "",
        }
        missing_reason = customer.build_readiness_values(customer=values, addresses=[], contacts=[])

        self.assertEqual(missing_reason["delivery_readiness"], customer.MISSING)

        values["no_delivery_reason"] = "No physical goods are delivered."
        not_applicable = customer.build_readiness_values(customer=values, addresses=[], contacts=[])

        self.assertEqual(not_applicable["delivery_readiness"], customer.NOT_APPLICABLE)


class TestCustomerOnboardingValidation(UnitTestCase):
    def test_address_and_contact_deletions_refresh_readiness_after_database_delete(self) -> None:
        self.assertIn("after_delete", hooks.doc_events["Address"])
        self.assertIn("after_delete", hooks.doc_events["Contact"])

    @patch.object(customer, "_refresh_customer_readiness_for_names")
    def test_unlinking_address_or_contact_refreshes_the_previous_customer(
        self, mocked_refresh: MagicMock
    ) -> None:
        previous = FakeDocument(
            {"links": [FakeDocument({"link_doctype": "Customer", "link_name": "CD-UNLINK-001"})]}
        )
        doc = FakeDocument({"links": []}, before=previous)

        customer.refresh_linked_customer_readiness(cast(Document, doc))

        mocked_refresh.assert_called_once_with(["CD-UNLINK-001"])

    @patch.object(customer, "refresh_customer_readiness")
    @patch.object(customer.frappe.db, "set_value")
    @patch.object(customer.frappe, "rename_doc")
    def test_customer_code_rename_preserves_business_customer_name(
        self,
        mocked_rename_doc: MagicMock,
        mocked_set_value: MagicMock,
        mocked_refresh: MagicMock,
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
        mocked_refresh.assert_called_once_with("CD-001")

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
            {
                "customer_group": "Commercial",
                "disabled": 0,
                "customer_onboarding_state": customer_onboarding.CUSTOMER_ACTIVE_STATE,
            },
        )

    @patch.object(customer, "_validate_accounting_review")
    def test_accounting_reviewer_can_return_incomplete_customer_for_correction(
        self, mocked_review: MagicMock
    ) -> None:
        previous = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.PENDING_ACCOUNTING_STATE,
                "correction_reason": "Earlier reason",
            }
        )
        doc = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.CUSTOMER_REQUEST_STATE,
                "correction_reason": "Earlier reason",
            },
            before=previous,
        )

        customer._validate_onboarding_transition(
            cast(Document, doc),
            cast(Document, previous),
            {"tax_invoice_readiness": customer.READY, "delivery_readiness": customer.READY},
        )

        mocked_review.assert_not_called()
        self.assertEqual(doc.disabled, 1)

    def test_resubmitting_for_duplicate_verification_clears_prior_correction_reason(self) -> None:
        previous = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.CUSTOMER_REQUEST_STATE,
                "correction_reason": "Correct the delivery address",
            }
        )
        doc = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.PENDING_DUPLICATE_STATE,
                "correction_reason": "Correct the delivery address",
            },
            before=previous,
        )

        customer._validate_onboarding_transition(
            cast(Document, doc),
            cast(Document, previous),
            {"tax_invoice_readiness": customer.MISSING, "delivery_readiness": customer.MISSING},
        )

        self.assertIsNone(doc.correction_reason)

    def test_activation_is_blocked_until_tax_and_delivery_are_ready(self) -> None:
        doc = FakeDocument(
            {"customer_onboarding_state": customer_onboarding.CUSTOMER_ACTIVE_STATE},
            before=FakeDocument({"customer_onboarding_state": customer_onboarding.PENDING_ACCOUNTING_STATE}),
        )

        with self.assertRaises(frappe.ValidationError):
            customer._validate_onboarding_transition(
                cast(Document, doc),
                cast(Document, doc.get_doc_before_save()),
                {"tax_invoice_readiness": customer.MISSING, "delivery_readiness": customer.READY},
            )


class TestItemSearch(UnitTestCase):
    @patch.object(item.frappe.db, "sql", return_value=[("CD-ITEM-001", "CD Item", 4)])
    def test_item_search_matches_the_retained_item_code_without_mapping_tables(
        self, mocked_sql: MagicMock
    ) -> None:
        with patch.object(item.frappe, "has_permission"):
            result = item.get_item_with_stock("Item", "EXT-ITEM", "name", 0, 20)

        query, params = _item_search_sql_call(mocked_sql)
        self.assertEqual(result, [("CD-ITEM-001", "CD Item", "4 QTY.")])
        self.assertIn("i.dksh_item_code LIKE %(txt)s", query)
        self.assertIn("EXISTS (", query)
        self.assertNotIn("`tabPartner Item Mapping`", query)
        self.assertNotIn("Item Mapping`", query)
        self.assertNotIn("company", params)

    @patch.object(item.frappe.db, "sql")
    def test_company_filter_does_not_change_standard_item_results(self, mocked_sql: MagicMock) -> None:
        mocked_sql.return_value = [("CD-ITEM-001", "CD Item", 4)]

        with patch.object(item.frappe, "has_permission"):
            item.get_item_with_stock("Item", "CD-ITEM", "name", 0, 20, filters={"company": "CD Company"})

        _query, params = _item_search_sql_call(mocked_sql)
        self.assertNotIn("company", params)


class TestCustomerCreditLimit(UnitTestCase):
    def test_active_customer_is_eligible_without_a_channel_field(self) -> None:
        customer_doc = FakeDocument(
            {
                "name": "CD-0001",
                "customer_onboarding_state": customer_onboarding.CUSTOMER_ACTIVE_STATE,
            }
        )

        result = customer_credit_request._get_eligible_customer(
            "CD-0001", customer=cast(Document, customer_doc)
        )

        self.assertIs(result, customer_doc)

    def test_approved_credit_request_updates_the_cd_company_limit(self) -> None:
        customer_doc = FakeDocument(
            {"credit_limits": [FakeDocument({"company": "CD Company", "credit_limit": 1000})]}
        )

        customer_credit_request._set_customer_credit_limit(cast(Document, customer_doc), "CD Company", 5000)

        credit_limits = cast(list[FakeDocument], customer_doc["credit_limits"])
        self.assertEqual(credit_limits[0].credit_limit, 5000)
        self.assertEqual(credit_limits[0].bypass_credit_limit_check, 0)
