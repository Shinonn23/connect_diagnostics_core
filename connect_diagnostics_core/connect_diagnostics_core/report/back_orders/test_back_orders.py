# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from connect_diagnostics_core.connect_diagnostics_core.report.back_orders import back_orders

REFERENCE_DATE = "2026-07-16"
TEST_COMPANY = "_Test Back Orders Company"
TEST_CUSTOMER = "_Test Back Orders Customer"
TEST_DEPARTMENT = "_Test Back Orders Department"
TEST_ITEM = "_Test Back Orders Item"
TEST_ITEM_SECOND = "_Test Back Orders Item 2"
TEST_TERRITORY = "_Test Back Orders Territory"
TEST_WAREHOUSE = "_Test Back Orders Warehouse"


class TestBackOrders(IntegrationTestCase):
    partial_order: SalesOrder
    same_date_order: SalesOrder
    pending_order: SalesOrder
    future_order: SalesOrder
    fully_delivered_order: SalesOrder
    draft_order: SalesOrder
    cancelled_order: SalesOrder
    on_hold_order: SalesOrder
    closed_order: SalesOrder
    completed_order: SalesOrder
    skip_delivery_note_order: SalesOrder

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.partial_order = cls._make_order(
            "Partial", add_days(REFERENCE_DATE, -5), delivered_qty=4
        )
        cls.same_date_order = cls._make_order("Alpha", REFERENCE_DATE, include_second_item=True)
        cls.pending_order = cls._make_order("Pending", REFERENCE_DATE)
        cls.future_order = cls._make_order("Future", add_days(REFERENCE_DATE, 5))
        cls.fully_delivered_order = cls._make_order(
            "Fully Delivered", add_days(REFERENCE_DATE, 1), delivered_qty=10
        )
        cls.draft_order = cls._make_order("Draft", add_days(REFERENCE_DATE, 2), docstatus=0)
        cls.cancelled_order = cls._make_order(
            "Cancelled", add_days(REFERENCE_DATE, 2), docstatus=2, status="Cancelled"
        )
        cls.on_hold_order = cls._make_order(
            "On Hold", add_days(REFERENCE_DATE, 2), status="On Hold"
        )
        cls.closed_order = cls._make_order("Closed", add_days(REFERENCE_DATE, 2), status="Closed")
        cls.completed_order = cls._make_order(
            "Completed", add_days(REFERENCE_DATE, 2), status="Completed"
        )
        cls.skip_delivery_note_order = cls._make_order(
            "Skip Delivery Note", add_days(REFERENCE_DATE, 2), skip_delivery_note=True
        )

    @classmethod
    def _make_order(
        cls,
        label: str,
        delivery_date: str | date,
        *,
        delivered_qty: float = 0,
        docstatus: int = 1,
        status: str = "To Deliver and Bill",
        skip_delivery_note: bool = False,
        include_second_item: bool = False,
    ) -> SalesOrder:
        items: list[dict[str, Any]] = [
            {
                "doctype": "Sales Order Item",
                "name": f"_Test Back Orders {label} Item 1",
                "docstatus": docstatus,
                "idx": 1,
                "delivery_date": delivery_date,
                "item_code": TEST_ITEM,
                "item_name": TEST_ITEM,
                "warehouse": TEST_WAREHOUSE,
                "department": TEST_DEPARTMENT,
                "territory": TEST_TERRITORY,
                "qty": 10,
                "delivered_qty": delivered_qty,
                "uom": "Nos",
                "net_rate": 25.5,
            }
        ]
        if include_second_item:
            items.append(
                {
                    **items[0],
                    "name": f"_Test Back Orders {label} Item 2",
                    "idx": 2,
                    "item_code": TEST_ITEM_SECOND,
                    "item_name": TEST_ITEM_SECOND,
                }
            )

        order = cast(
            SalesOrder,
            frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "name": f"_Test Back Orders {label}",
                    "docstatus": docstatus,
                    "status": status,
                    "transaction_date": add_days(delivery_date, -2),
                    "delivery_date": delivery_date,
                    "company": TEST_COMPANY,
                    "customer": TEST_CUSTOMER,
                    "customer_name": TEST_CUSTOMER,
                    "currency": "THB",
                    "skip_delivery_note": skip_delivery_note,
                    "po_no": f"_Test Back Orders {label}",
                    "items": items,
                }
            ),
        )
        order.db_insert()
        for item in order.items:
            item.db_insert()
        return order

    def _run_report(self, **filters: Any) -> list[back_orders.ReportRow]:
        report_filters = {"company": TEST_COMPANY, **filters}
        with patch.object(back_orders, "today", return_value=REFERENCE_DATE):
            return back_orders.execute(report_filters)[1]

    def test_pending_and_partially_delivered_items_have_correct_values(self) -> None:
        pending_rows = self._run_report(sales_order=self.pending_order.name)
        partial_rows = self._run_report(sales_order=self.partial_order.name)

        self.assertEqual(len(pending_rows), 1)
        self.assertEqual(pending_rows[0].qty, 10)
        self.assertEqual(pending_rows[0].delivered_qty, 0)
        self.assertEqual(pending_rows[0].pending_qty, 10)
        self.assertAlmostEqual(cast(float, pending_rows[0].pending_amount), 255.0)

        self.assertEqual(len(partial_rows), 1)
        partial_row = partial_rows[0]
        self.assertEqual(partial_row.sales_order, self.partial_order.name)
        self.assertEqual(partial_row.order_date, getdate(self.partial_order.transaction_date))
        self.assertEqual(partial_row.customer, self.partial_order.customer)
        self.assertEqual(partial_row.customer_name, self.partial_order.customer_name)
        self.assertEqual(
            partial_row.delivery_date,
            getdate(self.partial_order.items[0].delivery_date),
        )
        self.assertEqual(partial_row.item_code, TEST_ITEM)
        self.assertEqual(partial_row.item_name, TEST_ITEM)
        self.assertEqual(partial_row.warehouse, TEST_WAREHOUSE)
        self.assertEqual(partial_row.accounting_department, TEST_DEPARTMENT)
        self.assertEqual(partial_row.territory, TEST_TERRITORY)
        self.assertEqual(partial_row.qty, 10)
        self.assertEqual(partial_row.delivered_qty, 4)
        self.assertEqual(partial_row.pending_qty, 6)
        self.assertEqual(partial_row.uom, "Nos")
        self.assertAlmostEqual(cast(float, partial_row.net_rate), 25.5)
        self.assertAlmostEqual(cast(float, partial_row.pending_amount), 153.0)
        self.assertEqual(partial_row.currency, self.partial_order.currency)
        self.assertEqual(partial_row.company, TEST_COMPANY)

    def test_fully_delivered_item_is_excluded(self) -> None:
        self.assertEqual(
            self._run_report(sales_order=self.fully_delivered_order.name),
            [],
        )

    def test_ineligible_order_states_and_skip_delivery_note_are_excluded(self) -> None:
        excluded_orders = {
            "draft": self.draft_order,
            "cancelled": self.cancelled_order,
            "on hold": self.on_hold_order,
            "closed": self.closed_order,
            "completed": self.completed_order,
            "skip delivery note": self.skip_delivery_note_order,
        }
        for state, order in excluded_orders.items():
            with self.subTest(state=state):
                self.assertEqual(self._run_report(sales_order=order.name), [])

    def test_filters_limit_rows_by_each_supported_dimension(self) -> None:
        partial_delivery_date = cast(str | date, self.partial_order.items[0].delivery_date)
        correct_filters = {
            "from_delivery_date": add_days(partial_delivery_date, -1),
            "to_delivery_date": add_days(partial_delivery_date, 1),
            "customer": self.partial_order.customer,
            "item": TEST_ITEM,
            "warehouse": TEST_WAREHOUSE,
            "accounting_department": TEST_DEPARTMENT,
            "territory": TEST_TERRITORY,
        }
        for fieldname, value in correct_filters.items():
            with self.subTest(fieldname=fieldname, matches=True):
                rows = self._run_report(
                    sales_order=self.partial_order.name,
                    **{fieldname: value},
                )
                self.assertEqual([row.sales_order for row in rows], [self.partial_order.name])

        wrong_filters = {
            "from_delivery_date": add_days(partial_delivery_date, 1),
            "to_delivery_date": add_days(partial_delivery_date, -1),
            "customer": "_Test Missing Back Orders Customer",
            "item": "_Test Missing Back Orders Item",
            "warehouse": "_Test Missing Back Orders Warehouse",
            "accounting_department": "_Test Missing Back Orders Department",
            "territory": "_Test Missing Back Orders Territory",
        }
        for fieldname, value in wrong_filters.items():
            with self.subTest(fieldname=fieldname, matches=False):
                rows = self._run_report(
                    sales_order=self.partial_order.name,
                    **{fieldname: value},
                )
                self.assertEqual(rows, [])

        self.assertEqual(
            [row.sales_order for row in self._run_report(sales_order=self.partial_order.name)],
            [self.partial_order.name],
        )
        self.assertEqual(
            self._run_report(company="_Test Missing Back Orders Company", sales_order=self.partial_order.name),
            [],
        )

    def test_delivery_date_range_validation(self) -> None:
        with self.assertRaisesRegex(
            frappe.ValidationError,
            "From Delivery Date cannot be greater than To Delivery Date",
        ):
            back_orders.execute(
                {
                    "company": TEST_COMPANY,
                    "from_delivery_date": add_days(REFERENCE_DATE, 1),
                    "to_delivery_date": REFERENCE_DATE,
                }
            )

    def test_company_is_required(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "Company is required"):
            back_orders.execute({})

    def test_overdue_days_are_positive_only_for_past_delivery_dates(self) -> None:
        past_row = self._run_report(sales_order=self.partial_order.name)[0]
        today_row = self._run_report(sales_order=self.pending_order.name)[0]
        future_row = self._run_report(sales_order=self.future_order.name)[0]

        self.assertEqual(past_row.overdue_days, 5)
        self.assertEqual(today_row.overdue_days, 0)
        self.assertEqual(future_row.overdue_days, 0)

    def test_rows_are_sorted_by_delivery_date_then_sales_order_and_item_index(self) -> None:
        rows = self._run_report()
        self.assertEqual(
            [(row.sales_order, row.item_code) for row in rows],
            [
                (self.partial_order.name, TEST_ITEM),
                (self.same_date_order.name, TEST_ITEM),
                (self.same_date_order.name, TEST_ITEM_SECOND),
                (self.pending_order.name, TEST_ITEM),
                (self.future_order.name, TEST_ITEM),
            ],
        )

    def test_report_metadata_has_no_total_and_expected_access(self) -> None:
        metadata = cast(
            dict[str, Any],
            json.loads(Path(__file__).with_name("back_orders.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(metadata["add_total_row"], 0)
        self.assertEqual(metadata["ref_doctype"], "Sales Order")
        self.assertEqual(metadata["module"], "Connect Diagnostics Core")
        self.assertEqual(
            {role["role"] for role in metadata["roles"]},
            {"Sales User", "Sales Manager", "Stock User", "Stock Manager"},
        )
