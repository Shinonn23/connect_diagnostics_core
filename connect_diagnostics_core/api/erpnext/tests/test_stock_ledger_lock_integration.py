# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Two real MariaDB sessions prove the Warehouse mutex and current freeze read."""

from __future__ import annotations

from uuid import uuid4

import frappe
from erpnext.stock.doctype.landed_cost_voucher.test_landed_cost_voucher import (
    make_landed_cost_voucher,
)
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt
from erpnext.stock.doctype.stock_reconciliation.test_stock_reconciliation import (
    create_stock_reconciliation,
)
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import stock_ledger_lock, stock_reconciliation_freeze

COMPANY = "_Test Company"
ITEM = "_Test Item"
EXISTING_A = "_Test Warehouse - _TC"
EXISTING_B = "_Test Warehouse 1 - _TC"


class TestNativeStockLedgerLock(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.owned: list[tuple[str, str]] = []
        self.addCleanup(self._cleanup_owned)
        self.a = self._warehouse("A")
        self.b = self._warehouse("B")
        frappe.db.commit()

    def _warehouse(self, suffix: str) -> str:
        doc = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": f"_Test Freeze Lock {suffix} {uuid4().hex}",
                "company": COMPANY,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
        self.owned.append(("Warehouse", str(doc.name)))
        return str(doc.name)

    def _reconciliation(self, warehouse: str) -> str:
        doc = create_stock_reconciliation(
            company=COMPANY,
            item_code=ITEM,
            warehouse=warehouse,
            qty=1,
            rate=100,
            do_not_submit=True,
        )
        self.owned.append(("Stock Reconciliation", str(doc.name)))
        return str(doc.name)

    def _draft_receipt(self, warehouse: str) -> str:
        doc = frappe.get_doc(
            {
                "doctype": "Purchase Receipt",
                "company": COMPANY,
                "supplier": "_Test Supplier",
                "currency": "THB",
                "remarks": f"_Test Freeze Lock {uuid4().hex}",
                "items": [{"item_code": ITEM, "warehouse": warehouse, "qty": 1, "rate": 100}],
            }
        ).insert(ignore_permissions=True)
        self.owned.append(("Purchase Receipt", str(doc.name)))
        return str(doc.name)

    def _cleanup_owned(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        for doctype, name in reversed(self.owned):
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, ignore_permissions=True)
        frappe.db.commit()

    def _landed_cost_draft(self) -> tuple[str, str]:
        receipt_name = self._draft_receipt(EXISTING_A)
        # A draft reference is enough to test current locked reads. The accepted
        # coverage suite separately exercises genuine submitted LCV replay.
        voucher = frappe.get_doc(
            {
                "doctype": "Landed Cost Voucher",
                "company": COMPANY,
                "distribute_charges_based_on": "Amount",
                "purchase_receipts": [
                    {
                        "receipt_document_type": "Purchase Receipt",
                        "receipt_document": receipt_name,
                    }
                ],
                "taxes": [{"description": "_Test Freeze Lock Charge", "amount": 1}],
            }
        )
        voucher.set_new_name()
        voucher.set_parent_in_children()
        voucher.db_insert()
        self.owned.append(("Landed Cost Voucher", str(voucher.name)))
        for child in voucher.get_all_children():
            child.db_insert()
        return receipt_name, str(voucher.name)

    def test_same_warehouse_nowait_and_unrelated_warehouse_progress(self) -> None:
        with self.primary_connection():
            stock_ledger_lock.lock_warehouses((self.a,))
            with self.secondary_connection():
                with self.assertRaises(frappe.QueryTimeoutError):
                    stock_ledger_lock.lock_warehouses((self.a,))
                stock_ledger_lock.lock_warehouses((self.b,))
                frappe.db.rollback()

    def test_current_reconciliation_read_does_not_lock_unrelated_warehouse(self) -> None:
        reconciliation_name = self._reconciliation(self.b)
        frappe.db.commit()
        with self.primary_connection():
            frappe.db.get_value("Stock Reconciliation", reconciliation_name, "name", for_update=True)
            with self.secondary_connection():
                stock_reconciliation_freeze.validate_transaction(
                    Document(
                        {
                            "doctype": "Purchase Receipt",
                            "items": [{"item_code": ITEM, "warehouse": self.a}],
                        }
                    )
                )
                frappe.db.rollback()

    def test_old_rr_snapshot_still_sees_new_reconciliation_before_real_receipt_effect(self) -> None:
        receipt_name = self._draft_receipt(self.a)
        frappe.db.commit()
        with self.primary_connection():
            with self.secondary_connection():
                # Establish an ordinary repeatable-read snapshot before the publisher commits.
                self.assertEqual(frappe.db.get_value("Purchase Receipt", receipt_name, "docstatus"), 0)
            reconciliation_name = self._reconciliation(self.a)
            frappe.db.commit()
            with self.secondary_connection():
                receipt = frappe.get_doc("Purchase Receipt", receipt_name)
                with self.assertRaisesRegex(frappe.ValidationError, reconciliation_name):
                    receipt.submit()
                self.assertEqual(frappe.db.get_value("Purchase Receipt", receipt_name, "docstatus"), 0)
                self.assertEqual(
                    frappe.db.count(
                        "Stock Ledger Entry",
                        {"voucher_type": "Purchase Receipt", "voucher_no": receipt_name},
                    ),
                    0,
                )
                frappe.db.rollback()

    def test_publisher_old_new_and_delete_scope_contend_with_effect_mutex(self) -> None:
        reconciliation_name = self._reconciliation(self.a)
        frappe.db.commit()
        with self.primary_connection():
            stock_ledger_lock.lock_warehouses((self.a,))
            with self.secondary_connection():
                doc = frappe.get_doc("Stock Reconciliation", reconciliation_name)
                doc.items[0].warehouse = self.b
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    doc.save()
                frappe.db.rollback()
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    frappe.delete_doc("Stock Reconciliation", reconciliation_name, ignore_permissions=True)
                frappe.db.rollback()
            frappe.db.rollback()
            stock_ledger_lock.lock_warehouses((self.b,))
            with self.secondary_connection():
                doc = frappe.get_doc("Stock Reconciliation", reconciliation_name)
                doc.items[0].warehouse = self.b
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    doc.save()
                frappe.db.rollback()

    def test_landed_cost_held_reference_refuses_nowait(self) -> None:
        receipt_name, voucher_name = self._landed_cost_draft()
        frappe.db.commit()
        with self.primary_connection():
            frappe.db.get_value("Purchase Receipt", receipt_name, "name", for_update=True)
            with self.secondary_connection():
                voucher = frappe.get_doc("Landed Cost Voucher", voucher_name)
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    stock_reconciliation_freeze.validate_transaction(voucher)
                frappe.db.rollback()

    def test_landed_cost_held_non_scope_child_refuses_nowait(self) -> None:
        _receipt_name, voucher_name = self._landed_cost_draft()
        tax_name = str(frappe.get_doc("Landed Cost Voucher", voucher_name).taxes[0].name)
        frappe.db.commit()
        with self.primary_connection():
            frappe.db.get_value("Landed Cost Taxes and Charges", tax_name, "name", for_update=True)
            with self.secondary_connection():
                voucher = frappe.get_doc("Landed Cost Voucher", voucher_name)
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    stock_reconciliation_freeze.validate_transaction(voucher)
                frappe.db.rollback()

    def test_landed_cost_old_snapshot_uses_current_reference_warehouse(self) -> None:
        receipt_name, voucher_name = self._landed_cost_draft()
        item_name = str(frappe.get_doc("Purchase Receipt", receipt_name).items[0].name)
        frappe.db.commit()
        try:
            with self.primary_connection():
                with self.secondary_connection():
                    stale = frappe.get_doc("Purchase Receipt", receipt_name)
                    self.assertEqual(stale.items[0].warehouse, EXISTING_A)
                    voucher = frappe.get_doc("Landed Cost Voucher", voucher_name)
                # This deliberate test fixture edit represents a changed linked source,
                # not a supported post-submit warehouse mutation by an ERPNext user.
                frappe.db.set_value("Purchase Receipt Item", item_name, "warehouse", EXISTING_B)
                reconciliation_name = self._reconciliation(EXISTING_B)
                frappe.db.commit()
                with self.secondary_connection():
                    with self.assertRaisesRegex(frappe.ValidationError, reconciliation_name):
                        stock_reconciliation_freeze.validate_transaction(voucher)
                    frappe.db.rollback()
        finally:
            with self.primary_connection():
                frappe.db.set_value("Purchase Receipt Item", item_name, "warehouse", EXISTING_A)
                frappe.db.commit()


class TestNativeLandedCostEffectReferences(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        savepoint = f"lcv_effect_refs_{uuid4().hex[:12]}"
        frappe.db.savepoint(savepoint)
        self.addCleanup(frappe.db.rollback, save_point=savepoint)

    def _effects(self, doctype: str, name: str) -> tuple[list[dict], list[dict]]:
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

    def test_native_submit_checks_changed_in_memory_receipt_scope(self) -> None:
        first = make_purchase_receipt(item=ITEM, warehouse=EXISTING_A)
        frozen = make_purchase_receipt(item=ITEM, warehouse=EXISTING_B)
        voucher = make_landed_cost_voucher(
            receipt_document_type="Purchase Receipt",
            receipt_document=first.name,
            company=COMPANY,
            charges=50,
            do_not_submit=True,
        )
        before = self._effects("Purchase Receipt", frozen.name)
        reconciliation = create_stock_reconciliation(
            company=COMPANY,
            item_code=ITEM,
            warehouse=EXISTING_B,
            qty=1,
            rate=100,
            do_not_submit=True,
        )
        voucher.purchase_receipts[0].receipt_document = frozen.name
        voucher.items = []
        with self.assertRaisesRegex(frappe.ValidationError, str(reconciliation.name)):
            voucher.submit()
        self.assertEqual(frappe.db.get_value("Landed Cost Voucher", voucher.name, "docstatus"), 0)
        self.assertEqual(self._effects("Purchase Receipt", frozen.name), before)

    def test_native_cancel_refuses_changed_in_memory_receipt_identity(self) -> None:
        first = make_purchase_receipt(item=ITEM, warehouse=EXISTING_A)
        other = make_purchase_receipt(item=ITEM, warehouse=EXISTING_B)
        voucher = make_landed_cost_voucher(
            receipt_document_type="Purchase Receipt",
            receipt_document=first.name,
            company=COMPANY,
            charges=50,
        )
        first_before = self._effects("Purchase Receipt", first.name)
        other_before = self._effects("Purchase Receipt", other.name)
        voucher.purchase_receipts[0].receipt_document = other.name
        with self.assertRaisesRegex(frappe.ValidationError, "receipt documents changed"):
            voucher.cancel()
        self.assertEqual(frappe.db.get_value("Landed Cost Voucher", voucher.name, "docstatus"), 1)
        self.assertEqual(self._effects("Purchase Receipt", first.name), first_before)
        self.assertEqual(self._effects("Purchase Receipt", other.name), other_before)
