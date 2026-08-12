# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import stock_count
from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count.stock_count import (
    StockCount,
)
from connect_diagnostics_core.setup.stock_count import APPROVED

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
HOLDING_WAREHOUSE = "_Test Stock Count Holding - _TC"

# IntegrationTestCase rolls the whole class's DB changes back in a class cleanup,
# so these tests never delete what they create -- and must not, because the docs
# and the Stock Entries they post are submitted (docstatus 1), which delete_doc
# refuses. The rollback is the cleanup.


def _ensure_holding_warehouse() -> str:
    if not frappe.db.exists("Warehouse", HOLDING_WAREHOUSE):
        frappe.get_doc(
            {"doctype": "Warehouse", "warehouse_name": "_Test Stock Count Holding", "company": COMPANY}
        ).insert(ignore_permissions=True)
    return HOLDING_WAREHOUSE


def _prepare_environment() -> None:
    """Give the generated stock postings what ERPNext needs to submit.

    The counted items carry no real on-hand stock, so a shortage's Material Issue
    would hit negative stock; and a surplus's Material Receipt books value through
    the company's Stock Adjustment account. Both are configured here rather than
    depending on the bootstrap test company having them.
    """
    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
    if not frappe.db.get_value("Company", COMPANY, "stock_adjustment_account"):
        frappe.db.set_value("Company", COMPANY, "stock_adjustment_account", _stock_adjustment_account())


def _stock_adjustment_account() -> str:
    account = frappe.db.get_value(
        "Account", {"company": COMPANY, "account_type": "Stock Adjustment", "is_group": 0}, "name"
    )
    if account:
        return cast(str, account)
    from erpnext.accounts.doctype.account.test_account import create_account

    return create_account(
        account_name="_Test Stock Count Adjustment",
        company=COMPANY,
        parent_account=frappe.db.get_value(
            "Account", {"company": COMPANY, "root_type": "Expense", "is_group": 1}, "name"
        ),
        account_type="Stock Adjustment",
    )


def _approved_stock_count(**overrides: object) -> StockCount:
    data: dict[str, object] = {
        "doctype": "Stock Count",
        "count_type": stock_count.MONTHLY,
        "company": COMPANY,
        "warehouse": WAREHOUSE,
        "posting_date": "2026-08-12",
        "posting_time": "10:00:00",
        "selection_method": "Manual",
        "holding_warehouse": _ensure_holding_warehouse(),
        "items": [_item("_Test Item", system_qty=10, count_qty=8)],
    }
    data.update(overrides)
    doc = cast(StockCount, frappe.get_doc(data)).insert(ignore_permissions=True)
    doc.db_set("docstatus", 1, update_modified=False)
    doc.db_set("count_state", APPROVED, update_modified=False)
    doc.reload()
    return doc


def _item(item_code: str, *, system_qty: float, count_qty: float) -> dict[str, object]:
    return {
        "item_code": item_code,
        "warehouse": WAREHOUSE,
        "stock_uom": "_Test UOM",
        "system_qty": system_qty,
        "count_qty": count_qty,
        "valuation_rate": 100,
    }


class TestGenerateHoldingTransfer(IntegrationTestCase):
    def setUp(self) -> None:
        _prepare_environment()
        self.doc = _approved_stock_count()

    def test_creates_submitted_material_transfer(self) -> None:
        result = stock_count.generate_holding_transfer(self.doc.name)

        entry = cast(StockEntry, frappe.get_doc("Stock Entry", result["data"]["stock_entry"]))
        self.assertEqual(entry.docstatus, 1)
        self.assertEqual(entry.purpose, "Material Transfer")
        self.assertEqual(entry.from_warehouse, WAREHOUSE)
        self.assertEqual(entry.to_warehouse, HOLDING_WAREHOUSE)
        self.assertEqual(entry.items[0].qty, 2)
        self.assertEqual(entry.get("stock_count"), self.doc.name)

        self.doc.reload()
        self.assertEqual(len(self.doc.adjustments), 1)
        self.assertEqual(self.doc.adjustments[0].entry_type, "Material Transfer")

    def test_rejects_second_generation(self) -> None:
        stock_count.generate_holding_transfer(self.doc.name)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_holding_transfer(self.doc.name)

    def test_rejects_yearly_count(self) -> None:
        yearly = _approved_stock_count(count_type=stock_count.YEARLY)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_holding_transfer(yearly.name)

    def test_no_op_when_no_variance(self) -> None:
        matched = _approved_stock_count(items=[_item("_Test Item", system_qty=10, count_qty=10)])
        result = stock_count.generate_holding_transfer(matched.name)
        self.assertIsNone(result["data"])


class TestGenerateStockAdjustment(IntegrationTestCase):
    def setUp(self) -> None:
        _prepare_environment()
        self.doc = _approved_stock_count(
            count_type=stock_count.YEARLY,
            items=[
                _item("_Test Item", system_qty=10, count_qty=8),
                _item("_Test Item 2", system_qty=5, count_qty=7),
            ],
        )

    def test_posts_receipt_for_surplus_and_issue_for_shortage(self) -> None:
        result = stock_count.generate_stock_adjustment(self.doc.name)

        receipt = cast(StockEntry, frappe.get_doc("Stock Entry", result["data"]["receipt_entry"]))
        self.assertEqual(receipt.purpose, "Material Receipt")
        self.assertEqual(receipt.items[0].qty, 2)
        self.assertEqual(receipt.items[0].t_warehouse, WAREHOUSE)

        issue = cast(StockEntry, frappe.get_doc("Stock Entry", result["data"]["issue_entry"]))
        self.assertEqual(issue.purpose, "Material Issue")
        self.assertEqual(issue.items[0].qty, 2)
        self.assertEqual(issue.items[0].s_warehouse, WAREHOUSE)

        self.doc.reload()
        entry_types = {row.entry_type for row in self.doc.adjustments}
        self.assertEqual(entry_types, {"Material Receipt", "Material Issue"})

    def test_rejects_second_generation(self) -> None:
        stock_count.generate_stock_adjustment(self.doc.name)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_stock_adjustment(self.doc.name)

    def test_rejects_monthly_count(self) -> None:
        monthly = _approved_stock_count()
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_stock_adjustment(monthly.name)

    def test_rejects_when_not_approved(self) -> None:
        draft = cast(
            StockCount,
            frappe.get_doc(
                {
                    "doctype": "Stock Count",
                    "count_type": stock_count.YEARLY,
                    "company": COMPANY,
                    "warehouse": WAREHOUSE,
                    "posting_date": "2026-08-12",
                    "posting_time": "10:00:00",
                    "items": [_item("_Test Item", system_qty=10, count_qty=8)],
                }
            ),
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            stock_count.generate_stock_adjustment(draft.name)
