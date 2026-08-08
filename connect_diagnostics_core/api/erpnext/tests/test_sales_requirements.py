# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_requirements
from connect_diagnostics_core.setup.sales_requirements import OVERRIDE_ROLE

CUSTOMER = "CUST-0001"


class FakeDocument(frappe._dict):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        super().__init__(values or {})
        self.flags = frappe._dict()

    def set(self, key: str, value: Any) -> None:
        self[key] = value


def sales_order(**overrides: Any) -> FakeDocument:
    return FakeDocument(
        {
            "doctype": "Sales Order",
            "name": "SAL-ORD-0001",
            "customer": CUSTOMER,
            "customer_name": "Bangkok Hospital",
            "items": [FakeDocument({"prevdoc_docname": ""})],
            **overrides,
        }
    )


def sales_invoice(**overrides: Any) -> FakeDocument:
    return FakeDocument(
        {
            "doctype": "Sales Invoice",
            "name": "ACC-SINV-0001",
            "customer": CUSTOMER,
            "customer_name": "Bangkok Hospital",
            "source_purchase_orders": [],
            **overrides,
        }
    )


class RequirementHarness(UnitTestCase):
    """Drive the gate with controllable Customer requirements and roles."""

    def setUp(self) -> None:
        super().setUp()
        self.requirements: dict[str, int] = {
            "quotation_required": 0,
            "source_purchase_order_copy_required": 0,
        }
        self.roles: list[str] = ["Sales User"]
        self.messages: list[Any] = []

        patchers = (
            patch.object(
                sales_requirements,
                "get_customer_requirements",
                side_effect=lambda customer: dict(self.requirements),
            ),
            patch.object(sales_requirements.frappe, "get_roles", side_effect=lambda: list(self.roles)),
            patch.object(
                sales_requirements.frappe,
                "msgprint",
                side_effect=lambda *args, **kwargs: self.messages.append(args),
            ),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def require(self, **flags: int) -> None:
        self.requirements.update(flags)


class TestSalesOrderRequirements(RequirementHarness):
    def test_nothing_is_required_by_default(self) -> None:
        self.assertEqual(sales_requirements.evaluate_sales_order(sales_order()), [])

    def test_an_order_without_a_quotation_is_a_gap(self) -> None:
        self.require(quotation_required=1)

        self.assertTrue(sales_requirements.evaluate_sales_order(sales_order()))

    def test_a_quoted_order_has_no_gap(self) -> None:
        self.require(quotation_required=1)
        doc = sales_order(items=[FakeDocument({"prevdoc_docname": "SAL-QTN-0001"})])

        self.assertEqual(sales_requirements.evaluate_sales_order(doc), [])

    def test_any_quoted_line_satisfies_the_requirement(self) -> None:
        self.require(quotation_required=1)
        doc = sales_order(
            items=[
                FakeDocument({"prevdoc_docname": ""}),
                FakeDocument({"prevdoc_docname": "SAL-QTN-0001"}),
            ]
        )

        self.assertEqual(sales_requirements.evaluate_sales_order(doc), [])


class TestSalesInvoiceRequirements(RequirementHarness):
    def test_nothing_is_required_by_default(self) -> None:
        self.assertEqual(sales_requirements.evaluate_sales_invoice(sales_invoice()), [])

    def test_an_invoice_without_the_source_order_is_a_gap(self) -> None:
        self.require(source_purchase_order_copy_required=1)

        self.assertTrue(sales_requirements.evaluate_sales_invoice(sales_invoice()))

    def test_a_linked_purchase_order_row_satisfies_the_requirement(self) -> None:
        self.require(source_purchase_order_copy_required=1)
        doc = sales_invoice(
            source_purchase_orders=[FakeDocument({"purchase_order": "PUR-ORD-0001", "copies": 1})]
        )

        self.assertEqual(sales_requirements.evaluate_sales_invoice(doc), [])

    def test_an_attached_file_row_satisfies_the_requirement(self) -> None:
        self.require(source_purchase_order_copy_required=1)
        doc = sales_invoice(
            source_purchase_orders=[FakeDocument({"purchase_order_file": "/files/legacy-po.pdf"})]
        )

        self.assertEqual(sales_requirements.evaluate_sales_invoice(doc), [])

    def test_a_second_purchase_order_row_is_allowed(self) -> None:
        self.require(source_purchase_order_copy_required=1)
        doc = sales_invoice(
            source_purchase_orders=[
                FakeDocument({"purchase_order": "PUR-ORD-0001", "copies": 2}),
                FakeDocument({"purchase_order": "PUR-ORD-0002", "copies": 1}),
            ]
        )

        self.assertEqual(sales_requirements.evaluate_sales_invoice(doc), [])

    def test_rows_with_neither_an_order_nor_a_file_are_a_gap(self) -> None:
        self.require(source_purchase_order_copy_required=1)
        doc = sales_invoice(source_purchase_orders=[FakeDocument({"copies": 1})])

        self.assertTrue(sales_requirements.evaluate_sales_invoice(doc))


class TestGate(RequirementHarness):
    def test_a_document_meeting_its_requirements_saves(self) -> None:
        sales_requirements.validate(sales_order())  # ty: ignore[invalid-argument-type] - test double

    def test_a_stale_override_reason_is_cleared_once_the_gap_closes(self) -> None:
        doc = sales_order(requirement_override_reason="urgent")

        sales_requirements.validate(doc)  # ty: ignore[invalid-argument-type] - test double

        self.assertIsNone(doc["requirement_override_reason"])

    def test_a_user_without_the_role_is_blocked(self) -> None:
        self.require(quotation_required=1)

        with self.assertRaises(frappe.ValidationError):
            sales_requirements.validate(sales_order())  # ty: ignore[invalid-argument-type] - test double

    def test_the_role_alone_does_not_bypass_the_gate(self) -> None:
        self.require(quotation_required=1)
        self.roles.append(OVERRIDE_ROLE)

        with self.assertRaises(frappe.ValidationError):
            sales_requirements.validate(sales_order())  # ty: ignore[invalid-argument-type] - test double

    def test_the_role_with_a_reason_proceeds_and_warns(self) -> None:
        self.require(quotation_required=1)
        self.roles.append(OVERRIDE_ROLE)
        doc = sales_order(requirement_override_reason="Verbal order confirmed by the head nurse")

        sales_requirements.validate(doc)  # ty: ignore[invalid-argument-type] - test double

        self.assertEqual(len(self.messages), 1)
        self.assertEqual(
            doc["requirement_override_reason"],
            "Verbal order confirmed by the head nurse",
        )

    def test_an_ungated_doctype_is_untouched(self) -> None:
        self.require(quotation_required=1, source_purchase_order_copy_required=1)
        doc = FakeDocument({"doctype": "Delivery Note", "customer": CUSTOMER})

        self.assertEqual(sales_requirements.evaluate(doc), [])


class TestRequirementLookup(UnitTestCase):
    def test_no_customers_needs_no_query(self) -> None:
        with patch.object(sales_requirements.frappe, "get_all") as mocked_get_all:
            self.assertEqual(sales_requirements.get_customer_requirements_map([]), {})

        mocked_get_all.assert_not_called()

    def test_a_schema_without_the_fields_requires_nothing(self) -> None:
        with patch.object(sales_requirements, "_available_requirement_fields", return_value=[]):
            requirements = sales_requirements.get_customer_requirements_map([CUSTOMER])

        self.assertEqual(
            requirements[CUSTOMER],
            {"quotation_required": 0, "source_purchase_order_copy_required": 0},
        )

    def test_many_customers_are_read_in_one_query(self) -> None:
        rows = [
            {"name": CUSTOMER, "quotation_required": 1, "source_purchase_order_copy_required": 0},
            {"name": "CUST-0002", "quotation_required": 0, "source_purchase_order_copy_required": 1},
        ]
        with (
            patch.object(
                sales_requirements,
                "_available_requirement_fields",
                return_value=list(sales_requirements.REQUIREMENT_FIELDS),
            ),
            patch.object(sales_requirements.frappe, "get_all", return_value=rows) as mocked_get_all,
        ):
            requirements = sales_requirements.get_customer_requirements_map([CUSTOMER, "CUST-0002", CUSTOMER])

        self.assertEqual(mocked_get_all.call_count, 1)
        self.assertEqual(requirements[CUSTOMER]["quotation_required"], 1)
        self.assertEqual(requirements["CUST-0002"]["source_purchase_order_copy_required"], 1)

    def test_a_customer_with_no_row_requires_nothing(self) -> None:
        with (
            patch.object(
                sales_requirements,
                "_available_requirement_fields",
                return_value=list(sales_requirements.REQUIREMENT_FIELDS),
            ),
            patch.object(sales_requirements.frappe, "get_all", return_value=[]),
        ):
            requirements = sales_requirements.get_customer_requirements_map([CUSTOMER])

        self.assertEqual(requirements[CUSTOMER]["quotation_required"], 0)
