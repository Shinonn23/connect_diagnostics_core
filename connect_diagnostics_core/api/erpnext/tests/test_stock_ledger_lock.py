# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_ledger_lock, stock_reconciliation_freeze


class TestStockLedgerLock(UnitTestCase):
    def test_warehouse_mutex_is_sorted_deduplicated_and_fails_closed(self) -> None:
        with patch.object(frappe.db, "get_value", side_effect=lambda _dt, name, _field, **_kw: name) as get:
            stock_ledger_lock.lock_warehouses(("WH-B", "WH-A", "WH-B"))
        self.assertEqual([call.args[1] for call in get.call_args_list], ["WH-A", "WH-B"])
        self.assertTrue(
            all(call.kwargs == {"for_update": True, "wait": False} for call in get.call_args_list)
        )
        with (
            patch.object(frappe.db, "get_value", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_ledger_lock.lock_warehouses(("MISSING",))
        with self.assertRaises(frappe.ValidationError):
            stock_ledger_lock.lock_warehouses(("",))

    def test_publisher_locks_persisted_and_proposed_scope(self) -> None:
        previous = Document(
            {"doctype": "Stock Reconciliation", "name": "SR-1", "items": [{"warehouse": "OLD"}]}
        )
        proposed = Document(
            {"doctype": "Stock Reconciliation", "name": "SR-1", "items": [{"warehouse": "NEW"}]}
        )
        with (
            patch.object(Document, "is_new", return_value=False),
            patch.object(stock_reconciliation_freeze, "locked_document", return_value=previous),
            patch.object(stock_reconciliation_freeze, "lock_warehouses") as lock,
        ):
            stock_reconciliation_freeze.lock_reconciliation_scope_before_validate(proposed)
        lock.assert_called_once_with({"OLD", "NEW"})

    def test_trash_uses_locked_persisted_scope_not_delete_payload(self) -> None:
        previous = Document(
            {"doctype": "Stock Reconciliation", "name": "SR-1", "items": [{"warehouse": "OLD"}]}
        )
        stale = Document(
            {"doctype": "Stock Reconciliation", "name": "SR-1", "items": [{"warehouse": "STALE"}]}
        )
        with (
            patch.object(stock_reconciliation_freeze, "locked_document", return_value=previous) as current,
            patch.object(stock_reconciliation_freeze, "lock_warehouses") as lock,
        ):
            stock_reconciliation_freeze.lock_reconciliation_scope_on_trash(stale)
        current.assert_called_once_with("Stock Reconciliation", "SR-1")
        lock.assert_called_once_with({"OLD"})

    def test_held_warehouse_conflict_has_retry_message(self) -> None:
        with (
            patch.object(
                stock_reconciliation_freeze, "lock_warehouses", side_effect=frappe.QueryTimeoutError
            ),
            self.assertRaisesRegex(frappe.ValidationError, "retry"),
        ):
            stock_reconciliation_freeze.validate_transaction(
                Document({"doctype": "Stock Entry", "items": [{"item_code": "A", "s_warehouse": "WH-A"}]})
            )
