# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.borrowed_item_resolution.borrowed_item_resolution import (
    BorrowedItemResolution,
)


class TestBorrowedItemResolution(UnitTestCase):
    def test_settlement_requires_customer_demo_or_loan(self) -> None:
        doc = MagicMock()
        doc.material_request = "MR-1"
        invoice = frappe._dict(docstatus=1, status="Paid", outstanding_amount=0, customer="CUST-1")

        with patch.object(
            frappe.db,
            "get_value",
            side_effect=["Employee Borrow", invoice, "CUST-1"],
        ):
            with self.assertRaises(frappe.ValidationError):
                BorrowedItemResolution._validate_settlement(doc)

    def test_missing_write_off_must_use_borrow_warehouse(self) -> None:
        doc = MagicMock()
        doc.write_off_reason = "Missing"
        doc.items = [frappe._dict(idx=1, asset=None, warehouse="QA - TC")]
        doc._borrow_warehouse.return_value = "Borrow - TC"

        with self.assertRaises(frappe.ValidationError):
            BorrowedItemResolution._validate_write_off(doc)

    def test_damaged_write_off_requires_a_return_line(self) -> None:
        doc = MagicMock()
        row = frappe._dict(idx=1, against_dispatch_transfer=None, asset=None)

        with self.assertRaises(frappe.ValidationError):
            BorrowedItemResolution._validate_damaged_return(doc, row)
