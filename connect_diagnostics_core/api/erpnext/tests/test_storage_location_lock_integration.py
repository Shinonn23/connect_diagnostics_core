# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native two-session locking at the first Storage Location ledger boundary."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import frappe
from erpnext.stock import get_warehouse_account
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.model.document import Document
from frappe.model.rename_doc import rename_doc
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    validate_ledger_location,
)

COMPANY = "_Test Company"
WAREHOUSE_A = "_Test Warehouse - _TC"
WAREHOUSE_B = "_Test Warehouse 1 - _TC"
ITEM = "_Test Item"


class TestStorageLocationFirstMovement(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.location_name = f"_Test First Movement {uuid4().hex}"
        self.addCleanup(self._cleanup_location)
        frappe.get_doc(
            {
                "doctype": "Storage Location",
                "location_code": self.location_name,
                "warehouse": WAREHOUSE_A,
            }
        ).insert(ignore_permissions=True)
        # Publish the owned Location for the second MariaDB session.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def _cleanup_location(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        if frappe.db.exists("Storage Location", self.location_name):
            frappe.delete_doc("Storage Location", self.location_name, force=True, ignore_permissions=True)
        # Persist exact fixture cleanup after both sessions release their locks.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def test_producer_refuses_held_foreign_location_without_wait(self) -> None:
        with self.primary_connection():
            frappe.db.get_value("Storage Location", self.location_name, "name", for_update=True)
            with self.secondary_connection():
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    validate_ledger_location(
                        Document(
                            {
                                "doctype": "Stock Ledger Entry",
                                "warehouse": WAREHOUSE_A,
                                "storage_location": self.location_name,
                            }
                        )
                    )
                frappe.db.rollback()

    def test_native_reparent_refuses_held_foreign_warehouse_without_wait(self) -> None:
        with self.primary_connection():
            frappe.db.get_value("Warehouse", WAREHOUSE_B, "name", for_update=True)
            with self.secondary_connection():
                location = frappe.get_doc("Storage Location", self.location_name)
                cast(Any, location).warehouse = WAREHOUSE_B
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    location.save(ignore_permissions=True)
                self.assertEqual(
                    frappe.db.get_value("Storage Location", self.location_name, "warehouse"), WAREHOUSE_A
                )
                frappe.db.rollback()

    def test_native_first_movement_refuses_held_foreign_location(self) -> None:
        with self.primary_connection():
            frappe.db.get_value("Storage Location", self.location_name, "name", for_update=True)
            with self.secondary_connection():
                voucher = cast(Any, make_stock_entry)(
                    item_code=ITEM,
                    target=WAREHOUSE_A,
                    qty=1,
                    basic_rate=100,
                    do_not_save=True,
                )
                voucher.items[0].set("to_storage_location", self.location_name)
                voucher.insert(ignore_permissions=True)
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    voucher.submit()
                self.assertEqual(
                    frappe.db.count(
                        "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": voucher.name}
                    ),
                    0,
                )
                frappe.db.rollback()

    def test_native_stock_ledger_insert_rejects_wrong_warehouse(self) -> None:
        voucher = cast(Any, make_stock_entry)(
            item_code=ITEM,
            target=WAREHOUSE_B,
            qty=1,
            basic_rate=100,
            do_not_save=True,
        ).insert(ignore_permissions=True)
        entry = frappe.get_doc(
            {
                "doctype": "Stock Ledger Entry",
                "company": COMPANY,
                "item_code": ITEM,
                "warehouse": WAREHOUSE_B,
                "storage_location": self.location_name,
                "actual_qty": 1,
                "incoming_rate": 100,
                "posting_date": frappe.utils.today(),
                "posting_time": "12:00:00",
                "voucher_type": "Stock Entry",
                "voucher_no": voucher.name,
            }
        )
        with self.assertRaisesRegex(frappe.ValidationError, "must belong"):
            entry.insert(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("Stock Ledger Entry", entry.name))

    def test_locationless_native_stock_ledger_hook_is_noop(self) -> None:
        validate_ledger_location(Document({"doctype": "Stock Ledger Entry", "warehouse": WAREHOUSE_A}))


