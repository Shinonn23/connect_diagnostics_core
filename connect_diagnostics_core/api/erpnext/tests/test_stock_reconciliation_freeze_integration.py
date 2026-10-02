# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native pre-effect coverage for stock reconciliation freeze boundaries."""

from __future__ import annotations

from uuid import uuid4

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_internal_supplier
from erpnext.stock.doctype.delivery_note.delivery_note import make_inter_company_purchase_receipt
from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
from erpnext.stock.doctype.landed_cost_voucher.test_landed_cost_voucher import (
    make_landed_cost_voucher,
)
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import (
    make_purchase_receipt,
)
from erpnext.stock.doctype.stock_reconciliation.test_stock_reconciliation import (
    create_stock_reconciliation,
)
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import stock_reconciliation_freeze

COMPANY = "_Test Company"
ITEM = "_Test Item"


def _freeze(warehouse: str, company: str = COMPANY) -> str:
    reconciliation = create_stock_reconciliation(
        company=company,
        item_code=ITEM,
        warehouse=warehouse,
        qty=1,
        rate=100,
        do_not_submit=True,
    )
    return str(reconciliation.name)


def _effects(doctype: str, name: str | None) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    assert name
    filters = {"voucher_type": doctype, "voucher_no": name}
    stock = frappe.get_all(
        "Stock Ledger Entry",
        filters=filters,
        fields=["name", "actual_qty", "is_cancelled"],
        order_by="name",
    )
    general = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=["name", "debit", "credit", "is_cancelled"],
        order_by="name",
    )
    return [dict(row) for row in stock], [dict(row) for row in general]


