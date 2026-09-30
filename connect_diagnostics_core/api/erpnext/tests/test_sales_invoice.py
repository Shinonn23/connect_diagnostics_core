# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import sales_invoice


class TestDemoSalesInvoice(UnitTestCase):
    def test_non_demo_submit_and_cancel_are_ignored(self) -> None:
        invoice = cast(Document, frappe._dict(name="SINV-1"))
        with patch.object(sales_invoice.frappe, "db") as db:
            sales_invoice.on_submit_demo_sales_invoice(invoice, "on_submit")
            sales_invoice.on_cancel_demo_sales_invoice(invoice, "on_cancel")
        db.get_value.assert_not_called()

    @patch.object(sales_invoice.frappe, "get_roles", return_value=["Sales User"])
    def test_create_requires_accounts_role(self, _get_roles: MagicMock) -> None:
        with self.assertRaises(frappe.PermissionError):
            sales_invoice.create_demo_sales_invoice("ALLOC-1", "CUSTOMER-1")

    def test_submit_rejects_tampered_sale_identity(self) -> None:
        invoice = cast(
            Document,
            frappe._dict(
                name="SINV-1",
                company="Company",
                customer="Customer",
                update_stock=0,
                demo_fulfillment_allocation="ALLOC-1",
                demo_outbound_dispatch="DSP-1",
                demo_sale_attempt=2,
                demo_sale_operation_id="demo-sale:ALLOC-1:1",
                items=[],
            ),
        )
        context = (
            frappe._dict(
                name="ALLOC-1",
                sale_attempt=2,
                current_sales_invoice="SINV-1",
            ),
            frappe._dict(company="Company"),
            frappe._dict(name="ASSET-1", item_code="ITEM-1"),
            frappe._dict(name="DSP-1"),
        )
        with patch.object(sales_invoice, "_demo_sale_context", return_value=context):
            with self.assertRaises(frappe.ValidationError):
                sales_invoice.validate_demo_sales_invoice(invoice)

    def test_stale_cancel_attempt_fails_closed(self) -> None:
        invoice = cast(
            Document,
            frappe._dict(
                name="SINV-OLD",
                demo_fulfillment_allocation="ALLOC-1",
                demo_sale_attempt=1,
                demo_sale_operation_id="demo-sale:ALLOC-1:1",
            ),
        )
        allocation = frappe._dict(
            name="ALLOC-1",
            current_sales_invoice="SINV-NEW",
            sale_attempt=2,
            lifecycle_state="Sold",
            resolved_asset="ASSET-1",
        )
        with patch.object(sales_invoice.frappe.db, "get_value", return_value=allocation):
            with self.assertRaises(frappe.ValidationError):
                sales_invoice.on_cancel_demo_sales_invoice(invoice, "on_cancel")