class TestCommittedFirstMovementHistory(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.token = uuid4().hex
        self.location_name = f"_Test First History Location {self.token}"
        self.warehouses: list[str] = []
        self.entry_name: str | None = None
        self.artifact_ids: dict[str, set[str]] = {
            doctype: set()
            for doctype in ("Stock Ledger Entry", "GL Entry", "Repost Item Valuation", "Workflow Action")
        }
        self.addCleanup(self._cleanup_owned)
        self.a = self._warehouse("A")
        self.b = self._warehouse("B")
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": self.location_name, "warehouse": self.a}
        ).insert(ignore_permissions=True)
        # Publish the owned Warehouse and Location fixtures for the second session.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def _warehouse(self, suffix: str) -> str:
        warehouse = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": f"_Test First History {suffix} {self.token}",
                "company": COMPANY,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
        self.warehouses.append(str(warehouse.name))
        return str(warehouse.name)

    def _source_artifacts(self) -> dict[str, list[frappe._dict]]:
        assert self.entry_name
        return {
            "Stock Ledger Entry": frappe.get_all(
                "Stock Ledger Entry",
                {"voucher_type": "Stock Entry", "voucher_no": self.entry_name},
                ["name", "voucher_type", "voucher_no", "warehouse", "storage_location", "company"],
            ),
            "GL Entry": frappe.get_all(
                "GL Entry",
                {"voucher_type": "Stock Entry", "voucher_no": self.entry_name},
                ["name", "voucher_type", "voucher_no", "company", "account"],
            ),
            "Repost Item Valuation": frappe.get_all(
                "Repost Item Valuation",
                {"voucher_type": "Stock Entry", "voucher_no": self.entry_name},
                ["name", "voucher_type", "voucher_no", "company", "docstatus"],
            ),
            "Workflow Action": frappe.get_all(
                "Workflow Action",
                {"reference_doctype": "Stock Entry", "reference_name": self.entry_name},
                ["name", "reference_doctype", "reference_name"],
            ),
        }

    def _assert_artifact_ownership(self, artifacts: dict[str, list[frappe._dict]], source: Document) -> None:
        assert self.entry_name and self.token in str(source.get("remarks") or "")
        self.assertEqual(source.get("company"), COMPANY)
        item = source.get("items")[0]
        self.assertEqual(item.get("t_warehouse"), self.a)
        self.assertEqual(item.get("to_storage_location"), self.location_name)
        expected_accounts = {
            str(item.get("expense_account")),
            str(get_warehouse_account(frappe.get_doc("Warehouse", self.a))),
        }
        for row in artifacts["Stock Ledger Entry"]:
            self.assertEqual((row.voucher_type, row.voucher_no), ("Stock Entry", self.entry_name))
            self.assertEqual(
                (row.company, row.warehouse, row.storage_location), (COMPANY, self.a, self.location_name)
            )
        for row in artifacts["GL Entry"]:
            self.assertEqual(
                (row.voucher_type, row.voucher_no, row.company), ("Stock Entry", self.entry_name, COMPANY)
            )
            self.assertIn(row.account, expected_accounts)
        for row in artifacts["Repost Item Valuation"]:
            self.assertEqual(
                (row.voucher_type, row.voucher_no, row.company), ("Stock Entry", self.entry_name, COMPANY)
            )
        for row in artifacts["Workflow Action"]:
            self.assertEqual((row.reference_doctype, row.reference_name), ("Stock Entry", self.entry_name))

    def _remember_artifacts(self) -> None:
        for doctype, rows in self._source_artifacts().items():
            self.artifact_ids[doctype].update(str(row.name) for row in rows)

    def _assert_owned_bins_zero(self) -> None:
        quantity_fields = (
            "actual_qty",
            "reserved_qty",
            "ordered_qty",
            "indented_qty",
            "projected_qty",
            "planned_qty",
        )
        for warehouse in self.warehouses:
            for row in frappe.get_all("Bin", {"warehouse": warehouse}, ["name", *quantity_fields]):
                self.assertEqual(tuple(float(row.get(field) or 0) for field in quantity_fields), (0.0,) * 6)

    def _cleanup_owned(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        if self.entry_name and frappe.db.exists("Stock Entry", self.entry_name):
            source = frappe.get_doc("Stock Entry", self.entry_name)
            self.assertIn(self.token, str(source.get("remarks") or ""))
            if source.docstatus == 1:
                source.cancel()
                self._remember_artifacts()
            source = frappe.get_doc("Stock Entry", self.entry_name)
            artifacts = self._source_artifacts()
            self._assert_artifact_ownership(artifacts, source)
            for doctype, rows in artifacts.items():
                self.assertEqual({str(row.name) for row in rows}, self.artifact_ids[doctype])
            self._assert_owned_bins_zero()
            for row in artifacts["Repost Item Valuation"]:
                repost = frappe.get_doc("Repost Item Valuation", cast(str, row.name))
                if repost.docstatus == 1:
                    repost.cancel()
                frappe.delete_doc("Repost Item Valuation", row.name, force=True, ignore_permissions=True)
            # Native cancellation retains ledger history. Remove only exact owned
            # scratch row names after source and accounting provenance checks.
            for doctype in ("Stock Ledger Entry", "GL Entry"):
                for row in artifacts[doctype]:
                    frappe.db.delete(doctype, {"name": row.name})
            frappe.delete_doc("Stock Entry", self.entry_name, force=True, ignore_permissions=True)
            self.assertTrue(all(not rows for rows in self._source_artifacts().values()))
        else:
            self._assert_owned_bins_zero()
        if frappe.db.exists("Storage Location", self.location_name):
            frappe.delete_doc("Storage Location", self.location_name, force=True, ignore_permissions=True)
        for warehouse in reversed(self.warehouses):
            frappe.delete_doc("Warehouse", warehouse, force=True, ignore_permissions=True)
        if self.entry_name:
            self.assertFalse(frappe.db.exists("Stock Entry", self.entry_name))
            self.assertTrue(all(not rows for rows in self._source_artifacts().values()))
        self.assertFalse(frappe.db.exists("Storage Location", self.location_name))
        for warehouse in self.warehouses:
            self.assertFalse(frappe.db.exists("Warehouse", warehouse))
        # Persist deletion only after checking ownership and zero active balances.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def _assert_history_denies_master_changes(self) -> None:
        location = frappe.get_doc("Storage Location", self.location_name)
        cast(Any, location).warehouse = self.b
        with self.assertRaisesRegex(frappe.ValidationError, "history"):
            location.save(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "history"):
            rename_doc(
                "Storage Location",
                self.location_name,
                f"_Test Renamed First History {self.token}",
                ignore_permissions=True,
            )
        with self.assertRaisesRegex(frappe.ValidationError, "history"):
            frappe.delete_doc("Storage Location", self.location_name, force=True, ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Storage Location", self.location_name, "warehouse"), self.a)

    def test_old_rr_snapshot_sees_committed_first_movement_and_cancelled_history(self) -> None:
        with self.primary_connection():
            with self.secondary_connection():
                self.assertEqual(
                    frappe.db.get_value("Storage Location", self.location_name, "warehouse"), self.a
                )
                self.assertFalse(
                    frappe.db.get_value(
                        "Stock Ledger Entry", {"storage_location": self.location_name}, "name"
                    )
                )
            voucher = cast(Any, make_stock_entry)(
                item_code=ITEM,
                target=self.a,
                qty=1,
                basic_rate=100,
                do_not_save=True,
            )
            voucher.remarks = f"_Test First History {self.token}"
            voucher.items[0].set("to_storage_location", self.location_name)
            voucher.insert(ignore_permissions=True)
            self.entry_name = str(voucher.name)
            voucher.submit()
            self._remember_artifacts()
            self.assertTrue(self.artifact_ids["Stock Ledger Entry"])
            # Publish native receipt history for the stale-snapshot probe.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            with self.secondary_connection():
                self._assert_history_denies_master_changes()
                frappe.db.rollback()
            voucher.reload()
            voucher.cancel()
            self._remember_artifacts()
            # Publish native cancellation history for the second-session probe.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            with self.secondary_connection():
                self._assert_history_denies_master_changes()
                frappe.db.rollback()


class TestCurrentLocationSnapshot(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(frappe.local.site, "local.test")
        self.old_user = frappe.session.user
        frappe.set_user("Administrator")
        self.token = uuid4().hex
        self.location_name = f"_Test Current Snapshot {self.token}"
        self.entry_name: str | None = None
        self.cutoff = datetime(2099, 1, 1)
        self.bin_before = float(
            frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": WAREHOUSE_A}, "actual_qty") or 0
        )
        self.addCleanup(self._finalize_history)
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": self.location_name, "warehouse": WAREHOUSE_A}
        ).insert(ignore_permissions=True)
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def _snapshot(self, *, locking_read: bool) -> Decimal:
        return snapshot_location(
            company=COMPANY,
            item_code=ITEM,
            warehouse=WAREHOUSE_A,
            storage_location=self.location_name,
            cutoff=self.cutoff,
            locking_read=locking_read,
        ).quantity

    def _assert_current_or_retry(self, expected: Decimal) -> None:
        try:
            self.assertEqual(self._snapshot(locking_read=True), expected)
        except frappe.ValidationError as error:
            self.assertEqual(str(error), "Stock scope is being updated by another transaction. Please retry.")
        finally:
            # A 1020 conflict invalidates the old repeatable-read transaction.
            frappe.db.rollback()

    def _source_rows(self, doctype: str) -> list[frappe._dict]:
        assert self.entry_name
        return frappe.get_all(
            doctype,
            filters={"voucher_type": "Stock Entry", "voucher_no": self.entry_name},
            fields=["name", "voucher_type", "voucher_no", "is_cancelled", "actual_qty"]
            if doctype == "Stock Ledger Entry"
            else ["name", "voucher_type", "voucher_no", "is_cancelled", "account", "debit", "credit"],
        )

    def _assert_restored_history(self, original_sle: set[str], original_gl: set[str]) -> None:
        assert self.entry_name
        source = frappe.get_doc("Stock Entry", self.entry_name)
        self.assertEqual(source.docstatus, 2)
        self.assertIn(self.token, str(source.get("remarks") or ""))
        sle = self._source_rows("Stock Ledger Entry")
        gl = self._source_rows("GL Entry")
        self.assertTrue(original_sle)
        self.assertTrue(original_sle.issubset({str(row.name) for row in sle}))
        self.assertTrue(original_gl.issubset({str(row.name) for row in gl}))
        self.assertTrue(all(row.is_cancelled for row in sle))
        self.assertEqual(sum((Decimal(str(row.actual_qty)) for row in sle), Decimal(0)), Decimal(0))
        for account in {str(row.account) for row in gl}:
            self.assertEqual(
                sum(
                    (
                        Decimal(str(row.debit)) - Decimal(str(row.credit))
                        for row in gl
                        if row.account == account
                    ),
                    Decimal(0),
                ),
                Decimal(0),
            )
        self.assertEqual(self._snapshot(locking_read=True), Decimal(0))
        self.assertEqual(
            float(
                frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": WAREHOUSE_A}, "actual_qty") or 0
            ),
            self.bin_before,
        )
        self.assertFalse(
            frappe.db.exists(
                "Workflow Action",
                {"reference_doctype": "Stock Entry", "reference_name": self.entry_name, "status": "Open"},
            )
        )

    def _finalize_history(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        frappe.set_user("Administrator")
        try:
            if self.entry_name and frappe.db.exists("Stock Entry", self.entry_name):
                source = frappe.get_doc("Stock Entry", self.entry_name)
                self.assertIn(self.token, str(source.get("remarks") or ""))
                if source.docstatus == 1:
                    apply_workflow(source, "Cancel Stock Entry")
                    frappe.db.commit()  # nosemgrep: frappe-manual-commit
                self.assertEqual(frappe.db.get_value("Stock Entry", self.entry_name, "docstatus"), 2)
                self.assertEqual(
                    frappe.db.get_value("Stock Entry", self.entry_name, "workflow_state"),
                    "Stock Entry Cancelled",
                )
                self.assertEqual(self._snapshot(locking_read=True), Decimal(0))
                self.assertFalse(
                    frappe.db.exists(
                        "Workflow Action",
                        {
                            "reference_doctype": "Stock Entry",
                            "reference_name": self.entry_name,
                            "status": "Open",
                        },
                    )
                )
                self.assertEqual(
                    float(
                        frappe.db.get_value(
                            "Bin", {"item_code": ITEM, "warehouse": WAREHOUSE_A}, "actual_qty"
                        )
                        or 0
                    ),
                    self.bin_before,
                )
            elif frappe.db.exists("Storage Location", self.location_name):
                frappe.delete_doc("Storage Location", self.location_name)
                frappe.db.commit()  # nosemgrep: frappe-manual-commit
        finally:
            frappe.db.rollback()
            frappe.set_user(self.old_user)

    def test_stale_rr_default_and_current_locking_read_across_receipt_and_cancel(self) -> None:
        with self.secondary_connection():
            self.assertEqual(self._snapshot(locking_read=False), Decimal(0))
        # Frappe's first secondary_connection() initializes local.db to the
        # secondary connection; restore primary explicitly before publishing.
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        with self.primary_connection():
            voucher = cast(Any, make_stock_entry)(
                item_code=ITEM,
                target=WAREHOUSE_A,
                qty=1,
                basic_rate=100,
                do_not_save=True,
            )
            voucher.remarks = f"_Test Current Snapshot {self.token}"
            voucher.items[0].set("to_storage_location", self.location_name)
            voucher.insert(ignore_permissions=True)
            voucher = apply_workflow(voucher, "Submit Stock Entry")
            self.entry_name = str(voucher.name)
            self.assertEqual(voucher.get("workflow_state"), "Stock Entry Submitted")
            original_sle = {str(row.name) for row in self._source_rows("Stock Ledger Entry")}
            original_gl = {str(row.name) for row in self._source_rows("GL Entry")}
            frappe.db.commit()  # nosemgrep: frappe-manual-commit

            with self.secondary_connection():
                self.assertEqual(self._snapshot(locking_read=False), Decimal(0))
                self._assert_current_or_retry(Decimal(1))
                self.assertEqual(self._snapshot(locking_read=True), Decimal(1))
                frappe.db.rollback()
                self.assertEqual(self._snapshot(locking_read=False), Decimal(1))

            voucher = apply_workflow(voucher, "Cancel Stock Entry")
            self.assertEqual(voucher.get("workflow_state"), "Stock Entry Cancelled")
            frappe.db.commit()  # nosemgrep: frappe-manual-commit

            with self.secondary_connection():
                self.assertEqual(self._snapshot(locking_read=False), Decimal(1))
                self._assert_current_or_retry(Decimal(0))
                self.assertEqual(self._snapshot(locking_read=True), Decimal(0))
                frappe.db.rollback()

            self._assert_restored_history(original_sle, original_gl)