class TestNativeStockReconciliationFreeze(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        savepoint = f"freeze_coverage_{uuid4().hex[:12]}"
        frappe.db.savepoint(savepoint)
        self.addCleanup(frappe.db.rollback, save_point=savepoint)
        self.frozen = self._warehouse("Frozen")
        self.other = self._warehouse("Other")

    def _warehouse(self, label: str, company: str = COMPANY) -> str:
        warehouse = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": f"_Test Freeze {label} {uuid4().hex[:8]}",
                "company": company,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
        return str(warehouse.name)

    def _internal_transfer(self) -> tuple[Document, str]:
        company = COMPANY
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"_Test Freeze Internal Customer {uuid4().hex[:8]}",
                "customer_code": f"TFC{uuid4().hex[:8]}",
                "customer_group": "_Test Customer Group",
                "customer_type": "Individual",
                "territory": "_Test Territory",
                "is_internal_customer": 1,
                "represents_company": company,
                "companies": [{"company": company}],
            }
        ).insert(ignore_permissions=True)
        create_internal_supplier(f"_Test Freeze Internal Supplier {uuid4().hex[:8]}", company, company)
        source = self._warehouse("Source", company)
        transit = self._warehouse("Transit", company)
        destination = self._warehouse("Destination", company)
        make_purchase_receipt(item=ITEM, company=company, warehouse=source, qty=5)
        delivery = create_delivery_note(
            item_code=ITEM,
            company=company,
            customer=customer.name,
            cost_center="_Test Cost Center - _TC",
            expense_account="Cost of Goods Sold - _TC",
            qty=5,
            rate=500,
            warehouse=source,
            target_warehouse=transit,
        )
        receipt = make_inter_company_purchase_receipt(delivery.name)
        receipt.items[0].from_warehouse = transit
        receipt.items[0].warehouse = destination
        receipt.save()
        self.assertEqual(receipt.items[0].from_warehouse, transit)
        return receipt, transit

    def test_purchase_receipt_submit_refuses_frozen_warehouse_before_ledger(self) -> None:
        draft = make_purchase_receipt(do_not_submit=True, item=ITEM, warehouse=self.frozen)
        frozen_name = _freeze(self.frozen)
        self.assertTrue(frappe.db.exists("Stock Reconciliation", frozen_name))
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            draft.submit()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", draft.name, "docstatus"), 0)
        self.assertEqual(_effects("Purchase Receipt", draft.name), ([], []))

        # An unrelated physical warehouse remains available while this scope is frozen.
        unrelated = make_purchase_receipt(do_not_submit=True, item=ITEM, warehouse=self.other)
        unrelated.submit()
        self.assertEqual(unrelated.docstatus, 1)

    def test_purchase_receipt_cancel_refuses_frozen_warehouse_before_ledger(self) -> None:
        receipt = make_purchase_receipt(item=ITEM, warehouse=self.frozen)
        before = _effects("Purchase Receipt", receipt.name)
        self.assertTrue(before[0])
        _freeze(self.frozen)
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            receipt.cancel()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", receipt.name, "docstatus"), 1)
        self.assertEqual(_effects("Purchase Receipt", receipt.name), before)

    def test_pick_list_reservation_submit_remains_allowed_during_freeze_without_ledger(self) -> None:
        _freeze(self.frozen)
        pick_list = frappe.get_doc(
            {
                "doctype": "Pick List",
                "company": COMPANY,
                "customer": "_Test Customer",
                "items_based_on": "Sales Order",
                "purpose": "Delivery",
                "locations": [
                    {
                        "item_code": ITEM,
                        "qty": 1,
                        "stock_qty": 1,
                        "conversion_factor": 1,
                        "warehouse": self.frozen,
                    }
                ],
            }
        ).insert(ignore_permissions=True)

        pick_list.submit()

        self.assertEqual(pick_list.docstatus, 1)
        self.assertFalse(
            frappe.db.exists(
                "Stock Ledger Entry", {"voucher_type": "Pick List", "voucher_no": pick_list.name}
            )
        )

    def test_purchase_receipt_outgoing_source_freeze_blocks_submit_before_ledger(self) -> None:
        transfer, source = self._internal_transfer()
        _freeze(source)
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            transfer.submit()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", transfer.name, "docstatus"), 0)
        self.assertEqual(_effects("Purchase Receipt", transfer.name), ([], []))

    def test_purchase_receipt_outgoing_source_freeze_blocks_cancel_before_ledger(self) -> None:
        transfer, source = self._internal_transfer()
        transfer.submit()
        before = _effects("Purchase Receipt", transfer.name)
        self.assertTrue(before[0])
        _freeze(source)
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            transfer.cancel()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", transfer.name, "docstatus"), 1)
        self.assertEqual(_effects("Purchase Receipt", transfer.name), before)

    def test_landed_cost_submit_checks_source_before_replay(self) -> None:
        receipt = make_purchase_receipt(item=ITEM, warehouse=self.frozen)
        voucher = make_landed_cost_voucher(
            receipt_document_type="Purchase Receipt",
            receipt_document=receipt.name,
            company=COMPANY,
            charges=50,
            do_not_submit=True,
        )
        before = _effects("Purchase Receipt", receipt.name)
        _freeze(self.frozen)
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            voucher.submit()
        self.assertEqual(frappe.db.get_value("Landed Cost Voucher", voucher.name, "docstatus"), 0)
        self.assertEqual(_effects("Purchase Receipt", receipt.name), before)

    def test_landed_cost_cancel_checks_source_before_replay(self) -> None:
        receipt = make_purchase_receipt(item=ITEM, warehouse=self.frozen)
        voucher = make_landed_cost_voucher(
            receipt_document_type="Purchase Receipt",
            receipt_document=receipt.name,
            company=COMPANY,
            charges=50,
        )
        self.assertEqual(voucher.docstatus, 1)
        before = _effects("Purchase Receipt", receipt.name)
        _freeze(self.frozen)
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
            voucher.cancel()
        self.assertEqual(frappe.db.get_value("Landed Cost Voucher", voucher.name, "docstatus"), 1)
        self.assertEqual(_effects("Purchase Receipt", receipt.name), before)

    def test_new_source_and_outgoing_or_packed_hook_refuses_before_effect(self) -> None:
        _freeze(self.frozen)
        cases = (
            {
                "doctype": "Purchase Receipt",
                "items": [{"item_code": ITEM, "warehouse": self.other, "from_warehouse": self.frozen}],
            },
            {
                "doctype": "Purchase Invoice",
                "update_stock": 1,
                "items": [{"item_code": ITEM, "warehouse": self.other, "from_warehouse": self.frozen}],
            },
            {
                "doctype": "Delivery Note",
                "items": [{"item_code": "PARENT", "warehouse": self.other}],
                "packed_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
            {
                "doctype": "Sales Invoice",
                "update_stock": 1,
                "items": [{"item_code": "PARENT", "warehouse": self.other}],
                "packed_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
            {"doctype": "Subcontracting Receipt", "items": [{"item_code": ITEM, "warehouse": self.frozen}]},
            {
                "doctype": "Asset Capitalization",
                "stock_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
        )
        for values in cases:
            with self.subTest(doctype=values["doctype"]):
                doc = frappe.get_doc(values)
                with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
                    stock_reconciliation_freeze.validate_transaction(doc)

    def test_native_cancel_hook_dispatch_rejects_packed_and_new_source_scopes(self) -> None:
        _freeze(self.frozen)
        cases = (
            {
                "doctype": "Delivery Note",
                "items": [{"item_code": "PARENT", "warehouse": self.other}],
                "packed_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
            {
                "doctype": "Sales Invoice",
                "update_stock": 1,
                "items": [{"item_code": "PARENT", "warehouse": self.other}],
                "packed_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
            {
                "doctype": "Subcontracting Receipt",
                "items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
            {
                "doctype": "Asset Capitalization",
                "stock_items": [{"item_code": ITEM, "warehouse": self.frozen}],
            },
        )
        for values in cases:
            with self.subTest(doctype=values["doctype"]):
                with self.assertRaisesRegex(frappe.ValidationError, "Stock Reconciliation"):
                    Document(values).run_method("before_cancel")

    def test_non_old_purchase_raw_material_does_not_claim_unaffected_supplier_scope(self) -> None:
        _freeze(self.frozen)
        for doctype in ("Purchase Receipt", "Purchase Invoice"):
            with self.subTest(doctype=doctype):
                doc = Document(
                    {
                        "doctype": doctype,
                        "update_stock": 1,
                        "is_old_subcontracting_flow": 0,
                        "items": [{"item_code": ITEM, "warehouse": self.other}],
                        "supplier_warehouse": self.frozen,
                        "supplied_items": [{"rm_item_code": ITEM}],
                    }
                )
                stock_reconciliation_freeze.validate_transaction(doc)
