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
from connect_diagnostics_core.api.erpnext import customer, customer_credit_request, dksh_item_mapping, item
from connect_diagnostics_core.config.dksh import DKSH_COMPANY
from connect_diagnostics_core.connect_diagnostics_core.doctype.partner_item_mapping import (
    partner_item_mapping,
)
from connect_diagnostics_core.naming import customer as customer_naming
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
            {"name": "DKSH-001", "customer_name": "Example Hospital"},
        )
        doc.flags = frappe._dict(customer_code_rename_to="CD-001")

        customer.on_update(cast(Document, doc))

        mocked_rename_doc.assert_called_once_with(
            "Customer", "DKSH-001", "CD-001", force=True, show_alert=False
        )
        mocked_set_value.assert_called_once_with(
            "Customer", "CD-001", "customer_name", "Example Hospital", update_modified=False
        )
        mocked_refresh.assert_called_once_with("CD-001")

    def test_manual_customer_code_becomes_document_name(self) -> None:
        doc = FakeDocument({"customer_code": "  DKSH-0001  ", "naming_series": "", "name": ""})

        customer_naming.prepare_customer_naming(doc)

        customer_naming.set_customer_code(doc)

        self.assertEqual(doc.customer_code, "DKSH-0001")
        self.assertEqual(doc.name, "DKSH-0001")
        self.assertEqual(doc.naming_series, "")

    def test_legacy_customer_series_function_is_retained_during_deprecation(self) -> None:
        self.assertEqual(
            customer_naming.series_for_customer(
                SimpleNamespace(customer_type="Company", customer_group="Government")
            ),
            "4H.###",
        )

    def test_draft_dksh_customer_code_can_change_before_rename(self) -> None:
        doc = FakeDocument(
            {
                "customer_channel": customer.CHANNEL_DKSH,
                "customer_code": "DKSH-NEW",
                "dksh_sap_customer_code": "",
                "name": "DKSH-OLD",
            }
        )

        customer._validate_customer_channel(cast(Document, doc))

        self.assertEqual(doc.customer_code, "DKSH-NEW")

    def test_cd_customer_does_not_keep_a_dksh_sap_customer_code(self) -> None:
        doc = FakeDocument(
            {
                "customer_channel": customer.CHANNEL_CD,
                "dksh_sap_customer_code": "SAP-OLD",
            }
        )

        customer._validate_customer_channel(cast(Document, doc))

        self.assertIsNone(doc.dksh_sap_customer_code)

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

    @patch.object(customer, "_validate_dksh_sap_setup")
    def test_dksh_admin_can_return_missing_sap_customer_code_for_correction(
        self, mocked_setup: MagicMock
    ) -> None:
        previous = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.PENDING_DKSH_SAP_STATE,
                "correction_reason": "Earlier reason",
            }
        )
        doc = FakeDocument(
            {
                "customer_onboarding_state": customer_onboarding.CUSTOMER_REQUEST_STATE,
                "correction_reason": "SAP code is not available",
            },
            before=previous,
        )

        customer._validate_onboarding_transition(
            cast(Document, doc),
            cast(Document, previous),
            {"tax_invoice_readiness": customer.READY, "delivery_readiness": customer.READY},
        )

        mocked_setup.assert_not_called()
        self.assertEqual(doc.disabled, 1)

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


class TestPartnerItemMappingValidation(UnitTestCase):
    @patch.object(partner_item_mapping.frappe.db, "add_unique")
    def test_partner_mapping_doctype_has_a_database_unique_constraint(
        self, mocked_add_unique: MagicMock
    ) -> None:
        partner_item_mapping.on_doctype_update()

        mocked_add_unique.assert_called_once_with(
            "Partner Item Mapping",
            ["parenttype", "partner_company", "external_item_code"],
            constraint_name="unique_partner_item_mapping_code",
        )

    def test_dksh_item_channel_is_allowed_while_its_master_mapping_is_pending(self) -> None:
        doc = FakeDocument(
            {
                "item_channel": item.CHANNEL_DKSH,
                "item_code": "DKSH-ITEM-001",
                "stock_uom": "Nos",
            }
        )

        item.validate(cast(Document, doc))

        self.assertEqual(doc.has_dksh_code, 1)
        self.assertEqual(doc.item_code_is_dksh_code, 1)

    @patch.object(item.frappe.db, "sql", return_value=[("DKSH-ITEM-001", "DKSH Item", 4)])
    def test_item_search_uses_exists_for_master_code_searches(self, mocked_sql: MagicMock) -> None:
        with patch.object(item.frappe, "has_permission"):
            result = item.get_item_with_stock("Item", "DKSH-ITEM", "name", 0, 20)

        query, params = _item_search_sql_call(mocked_sql)
        self.assertEqual(result, [("DKSH-ITEM-001", "DKSH Item", "4 QTY.")])
        self.assertIn("EXISTS (", query)
        self.assertIn("`tabDKSH Item Mapping`", query)
        self.assertNotIn("`tabPartner Item Mapping`", query)
        self.assertEqual(params["dksh_company"], "")

    @patch.object(item.frappe.db, "sql", return_value=[("DKSH-ITEM-001", "DKSH Item", 4)])
    def test_dksh_company_item_search_requires_an_active_dksh_mapping(self, mocked_sql: MagicMock) -> None:
        with patch.object(item.frappe, "has_permission"):
            result = item.get_item_with_stock(
                "Item", "DKSH-ITEM", "name", 0, 20, filters={"company": DKSH_COMPANY}
            )

        query, params = _item_search_sql_call(mocked_sql)
        self.assertEqual(result, [("DKSH-ITEM-001", "DKSH Item", "4 QTY.")])
        self.assertIn("mapping.mapping_state = %(active_mapping_state)s", query)
        self.assertIn("IFNULL(mapping.active, 0) = 1", query)
        self.assertEqual(params["dksh_company"], DKSH_COMPANY)

    @patch.object(item.frappe.db, "sql")
    def test_non_dksh_company_item_search_keeps_standard_item_results(self, mocked_sql: MagicMock) -> None:
        mocked_sql.side_effect = [[("Item",)], []]

        with patch.object(item.frappe, "has_permission"):
            item.get_item_with_stock("Item", "CD-ITEM", "name", 0, 20, filters={"company": "CD Company"})

        _query, params = _item_search_sql_call(mocked_sql)
        self.assertEqual(params["dksh_company"], "")


class TestCustomerCreditLimit(UnitTestCase):
    def test_approved_credit_request_updates_the_cd_company_limit(self) -> None:
        customer_doc = FakeDocument(
            {"credit_limits": [FakeDocument({"company": "CD Company", "credit_limit": 1000})]}
        )

        customer_credit_request._set_customer_credit_limit(cast(Document, customer_doc), "CD Company", 5000)

        credit_limits = cast(list[FakeDocument], customer_doc["credit_limits"])
        self.assertEqual(credit_limits[0].credit_limit, 5000)
        self.assertEqual(credit_limits[0].bypass_credit_limit_check, 0)
