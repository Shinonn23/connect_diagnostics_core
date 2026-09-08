# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.borrowed_item_resolution.borrowed_item_resolution import (
    BorrowedItemResolution,
)
from connect_diagnostics_core.connect_diagnostics_stock.report.outstanding_borrowed_items import (
    outstanding_borrowed_items,
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

    @patch.object(
        outstanding_borrowed_items,
        "get_outstanding_rows",
        return_value=[frappe._dict(material_request_item="MRI-1", asset=None, outstanding_qty=2)],
    )
    def test_resolution_cannot_exceed_current_outstanding_quantity(self, _outstanding: MagicMock) -> None:
        doc = frappe._dict(
            company="_Test Company",
            material_request="MR-1",
            items=[frappe._dict(idx=1, material_request_item="MRI-1", asset=None, qty=3)],
        )

        with self.assertRaises(frappe.ValidationError):
            BorrowedItemResolution._validate_outstanding_quantities(cast(BorrowedItemResolution, doc))

    @patch.object(
        outstanding_borrowed_items,
        "get_outstanding_rows",
        return_value=[frappe._dict(material_request_item="MRI-1", asset=None, outstanding_qty=2)],
    )
    def test_resolution_accepts_quantity_within_current_outstanding(self, _outstanding: MagicMock) -> None:
        doc = frappe._dict(
            company="_Test Company",
            material_request="MR-1",
            items=[frappe._dict(idx=1, material_request_item="MRI-1", asset=None, qty=2)],
        )

        BorrowedItemResolution._validate_outstanding_quantities(cast(BorrowedItemResolution, doc))

    @patch.object(frappe.db, "get_value")
    def test_before_submit_locks_material_request_items_before_rechecking(self, get_value: MagicMock) -> None:
        doc = MagicMock()
        doc.get.side_effect = {"items": [frappe._dict(material_request_item="MRI-1")]}.get
        doc._validate_outstanding_quantities = MagicMock()

        BorrowedItemResolution.before_submit(doc)

        get_value.assert_called_once_with("Material Request Item", "MRI-1", "name", for_update=True)
        doc._validate_outstanding_quantities.assert_called_once_with()
