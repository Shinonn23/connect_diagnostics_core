# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.report.customer_borrow_tracking import (
    customer_borrow_tracking as report,
)


class TestCustomerBorrowTracking(UnitTestCase):
    def test_each_delivery_has_its_own_age_and_optional_due_date(self) -> None:
        rows = [
            {"posting_date": "2026-10-01", "expected_return_date": "2026-10-02", "qty": 3},
            {"posting_date": "2026-10-03", "expected_return_date": None, "qty": 2},
            {"posting_date": "2026-10-04", "expected_return_date": "2026-10-10", "qty": 1},
        ]
        with (
            patch.object(report.frappe, "has_permission") as permission,
            patch.object(report, "_get_data", return_value=rows),
            patch.object(report, "today", return_value="2026-10-04"),
        ):
            columns, data, message = report.execute({"customer": "_Test Borrower"})
        self.assertEqual([row["days_borrowed"] for row in data], [3, 1, 0])
        self.assertEqual([row["days_overdue"] for row in data], [2, None, 0])
        self.assertEqual([row["qty"] for row in data], [3, 2, 1])
        self.assertEqual(permission.call_count, 2)
        permission.assert_any_call("Material Request", "read", throw=True)
        permission.assert_any_call("Stock Entry", "read", throw=True)
        self.assertTrue(message)
        self.assertIn("serial_and_batch_bundle", {column["fieldname"] for column in columns})

    def test_denied_stock_entry_access_stops_before_query(self) -> None:
        with (
            patch.object(report.frappe, "has_permission", side_effect=[True, frappe.PermissionError]),
            patch.object(report, "_get_data") as query,
        ):
            with self.assertRaises(frappe.PermissionError):
                report.execute()
        query.assert_not_called()

    def test_query_intersects_parent_permissions_and_binds_user_filters(self) -> None:
        user_value = "_Test Customer' OR 1=1 --"
        with (
            patch.object(
                report,
                "get_match_cond",
                side_effect=[
                    " AND (`tabMaterial Request`.owner = 'allowed-request-owner')",
                    " AND (`tabStock Entry`.owner = 'allowed-entry-owner')",
                ],
            ) as matches,
            patch.object(report.frappe.db, "sql", return_value=[]) as query,
        ):
            self.assertEqual(report._get_data({"customer": user_value}), [])
        self.assertEqual([call.args[0] for call in matches.call_args_list], ["Material Request", "Stock Entry"])
        sql, params = query.call_args.args
        self.assertIn("allowed-request-owner", sql)
        self.assertIn("allowed-entry-owner", sql)
        self.assertNotIn(user_value, sql)
        self.assertEqual(params, {"customer": user_value})
        self.assertIn("`tabStock Entry`.docstatus = 1", sql)
        self.assertIn("`tabMaterial Request`.docstatus = 1", sql)
        self.assertIn("detail.material_request = `tabMaterial Request`.name", sql)
        self.assertIn("request_item.name = detail.material_request_item", sql)
        self.assertIn("detail.t_warehouse = `tabMaterial Request`.borrow_warehouse", sql)

    def test_filter_shape_and_allowlist(self) -> None:
        for filters in ({"unexpected": "value"}, {"customer": ["a", "b"]}):
            with self.subTest(filters=filters), self.assertRaises(frappe.ValidationError):
                report._validate_filters(filters)
        self.assertEqual(report._validate_filters({"customer": "", "employee": None}), {})
