# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.outstanding_borrowed_items import (
    outstanding_borrowed_items,
)


class TestOutstandingBorrowedItems(UnitTestCase):
    @patch.object(outstanding_borrowed_items.frappe.db, "sql", return_value=[])
    def test_query_subtracts_only_delivered_returns(self, sql: MagicMock) -> None:
        outstanding_borrowed_items.get_outstanding_rows(
            {"company": "_Test Company", "as_of_date": "2026-09-07"}
        )

        query = sql.call_args.args[0]
        self.assertIn("d.delivery_status = 'Delivered'", query)
        self.assertIn("d.dispatch_type = 'Return'", query)
        self.assertIn("d.dispatch_type = 'Outbound'", query)
        self.assertNotIn("dispatch_type = 'Retry'", query)

    @patch.object(outstanding_borrowed_items.frappe.db, "sql", return_value=[])
    def test_filters_are_parameterized(self, sql: MagicMock) -> None:
        outstanding_borrowed_items.get_outstanding_rows(
            {
                "company": "_Test Company",
                "as_of_date": "2026-09-07",
                "request_usage": "Customer Demo",
                "material_request": "MR-1",
                "overdue_only": 1,
            }
        )

        params = sql.call_args.args[1]
        self.assertEqual(params["request_usage"], "Customer Demo")
        self.assertEqual(params["material_request"], "MR-1")

    def test_execute_requires_company(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            outstanding_borrowed_items.execute({})

    def test_columns_distinguish_asset_and_stock(self) -> None:
        fieldnames = {column["fieldname"] for column in outstanding_borrowed_items.get_columns()}

        self.assertIn("material_request_item", fieldnames)
        self.assertIn("asset", fieldnames)
        self.assertIn("outstanding_qty", fieldnames)
