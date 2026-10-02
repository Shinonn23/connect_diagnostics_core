# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native dimension posting through the protected same-Warehouse transfer route."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import frappe
import frappe.client as frappe_client
from erpnext.stock.doctype.serial_and_batch_bundle.test_serial_and_batch_bundle import (
    make_serial_batch_bundle,
)
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime
from frappe.utils.nestedset import get_root_of

from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
from connect_diagnostics_core.api.erpnext.tests.test_stock_entry_workflow_integration import (
    APPROVER,
    COMPANY,
    ITEM,
    MAKER,
    REVIEWER,
    SOURCE,
    _bin_qty,
    _ensure_item,
    _ensure_user,
)
from connect_diagnostics_core.setup.storage_location import ensure_configuration

SOURCE_LOCATION = "_Test Workflow Source Location"
TARGET_LOCATION = "_Test Workflow Target Location"
EMPTY_LOCATION = "_Test Workflow Empty Location"
RECONCILIATION_APPROVER = "_test.location.accounts.manager@example.com"
RECONCILIATION_MAKER = "_test.location.stock.manager.maker@example.com"


def _ensure_employee_prerequisites() -> None:
    if not frappe.db.exists("Department", {"company": COMPANY}):
        root = get_root_of("Department")
        if not root:
            root = (
                frappe.get_doc(
                    {
                        "doctype": "Department",
                        "department_name": "_Test Storage Location Department Root",
                        "is_group": 1,
                    }
                )
                .insert()
                .name
            )
        frappe.get_doc(
            {
                "doctype": "Department",
                "department_name": "_Test Storage Location Approval Department",
                "company": COMPANY,
                "parent_department": root,
            }
        ).insert()
    if not frappe.db.exists("Employment Type", {}):
        frappe.get_doc(
            {"doctype": "Employment Type", "employee_type_name": "_Test Storage Location Employment Type"}
        ).insert()


def _location_qty(location: str) -> float:
    rows = frappe.get_all(
        "Stock Ledger Entry",
        filters={"item_code": ITEM, "warehouse": SOURCE, "storage_location": location, "is_cancelled": 0},
        fields=["actual_qty"],
    )
    return sum(float(row.actual_qty) for row in rows)


class TestStorageLocationIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        frappe.reload_doc("connect_diagnostics_stock", "doctype", "storage_location", force=True)
        super().setUpClass()
        ensure_configuration()

    def setUp(self) -> None:
        super().setUp()
        self._savepoint = f"location_ledger_{uuid4().hex}"
        frappe.db.savepoint(self._savepoint)
        self.addCleanup(self._rollback_fixture)
        old_user = frappe.session.user
        old_request = getattr(frappe.local, "request", None)
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        old_grants = list(grants) if grants is not None else None

        def restore_context() -> None:
            frappe.set_user(old_user)
            frappe.local.request = old_request
            if old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = old_grants

        self.addCleanup(restore_context)
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_employee_prerequisites()
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))
        _ensure_user(RECONCILIATION_APPROVER, ("Accounts Manager", "Stock Manager"))
        _ensure_user(RECONCILIATION_MAKER, ("Stock User", "Stock Manager"))
        for name in (SOURCE_LOCATION, TARGET_LOCATION, EMPTY_LOCATION):
            if not frappe.db.exists("Storage Location", name):
                frappe.get_doc(
                    {"doctype": "Storage Location", "location_code": name, "warehouse": SOURCE}
                ).insert(ignore_permissions=True)

    def _rollback_fixture(self) -> None:
        frappe.db.rollback(save_point=self._savepoint)
        frappe.db.value_cache.clear()
        frappe.clear_cache(doctype="Stock Settings")

    def _seed(self) -> None:
        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=ITEM, target=SOURCE, qty=5, basic_rate=100, do_not_save=True),
        )
        receipt.items[0].set("to_storage_location", SOURCE_LOCATION)
        receipt.insert().submit()

    def _approved_transfer(
        self,
        source_location: str = SOURCE_LOCATION,
        *,
        item_code: str = ITEM,
        qty: int = 1,
        serial_no: str | None = None,
        batches: dict[str, int] | None = None,
        posting_date: str | None = None,
        posting_time: str | None = None,
    ) -> StockEntry:
        frappe.set_user(MAKER)
        transfer = cast(
            StockEntry,
            make_stock_entry(
                item_code=item_code,
                source=SOURCE,
                target=SOURCE,
                qty=qty,
                serial_no=serial_no,
                use_serial_batch_fields=1 if serial_no else 0,
                batches=batches,
                posting_date=posting_date,
                posting_time=posting_time,
                do_not_save=True,
            ),
        )
        transfer.items[0].set("storage_location", source_location)
        transfer.items[0].set("to_storage_location", TARGET_LOCATION)
        transfer.insert()
        apply_workflow(transfer, "Send Stock Transfer for Review")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")
        transfer.reload()
        return transfer

    def test_cross_warehouse_direct_transfer_is_denied_without_stock_effects(self) -> None:
        self._seed()
        destinations = frappe.get_all(
            "Warehouse",
            filters={"company": COMPANY, "is_group": 0, "disabled": 0, "name": ("!=", SOURCE)},
            pluck="name",
            limit=1,
        )
        self.assertTrue(destinations, "Integration fixture requires a second active Warehouse")
        frappe.set_user(MAKER)
        transfer = cast(
            StockEntry,
            make_stock_entry(
                item_code=ITEM,
                source=SOURCE,
                target=destinations[0],
                qty=1,
                do_not_save=True,
            ),
        )
        transfer.items[0].set("storage_location", SOURCE_LOCATION)
        transfer.items[0].set("to_storage_location", TARGET_LOCATION)
        transfer.insert()
        before = frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name})
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Send Stock Transfer for Review")
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), before)
        self.assertEqual(transfer.reload().docstatus, 0)

    def test_batch_and_serial_from_another_location_cannot_be_sent_for_review(self) -> None:
        original_setting = frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item")
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            original_setting,
        )
        base = now_datetime() - timedelta(minutes=10)
        for serial in (False, True):
            suffix = uuid4().hex[:12]
            item_code = self._tracked_item(serial=serial, suffix=suffix)
            identity = f"_TEST-OTHER-LOCATION-{suffix}"
            if serial:
                self._post_tracked_entry(
                    item_code,
                    TARGET_LOCATION,
                    qty=1,
                    posting_at=base,
                    receipt=True,
                    serial_no=identity,
                )
            else:
                frappe.get_doc({"doctype": "Batch", "item": item_code, "batch_id": identity}).insert(
                    ignore_permissions=True
                )
                self._post_tracked_entry(
                    item_code,
                    TARGET_LOCATION,
                    qty=1,
                    posting_at=base,
                    receipt=True,
                    batches={identity: 1},
                )

            frappe.set_user(MAKER)
            transfer = cast(
                StockEntry,
                make_stock_entry(
                    item_code=item_code,
                    source=SOURCE,
                    target=SOURCE,
                    qty=1,
                    serial_no=identity if serial else None,
                    use_serial_batch_fields=1 if serial else 0,
                    batches={identity: 1} if not serial else None,
                    do_not_save=True,
                ),
            )
            transfer.items[0].set("storage_location", SOURCE_LOCATION)
            transfer.items[0].set("to_storage_location", TARGET_LOCATION)
            transfer.insert()
            before = frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name})
            with self.subTest(serial=serial), self.assertRaises(frappe.ValidationError):
                apply_workflow(transfer, "Send Stock Transfer for Review")
            self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), before)
            self.assertEqual(transfer.reload().docstatus, 0)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_same_warehouse_posts_two_location_legs_and_reverses(self, _email: object) -> None:
        self._seed()
        before_source = _location_qty(SOURCE_LOCATION)
        before_target = _location_qty(TARGET_LOCATION)
        warehouse_before = _bin_qty(ITEM, SOURCE)
        transfer = self._approved_transfer()

        frappe.set_user(REVIEWER)
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 1)
        legs = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_no": transfer.name, "is_cancelled": 0},
            fields=["warehouse", "storage_location", "actual_qty"],
        )
        self.assertEqual(len(legs), 2)
        self.assertEqual(
            {(row.warehouse, row.storage_location, float(row.actual_qty)) for row in legs},
            {(SOURCE, SOURCE_LOCATION, -1.0), (SOURCE, TARGET_LOCATION, 1.0)},
        )
        self.assertEqual(_location_qty(SOURCE_LOCATION), before_source - 1)
        self.assertEqual(_location_qty(TARGET_LOCATION), before_target + 1)
        self.assertEqual(_bin_qty(ITEM, SOURCE), warehouse_before)

        apply_workflow(transfer, "Cancel Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 2)
        self.assertEqual(_location_qty(SOURCE_LOCATION), before_source)
        self.assertEqual(_location_qty(TARGET_LOCATION), before_target)
        self.assertEqual(_bin_qty(ITEM, SOURCE), warehouse_before)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_dimension_negative_stock_blocks_empty_location(self, _email: object) -> None:
        self._seed()
        transfer = self._approved_transfer(source_location=EMPTY_LOCATION)
        frappe.set_user(REVIEWER)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Submit Stock Transfer")
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name, "is_cancelled": 0}), 0
        )

    def _tracked_item(self, *, serial: bool, suffix: str) -> str:
        item_code = f"_Test Location {'Serial' if serial else 'Batch'} {suffix}"
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        self.assertTrue(item_group)
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": item_group,
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "has_serial_no": int(serial),
                "has_batch_no": int(not serial),
            }
        ).insert(ignore_permissions=True)
        return item_code

    def _post_tracked_entry(
        self,
        item_code: str,
        location: str,
        *,
        qty: int,
        posting_at: datetime,
        receipt: bool,
        serial_no: str | None = None,
        batches: dict[str, int] | None = None,
    ) -> StockEntry:
        frappe.set_user("Administrator")
        entry = cast(
            StockEntry,
            make_stock_entry(
                item_code=item_code,
                source=None if receipt else SOURCE,
                target=SOURCE if receipt else None,
                qty=qty,
                serial_no=serial_no,
                use_serial_batch_fields=1 if serial_no else 0,
                batches=batches,
                posting_date=posting_at.strftime("%Y-%m-%d"),
                posting_time=posting_at.strftime("%H:%M:%S"),
                basic_rate=100,
                do_not_save=True,
            ),
        )
        entry.items[0].set("to_storage_location" if receipt else "storage_location", location)
        entry.insert().submit()
        return entry

    def _tracked_snapshot(
        self, item_code: str, *, serial: bool
    ) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
        location_qty: dict[str, float] = defaultdict(float)
        identity_qty: dict[tuple[str, str], float] = defaultdict(float)
        ledger = frappe.get_all(
            "Stock Ledger Entry",
            filters={"item_code": item_code, "warehouse": SOURCE, "is_cancelled": 0},
            fields=[
                "name",
                "item_code",
                "warehouse",
                "storage_location",
                "voucher_type",
                "voucher_no",
                "voucher_detail_no",
                "actual_qty",
                "serial_and_batch_bundle",
            ],
        )
        self.assertEqual(len({row.name for row in ledger}), len(ledger))
        for sle in ledger:
            self.assertEqual(sle.voucher_type, "Stock Entry")
            self.assertIn(sle.storage_location, (SOURCE_LOCATION, TARGET_LOCATION))
            self.assertTrue(sle.serial_and_batch_bundle)
            location_qty[sle.storage_location] += float(sle.actual_qty)
            bundle = frappe.get_doc("Serial and Batch Bundle", sle.serial_and_batch_bundle)
            self.assertEqual(bundle.docstatus, 1)
            self.assertEqual(bundle.is_cancelled, 0)
            self.assertEqual(bundle.item_code, item_code)
            self.assertEqual(bundle.warehouse, sle.warehouse)
            self.assertEqual(bundle.voucher_type, sle.voucher_type)
            self.assertEqual(bundle.voucher_no, sle.voucher_no)
            self.assertEqual(bundle.voucher_detail_no, sle.voucher_detail_no)
            self.assertEqual(bundle.type_of_transaction, "Inward" if sle.actual_qty > 0 else "Outward")
            self.assertTrue(bundle.entries)
            self.assertAlmostEqual(sum(float(entry.qty) for entry in bundle.entries), sle.actual_qty)
            for entry in bundle.entries:
                self.assertEqual(entry.warehouse, sle.warehouse)
                self.assertEqual(entry.item_code, item_code)
                self.assertFalse(entry.is_cancelled)
                identity = entry.serial_no if serial else entry.batch_no
                self.assertTrue(identity)
                identity_qty[(sle.storage_location, identity)] += float(entry.qty)
        return dict(location_qty), dict(identity_qty)

    def _assert_helper_matches_oracle(self, item_code: str, *, serial: bool, cutoff: datetime) -> None:
        # Keep the existing native SLE/child oracle independent of the production helper.
        old_user = frappe.session.user
        frappe.set_user(REVIEWER)
        try:
            self._assert_helper_matches_oracle_as_reviewer(item_code, cutoff=cutoff)
        finally:
            frappe.set_user(old_user)

    def _assert_helper_matches_oracle_as_reviewer(self, item_code: str, *, cutoff: datetime) -> None:
        all_ledger = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "item_code": item_code,
                "warehouse": SOURCE,
                "is_cancelled": 0,
                "docstatus": 1,
                "posting_datetime": ("<=", cutoff),
            },
            fields=["storage_location", "actual_qty", "serial_and_batch_bundle"],
        )
        for location in (SOURCE_LOCATION, TARGET_LOCATION):
            expected_qty = sum(
                (Decimal(str(row.actual_qty)) for row in all_ledger if row.storage_location == location),
                Decimal(0),
            )
            expected_identities: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
            for row in all_ledger:
                if row.storage_location != location or not row.actual_qty:
                    continue
                bundle = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)
                for child in bundle.entries:
                    expected_identities[(str(child.serial_no or ""), str(child.batch_no or ""))] += Decimal(
                        str(child.qty)
                    )
            snapshot = snapshot_location(
                company=COMPANY,
                item_code=item_code,
                warehouse=SOURCE,
                storage_location=location,
                cutoff=cutoff,
            )
            self.assertEqual(snapshot.quantity, expected_qty)
            self.assertEqual(
                snapshot.identities,
                tuple(
                    sorted(
                        (serial_no, batch_no, qty)
                        for (serial_no, batch_no), qty in expected_identities.items()
                    )
                ),
            )

    def _assert_tracked_flow(self, *, serial: bool) -> None:
        suffix = uuid4().hex[:12]
        item_code = self._tracked_item(serial=serial, suffix=suffix)
        first, second, third, fourth, fifth = (f"_TEST-LOC-{suffix}-{n}" for n in range(1, 6))
        if not serial:
            for batch in (first, second):
                frappe.get_doc({"doctype": "Batch", "item": item_code, "batch_id": batch}).insert(
                    ignore_permissions=True
                )
        original_setting = frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item")
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            original_setting,
        )
        base = now_datetime() - timedelta(minutes=10)
        source_identities = (first, second, third) if serial else (first, second)
        target_identities = (fourth, fifth) if serial else (first, second)
        source_receipt = self._post_tracked_entry(
            item_code,
            SOURCE_LOCATION,
            qty=3,
            posting_at=base,
            receipt=True,
            serial_no="\n".join(source_identities) if serial else None,
            batches=None if serial else {first: 2, second: 1},
        )
        target_receipt = self._post_tracked_entry(
            item_code,
            TARGET_LOCATION,
            qty=2,
            posting_at=base + timedelta(minutes=2),
            receipt=True,
            serial_no="\n".join(target_identities) if serial else None,
            batches=None if serial else {first: 1, second: 1},
        )
        issue = self._post_tracked_entry(
            item_code,
            SOURCE_LOCATION,
            qty=1,
            posting_at=base + timedelta(minutes=4),
            receipt=False,
            serial_no=third if serial else None,
            batches=None if serial else {first: 1},
        )
        self._assert_helper_matches_oracle(item_code, serial=serial, cutoff=base + timedelta(minutes=3))
        before_locations, before_identities = self._tracked_snapshot(item_code, serial=serial)
        self._assert_helper_matches_oracle(item_code, serial=serial, cutoff=base + timedelta(minutes=5))
        self.assertEqual(before_locations, {SOURCE_LOCATION: 2, TARGET_LOCATION: 2})
        positive_identities = {key: value for key, value in before_identities.items() if value > 0}
        self.assertTrue(all(value == 1 for value in positive_identities.values()))
        self.assertEqual(len(positive_identities), 4)
        self.assertTrue(all(value >= 0 for value in before_identities.values()))
        for entry in (source_receipt, target_receipt, issue):
            self.assertEqual(
                frappe.db.count("Stock Ledger Entry", {"voucher_no": entry.name, "is_cancelled": 0}),
                1,
            )
        transfer_at = base + timedelta(minutes=6)
        transfer = self._approved_transfer(
            item_code=item_code,
            qty=2,
            serial_no=f"{first}\n{second}" if serial else None,
            batches=None if serial else {first: 1, second: 1},
            posting_date=transfer_at.strftime("%Y-%m-%d"),
            posting_time=transfer_at.strftime("%H:%M:%S"),
        )
        frappe.set_user(REVIEWER)
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 1)
        active_legs = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_no": transfer.name, "is_cancelled": 0},
            fields=[
                "name",
                "storage_location",
                "actual_qty",
                "qty_after_transaction",
                "voucher_detail_no",
                "serial_and_batch_bundle",
            ],
        )
        self.assertEqual(len(active_legs), 2)
        self.assertEqual(
            {(row.storage_location, float(row.actual_qty)) for row in active_legs},
            {(SOURCE_LOCATION, -2.0), (TARGET_LOCATION, 2.0)},
        )
        self.assertTrue(
            any(
                row.storage_location == SOURCE_LOCATION and float(row.qty_after_transaction) != 0
                for row in active_legs
            ),
            "Warehouse running quantity must not be used as exact Location quantity",
        )
        after_locations, after_identities = self._tracked_snapshot(item_code, serial=serial)
        self._assert_helper_matches_oracle(item_code, serial=serial, cutoff=transfer_at)
        self.assertEqual(after_locations, {SOURCE_LOCATION: 0, TARGET_LOCATION: 4})
        self.assertEqual(sum(after_identities.values()), 4)
        self.assertEqual(after_identities[(TARGET_LOCATION, first)], 2 if not serial else 1)
        self.assertEqual(after_identities[(TARGET_LOCATION, second)], 2 if not serial else 1)

        apply_workflow(transfer, "Cancel Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 2)
        self.assertEqual(
            self._tracked_snapshot(item_code, serial=serial), (before_locations, before_identities)
        )
        self._assert_helper_matches_oracle(item_code, serial=serial, cutoff=transfer_at)
        cancelled_legs = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_no": transfer.name},
            fields=[
                "name",
                "storage_location",
                "actual_qty",
                "voucher_detail_no",
                "serial_and_batch_bundle",
                "is_cancelled",
            ],
        )
        self.assertEqual(len(cancelled_legs), 4)
        self.assertTrue(all(row.is_cancelled for row in cancelled_legs))
        self.assertTrue(all(not row.serial_and_batch_bundle for row in cancelled_legs))
        self.assertTrue({row.name for row in active_legs}.issubset({row.name for row in cancelled_legs}))
        for original in active_legs:
            matching = [
                row
                for row in cancelled_legs
                if row.name != original.name
                and row.storage_location == original.storage_location
                and row.voucher_detail_no == original.voucher_detail_no
                and float(row.actual_qty) == -float(original.actual_qty)
            ]
            self.assertEqual(len(matching), 1)
            bundle = frappe.get_doc("Serial and Batch Bundle", original.serial_and_batch_bundle)
            self.assertEqual(bundle.voucher_no, transfer.name)
            self.assertEqual(bundle.voucher_detail_no, original.voucher_detail_no)
            self.assertEqual(bundle.is_cancelled, 1)
            self.assertTrue(all(entry.is_cancelled for entry in bundle.entries))

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_batch_identity_location_ledger_and_cancellation(self, _email: object) -> None:
        self._assert_tracked_flow(serial=False)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_serial_identity_location_ledger_and_cancellation(self, _email: object) -> None:
        self._assert_tracked_flow(serial=True)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_batch_stock_reconciliation_has_current_and_target_location_legs(self, _email: object) -> None:
        suffix = uuid4().hex[:12]
        item_code = self._tracked_item(serial=False, suffix=suffix)
        batch = f"_TEST-LOC-SR-{suffix}"
        frappe.get_doc({"doctype": "Batch", "item": item_code, "batch_id": batch}).insert(
            ignore_permissions=True
        )
        original_setting = frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item")
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            original_setting,
        )
        base = now_datetime() - timedelta(minutes=10)
        self._post_tracked_entry(
            item_code,
            SOURCE_LOCATION,
            qty=3,
            posting_at=base,
            receipt=True,
            batches={batch: 3},
        )
        self._assert_helper_matches_oracle(item_code, serial=False, cutoff=base)
        posting_at = base + timedelta(minutes=2)
        new_bundle = make_serial_batch_bundle(
            frappe._dict(
                item_code=item_code,
                warehouse=SOURCE,
                qty=4,
                voucher_type="Stock Reconciliation",
                batches={batch: 4},
                rate=100,
                posting_date=posting_at.strftime("%Y-%m-%d"),
                posting_time=posting_at.strftime("%H:%M:%S"),
                company=COMPANY,
                do_not_submit=True,
            )
        )
        frappe.set_user(RECONCILIATION_MAKER)
        reconciliation = frappe.get_doc(
            {
                "doctype": "Stock Reconciliation",
                "company": COMPANY,
                "purpose": "Stock Reconciliation",
                "set_posting_time": 1,
                "posting_date": posting_at.strftime("%Y-%m-%d"),
                "posting_time": posting_at.strftime("%H:%M:%S"),
                "expense_account": frappe.get_cached_value("Company", COMPANY, "stock_adjustment_account")
                or frappe.get_cached_value(
                    "Account", {"account_type": "Stock Adjustment", "company": COMPANY}, "name"
                ),
                "cost_center": frappe.get_cached_value("Company", COMPANY, "cost_center")
                or frappe.get_cached_value("Cost Center", {"is_group": 0, "company": COMPANY}, "name"),
                "items": [
                    {
                        "item_code": item_code,
                        "warehouse": SOURCE,
                        "storage_location": SOURCE_LOCATION,
                        "qty": 4,
                        "valuation_rate": 100,
                        "reconcile_all_serial_batch": 0,
                        "batch_no": batch,
                        "serial_and_batch_bundle": new_bundle.name,
                    }
                ],
            }
        )
        reconciliation.insert()
        apply_workflow(reconciliation, "Send Stock Reconciliation for Review")
        pending = frappe.get_doc("Stock Reconciliation", reconciliation.name)
        pending.set("workflow_state", "Stock Reconciliation Reviewed")
        pending.set("approval_reviewer_user", MAKER)
        with self.assertRaises(frappe.ValidationError):
            pending.save()
        reconciliation.reload()
        self.assertEqual(reconciliation.workflow_state, "Stock Reconciliation Pending Review")
        self.assertFalse(reconciliation.approval_reviewer_user)
        frappe.set_user(REVIEWER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Review Stock Reconciliation")
        self.assertEqual(reconciliation.approval_maker_user, RECONCILIATION_MAKER)
        self.assertEqual(reconciliation.approval_reviewer_user, REVIEWER)
        self.assertTrue(reconciliation.checked_by)
        self.assertTrue(reconciliation.checked_signature)
        stale = frappe.get_doc("Stock Reconciliation", reconciliation.name)
        stale.items[0].qty = 5
        with self.assertRaises(frappe.ValidationError):
            stale.save()
        reconciliation.reload()
        self.assertEqual(reconciliation.items[0].qty, 4)
        frappe.set_user(RECONCILIATION_APPROVER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Return Stock Reconciliation")
        reconciliation.reload()
        self.assertEqual(reconciliation.approval_maker_user, RECONCILIATION_MAKER)
        self.assertFalse(reconciliation.approval_reviewer_user)
        self.assertFalse(reconciliation.checked_signature)
        frappe.set_user(RECONCILIATION_MAKER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Resubmit Stock Reconciliation for Review")
        frappe.set_user(REVIEWER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Review Stock Reconciliation")
        frappe.set_user(RECONCILIATION_APPROVER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Approve Stock Reconciliation")
        reconciliation.reload()
        self.assertEqual(reconciliation.approval_authorized_user, RECONCILIATION_APPROVER)
        self.assertTrue(reconciliation.authorized_by)
        self.assertTrue(reconciliation.authorized_signature)
        forged = reconciliation.as_dict()
        forged["workflow_state"] = "Stock Reconciliation Submitted"
        with self.assertRaises(Exception):
            frappe_client.save(forged)
        reconciliation.reload()
        self.assertEqual(reconciliation.docstatus, 0)
        frappe.set_user(REVIEWER)
        reconciliation.reload()
        apply_workflow(reconciliation, "Post Stock Reconciliation")
        reconciliation.reload()
        self.assertEqual(reconciliation.docstatus, 1)
        submitted = frappe.get_doc("Stock Reconciliation", reconciliation.name)
        submitted.set("workflow_state", "Stock Reconciliation Cancelled")
        with self.assertRaises(Exception):
            submitted.save()
        with self.assertRaises(Exception):
            frappe_client.set_value(
                "Stock Reconciliation", reconciliation.name, "approval_authorized_user", MAKER
            )
        reconciliation.reload()
        self.assertEqual(reconciliation.workflow_state, "Stock Reconciliation Submitted")
        self.assertEqual(reconciliation.approval_authorized_user, RECONCILIATION_APPROVER)
        legs = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_no": reconciliation.name, "is_cancelled": 0},
            fields=["actual_qty", "serial_and_batch_bundle", "storage_location"],
        )
        self.assertEqual(len(legs), 2)
        self.assertEqual({float(row.actual_qty) for row in legs}, {-3.0, 4.0})
        self.assertTrue(all(row.serial_and_batch_bundle for row in legs))
        self.assertTrue(all(row.storage_location == SOURCE_LOCATION for row in legs))
        self._assert_helper_matches_oracle(item_code, serial=False, cutoff=base)
        self._assert_helper_matches_oracle(item_code, serial=False, cutoff=posting_at)
        self.assertEqual(
            snapshot_location(
                company=COMPANY,
                item_code=item_code,
                warehouse=SOURCE,
                storage_location=SOURCE_LOCATION,
                cutoff=posting_at,
            ).quantity,
            Decimal(4),
        )
        apply_workflow(reconciliation, "Cancel Stock Reconciliation")
        reconciliation.reload()
        self.assertEqual(reconciliation.docstatus, 2)
        self._assert_helper_matches_oracle(item_code, serial=False, cutoff=posting_at)
        self.assertEqual(
            snapshot_location(
                company=COMPANY,
                item_code=item_code,
                warehouse=SOURCE,
                storage_location=SOURCE_LOCATION,
                cutoff=posting_at,
            ).quantity,
            Decimal(3),
        )
