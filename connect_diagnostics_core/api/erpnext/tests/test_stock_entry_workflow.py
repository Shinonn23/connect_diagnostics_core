# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks as app_hooks
from connect_diagnostics_core.api.erpnext import stock_count_session_workflow, stock_entry_workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestCountStockEntryAdapter(UnitTestCase):
    def _candidate(self) -> StockEntry:
        return cast(
            StockEntry,
            frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "purpose": "Material Transfer",
                    "stock_count_session": "COUNT-1",
                    "items": [{"item_code": "ITEM-A", "qty": 1}],
                }
            ),
        )

    def test_count_lifecycle_requires_domain_verification_before_leaving_ordinary_route(self) -> None:
        callbacks = (
            (stock_entry_workflow.validate_workflow, "validate"),
            (stock_entry_workflow.validate_before_submit, "before_submit"),
            (stock_entry_workflow.validate_before_cancel, "before_cancel"),
            (stock_entry_workflow.validate_after_submit_update, "before_update_after_submit"),
        )
        for callback, phase in callbacks:
            doc = self._candidate()
            with (
                patch.object(stock_count_session_workflow, "guard_count_stock_entry") as verify,
                patch.object(stock_entry_workflow, "_reject_excluded_material_transfer") as ordinary,
            ):
                callback(doc)
                verify.assert_called_once_with(doc, phase)
                ordinary.assert_not_called()
            with self.assertRaises(frappe.ValidationError):
                callback(doc)

    def test_count_and_emergency_markers_cannot_share_authority(self) -> None:
        for field in (
            stock_entry_workflow.EXCEPTION_FLAG,
            stock_entry_workflow.EXCEPTION_REASON,
            stock_entry_workflow.EXCEPTION_SCOPE,
        ):
            doc = self._candidate()
            doc.set(field, "1")
            with (
                patch.object(stock_count_session_workflow, "guard_count_stock_entry") as verify,
                self.assertRaises(frappe.ValidationError),
            ):
                stock_entry_workflow.validate_before_submit(doc)
            verify.assert_not_called()


class TestStockEntryWorkflow(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        # These tests isolate ordinary transfer approval, including its DB mocks.
        detector = patch.object(stock_count_session_workflow, "is_count_stock_entry", return_value=False)
        detector.start()
        self.addCleanup(detector.stop)
        for name in ("require_operational_warehouse", "require_location_warehouse"):
            location_guard = patch.object(stock_entry_workflow, name)
            location_guard.start()
            self.addCleanup(location_guard.stop)

    def _transfer(self, source: str = "SOURCE", target: str = "SOURCE") -> StockEntry:
        return cast(
            StockEntry,
            frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "purpose": "Material Transfer",
                    "items": [
                        {
                            "item_code": "ITEM-A",
                            "s_warehouse": source,
                            "t_warehouse": target,
                            "storage_location": "LOC-A",
                            "to_storage_location": "LOC-B",
                            "qty": 1,
                        }
                    ],
                }
            ),
        )

    def _capture_submit_identity(
        self,
        doc: StockEntry,
        tracked: dict[str, dict[tuple[str, str], Decimal]] | None = None,
    ) -> None:
        digest = "approved-digest"
        doc.set("approval_critical_digest", digest)
        doc.flags[stock_entry_workflow._SUBMIT_IDENTITY_CAPTURE] = {
            "name": doc.name,
            "approval_critical_digest": digest,
            "tracked_identities": tracked or {},
        }

    def test_on_submit_hook_verifies_native_stock_ledger_location_and_quantity(self) -> None:
        doc = self._transfer()
        doc.name = "SE-POSTED-1"
        doc.docstatus = 1
        row = doc.items[0]
        row.name = "SE-ROW-1"
        row.set("transfer_qty", 2)
        self._capture_submit_identity(doc)
        ledger = [
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=-2,
                storage_location="LOC-A",
                serial_and_batch_bundle=None,
            ),
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=2,
                storage_location="LOC-B",
                serial_and_batch_bundle=None,
            ),
        ]
        with (
            patch.object(stock_entry_workflow.frappe, "get_all", return_value=ledger),
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=0),
            ),
        ):
            stock_entry_workflow.validate_after_submit(doc)
            self.assertFalse(doc.flags.get(stock_entry_workflow._SUBMIT_IDENTITY_CAPTURE))
            self._capture_submit_identity(doc)
            ledger[1].storage_location = "WRONG-LOCATION"
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_after_submit(doc)

    def test_on_submit_hook_verifies_batch_bundle_identity_on_both_ledger_legs(self) -> None:
        doc = self._transfer()
        doc.name = "SE-POSTED-BATCH"
        doc.docstatus = 1
        row = doc.items[0]
        row.name = "SE-BATCH-ROW"
        row.set("transfer_qty", 2)
        row.set("batch_no", "BATCH-A")
        row.set("serial_and_batch_bundle", "NATIVE-GENERATED-BUNDLE")
        self._capture_submit_identity(
            doc,
            {row.name: {("", "BATCH-A"): Decimal(2)}},
        )
        ledger = [
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=-2,
                storage_location="LOC-A",
                serial_and_batch_bundle="BUNDLE-OUT",
            ),
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=2,
                storage_location="LOC-B",
                serial_and_batch_bundle="BUNDLE-IN",
            ),
        ]
        bundles = [
            frappe._dict(
                name="BUNDLE-OUT",
                item_code="ITEM-A",
                warehouse="SOURCE",
                type_of_transaction="Outward",
                total_qty=-2,
            ),
            frappe._dict(
                name="BUNDLE-IN",
                item_code="ITEM-A",
                warehouse="SOURCE",
                type_of_transaction="Inward",
                total_qty=2,
            ),
        ]
        entries = [
            frappe._dict(parent="BUNDLE-OUT", serial_no=None, batch_no="BATCH-A", qty=-2),
            frappe._dict(parent="BUNDLE-IN", serial_no=None, batch_no="BATCH-A", qty=2),
        ]
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_all",
                side_effect=[ledger, bundles, entries, ledger, bundles, entries],
            ),
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
        ):
            stock_entry_workflow.validate_after_submit(doc)
            self._capture_submit_identity(
                doc,
                {row.name: {("", "BATCH-A"): Decimal(2)}},
            )
            entries[1].batch_no = "BATCH-WRONG"
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_after_submit(doc)

    def test_stock_entry_submit_hook_registers_native_ledger_verifier(self) -> None:
        handlers = app_hooks.doc_events["Stock Entry"]["on_submit"]
        self.assertIn("connect_diagnostics_core.api.erpnext.stock_borrow.on_submit", handlers)
        self.assertIn(
            "connect_diagnostics_core.api.erpnext.stock_entry_workflow.validate_after_submit",
            handlers,
        )

    def test_on_submit_hook_verifies_legacy_batch_identity_without_bundle(self) -> None:
        doc = self._transfer()
        doc.name = "SE-POSTED-LEGACY-BATCH"
        doc.docstatus = 1
        row = doc.items[0]
        row.name = "SE-LEGACY-BATCH-ROW"
        row.set("transfer_qty", 2)
        row.set("batch_no", "BATCH-A")
        self._capture_submit_identity(
            doc,
            {row.name: {("", "BATCH-A"): Decimal(2)}},
        )
        ledger = [
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=-2,
                storage_location="LOC-A",
                serial_and_batch_bundle=None,
                serial_no=None,
                batch_no="BATCH-A",
            ),
            frappe._dict(
                voucher_detail_no=row.name,
                item_code="ITEM-A",
                warehouse="SOURCE",
                actual_qty=2,
                storage_location="LOC-B",
                serial_and_batch_bundle=None,
                serial_no=None,
                batch_no="BATCH-A",
            ),
        ]
        with (
            patch.object(stock_entry_workflow.frappe, "get_all", return_value=ledger),
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
        ):
            stock_entry_workflow.validate_after_submit(doc)
            self._capture_submit_identity(
                doc,
                {row.name: {("", "BATCH-A"): Decimal(2)}},
            )
            ledger[1].batch_no = "BATCH-WRONG"
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_after_submit(doc)

    def test_tracked_stock_digest_uses_converted_stock_uom_precision(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        doc.posting_time = "10:00:00"
        row = doc.items[0]
        row.set("storage_location", "LOC-A")
        row.set("to_storage_location", "LOC-B")
        row.set("qty", Decimal("0.333333"))
        row.set("conversion_factor", Decimal("6"))
        row.set("transfer_qty", Decimal("1.999998"))
        row.set("batch_no", "BATCH-A")
        snapshot = frappe._dict(identities=(("", "BATCH-A", Decimal("2.000000")),))
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow, "snapshot_location", return_value=snapshot) as lock,
        ):
            digest = stock_entry_workflow.get_approval_digest(doc)
        self.assertTrue(digest)
        lock.assert_called_once()
        self.assertTrue(lock.call_args.kwargs["locking_read"])
        self.assertEqual(
            stock_entry_workflow._requested_tracked_identities(
                row, frappe._dict(has_serial_no=0, has_batch_no=1)
            ),
            {("", "BATCH-A"): Decimal("1.999998")},
        )

    def test_wrong_location_batch_is_denied_before_review_and_approval_writes(self) -> None:
        doc = self._transfer()
        doc.name = "SE-WRONG-LOCATION-REVIEW"
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        row = doc.items[0]
        row.set("batch_no", "BATCH-A")
        row.set("transfer_qty", 1)
        doc.set("approval_critical_digest", "old-digest")
        wrong_location = frappe._dict(identities=(("", "OTHER-BATCH", Decimal(1)),))
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow, "snapshot_location", return_value=wrong_location),
            patch.object(stock_entry_workflow, "authorize_approval_field_write") as authorize,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.capture_review_snapshot(doc)
        authorize.assert_not_called()
        self.assertFalse(doc.get("approval_reviewer_user"))

        doc.name = "SE-WRONG-LOCATION-APPROVE"
        doc.set("approval_reviewer_user", "checker@example.com")
        doc.set("checked_by", "Checker")
        doc.set("checked_at", "2026-10-03 10:00:00")
        doc.set("checked_signature", "signed-review")
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow, "snapshot_location", return_value=wrong_location),
            patch.object(stock_entry_workflow, "authorize_approval_field_write") as authorize,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.capture_approval_snapshot(doc)
        authorize.assert_not_called()
        self.assertFalse(doc.get("approval_authorized_user"))

    def test_wrong_location_batch_is_denied_before_native_submit(self) -> None:
        doc = self._transfer()
        doc.name = "SE-WRONG-LOCATION-SUBMIT"
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        doc.set("workflow_state", "Stock Transfer Approved")
        doc.items[0].set("batch_no", "BATCH-A")
        doc.items[0].set("transfer_qty", 1)
        values = {field: f"signed-{field}" for field in stock_entry_workflow._APPROVAL_FIELDS}
        values["approval_critical_digest"] = "approved-digest"
        values["approval_maker_user"] = "maker@example.com"
        values["approval_reviewer_user"] = "checker@example.com"
        values["approval_authorized_user"] = "approver@example.com"
        for field, value in values.items():
            doc.set(field, value)
        persisted = frappe._dict(workflow_state="Stock Transfer Approved", **values)
        wrong_location = frappe._dict(identities=(("", "OTHER-BATCH", Decimal(1)),))
        with (
            patch.object(stock_entry_workflow, "validate_workflow"),
            patch.object(stock_entry_workflow, "resolve_user", return_value="manager@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "_validate_transfer_locations"),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow, "snapshot_location", return_value=wrong_location),
            patch.object(stock_entry_workflow, "consume_approval_field_grant") as consume,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_submit(doc)
        consume.assert_not_called()
        self.assertFalse(doc.flags.get(stock_entry_workflow._SUBMIT_IDENTITY_CAPTURE))

    def test_raw_terminal_state_requires_native_status(self) -> None:
        doc = self._transfer()
        doc.name = "STE-1"
        doc.set("workflow_state", "Stock Transfer Submitted")
        doc.docstatus = 0
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(doc)
        doc.set("workflow_state", "Stock Transfer Cancelled")
        doc.docstatus = 1
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(doc)

    def test_submitted_transfer_update_guard_preserves_general_legacy_route(self) -> None:
        current = self._transfer()
        current.name = "STE-1"
        current.docstatus = 1
        current.set("workflow_state", "Stock Entry Submitted")
        previous = deepcopy(current)
        with (
            patch.object(current, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "require_locked_submitted_update") as locked,
        ):
            stock_entry_workflow.validate_after_submit_update(current)
            locked.assert_not_called()
            previous.set("workflow_state", "Stock Transfer Submitted")
            locked.side_effect = frappe.ValidationError
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_after_submit_update(current)
            locked.assert_called_once_with(current, "Stock Transfer Submitted")
            locked.side_effect = None
            current.set("workflow_state", "Stock Transfer Submitted")
            current.set("add_to_transit", 1)
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_after_submit_update(current)

    def test_direct_transfer_must_stay_in_one_warehouse(self) -> None:
        doc = self._transfer("SOURCE", "TARGET")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow._validate_transfer_locations(doc)

    def test_same_warehouse_transfer_requires_exact_distinct_locations(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.items[0].set("storage_location", None)
        doc.items[0].set("to_storage_location", None)
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow._validate_transfer_locations(doc)
        doc.items[0].set("storage_location", "LOC-A")
        doc.items[0].set("to_storage_location", "LOC-B")
        with (
            patch.object(stock_entry_workflow, "require_operational_warehouse"),
            patch.object(stock_entry_workflow, "require_location_warehouse"),
        ):
            stock_entry_workflow._validate_transfer_locations(doc)

    def test_cross_warehouse_transfer_is_rejected_even_with_locations(self) -> None:
        doc = self._transfer("SOURCE", "TARGET")
        doc.items[0].set("storage_location", "LOC-A")
        doc.items[0].set("to_storage_location", "LOC-B")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow._validate_transfer_locations(doc)

    def test_same_warehouse_requires_distinct_locations(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.items[0].set("storage_location", None)
        doc.items[0].set("to_storage_location", None)
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.capture_review_snapshot(doc)
        doc.items[0].set("storage_location", "LOC-A")
        doc.items[0].set("to_storage_location", "LOC-A")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.capture_review_snapshot(doc)

    def test_one_sided_location_is_rejected_at_native_submit_boundary(self) -> None:
        doc = self._transfer()
        doc.set("workflow_state", "Stock Transfer Submitted")
        doc.items[0].set("to_storage_location", None)
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Approved")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_submit(doc)

    def test_location_values_bind_digest_and_warehouse_ownership(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.items[0].set("storage_location", "LOC-A")
        doc.items[0].set("to_storage_location", "LOC-B")
        baseline = stock_entry_workflow.get_approval_digest(doc)
        doc.items[0].set("to_storage_location", "LOC-C")
        self.assertNotEqual(baseline, stock_entry_workflow.get_approval_digest(doc))
        doc.items[0].set("storage_location", "LOC-D")
        self.assertNotEqual(baseline, stock_entry_workflow.get_approval_digest(doc))
        with (
            patch.object(stock_entry_workflow, "require_operational_warehouse") as warehouse,
            patch.object(stock_entry_workflow, "require_location_warehouse") as location,
        ):
            stock_entry_workflow._validate_transfer_locations(doc)
        warehouse.assert_called_once_with("SOURCE")
        self.assertEqual(
            [call.args for call in location.call_args_list],
            [("LOC-D", "SOURCE"), ("LOC-C", "SOURCE")],
        )

    def test_tracked_source_digest_binds_selected_identity_and_available_stock_uom_qty(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        doc.posting_time = "10:00:00"
        row = doc.items[0]
        row.set("storage_location", "LOC-A")
        row.set("to_storage_location", "LOC-B")
        row.set("batch_no", "BATCH-A")
        row.set("transfer_qty", 2)
        first = frappe._dict(identities=(("", "BATCH-A", Decimal(3)),))
        changed = frappe._dict(identities=(("", "BATCH-A", Decimal(2)),))
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow, "snapshot_location", side_effect=[first, changed]) as snapshot,
        ):
            original = stock_entry_workflow.get_approval_digest(doc)
            updated = stock_entry_workflow.get_approval_digest(doc)
        self.assertNotEqual(original, updated)
        self.assertTrue(all(call.kwargs["locking_read"] for call in snapshot.call_args_list))

    def test_locked_bundle_projection_rejects_revoked_or_concurrently_changed_bundle(self) -> None:
        row = self._transfer().items[0]
        row.set("transfer_qty", 2)
        row.set("serial_and_batch_bundle", "BUNDLE-SOURCE")
        item = frappe._dict(has_serial_no=0, has_batch_no=1)
        with (
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=None) as get_bundle,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow._requested_tracked_identities(row, item)
        self.assertTrue(get_bundle.call_args_list[0].kwargs["for_update"])
        self.assertFalse(get_bundle.call_args_list[0].kwargs["wait"])

        with (
            patch.object(
                stock_entry_workflow.frappe.db,
                "get_value",
                side_effect=frappe.QueryTimeoutError,
            ),
            patch.object(
                stock_entry_workflow,
                "lock_conflict",
                side_effect=frappe.ValidationError,
            ) as conflict,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow._requested_tracked_identities(row, item)
        conflict.assert_called_once_with()

    def test_changed_bundle_identity_is_rejected_by_exact_location_snapshot(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        row = doc.items[0]
        row.set("storage_location", "LOC-A")
        row.set("to_storage_location", "LOC-B")
        row.set("transfer_qty", 1)
        row.set("serial_and_batch_bundle", "BUNDLE-SOURCE")
        header = frappe._dict(
            docstatus=0,
            is_cancelled=0,
            item_code="ITEM-A",
            warehouse="SOURCE",
            type_of_transaction="Outward",
            total_qty=-1,
        )
        entries = [frappe._dict(serial_no=None, batch_no="BATCH-CHANGED", qty=-1)]
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=header) as get_bundle,
            patch.object(stock_entry_workflow.frappe.db, "get_values", return_value=entries) as get_entries,
            patch.object(
                stock_entry_workflow,
                "snapshot_location",
                return_value=frappe._dict(identities=(("", "BATCH-CHANGED", Decimal(0)),)),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.get_approval_digest(doc)
        self.assertTrue(get_bundle.call_args.kwargs["for_update"])
        self.assertTrue(get_entries.call_args.kwargs["for_update"])
        self.assertFalse(get_bundle.call_args.kwargs["wait"])
        self.assertFalse(get_entries.call_args.kwargs["wait"])

    def test_serial_from_another_location_is_rejected_by_locked_projection(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        row = doc.items[0]
        row.set("storage_location", "LOC-A")
        row.set("to_storage_location", "LOC-B")
        row.set("transfer_qty", 1)
        row.set("serial_no", "SERIAL-OTHER-LOCATION")
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=1, has_batch_no=0),
            ),
            patch.object(
                stock_entry_workflow,
                "snapshot_location",
                return_value=frappe._dict(identities=(("SERIAL-OTHER-LOCATION", "", Decimal(0)),)),
            ) as snapshot,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.get_approval_digest(doc)
        self.assertTrue(snapshot.call_args.kwargs["locking_read"])

    def test_wrong_location_serial_is_rejected_at_maker_review_approval_and_submit(self) -> None:
        stages = (
            "maker",
            "review",
            "approval",
            "submit",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                route = MagicMock(
                    draft_state="Stock Entry Draft",
                    returned_state="Stock Transfer Returned",
                    pending_review_state="Stock Transfer Pending Review",
                    maker_roles=("Stock User",),
                    send_action="Send Stock Transfer for Review",
                    resubmit_action="Resubmit Stock Transfer for Review",
                    approved_state="Stock Transfer Approved",
                    execution_roles=("Stock Manager",),
                    execute_action="Submit Stock Transfer",
                )
                doc = self._transfer()
                doc.name = "SE-WRONG-LOCATION-SERIAL"
                doc.company = "COMPANY"
                doc.posting_date = "2026-10-03"
                doc.set("approval_maker_user", "maker@example.com")
                row = doc.items[0]
                row.set("storage_location", "LOC-A")
                row.set("to_storage_location", "LOC-B")
                row.set("transfer_qty", 1)
                row.set("serial_no", "SERIAL-OTHER-LOCATION")
                if stage == "maker":
                    doc.set("workflow_state", "Stock Transfer Pending Review")
                    stored = frappe._dict(
                        workflow_state="Stock Entry Draft", docstatus=0, approval_maker_user=None
                    )
                elif stage == "submit":
                    doc.set("workflow_state", "Stock Transfer Submitted")
                    stored = frappe._dict(workflow_state="Stock Transfer Approved")
                else:
                    stored = frappe._dict()

                with (
                    patch.object(
                        stock_entry_workflow.frappe,
                        "get_cached_value",
                        return_value=frappe._dict(has_serial_no=1, has_batch_no=0),
                    ),
                    patch.object(
                        stock_entry_workflow,
                        "snapshot_location",
                        return_value=frappe._dict(identities=(("SERIAL-OTHER-LOCATION", "", Decimal(0)),)),
                    ),
                    patch.object(stock_entry_workflow, "get_route", return_value=route),
                    patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=stored),
                    patch.object(
                        stock_entry_workflow,
                        "authorize_workflow_field_write",
                        return_value="maker@example.com",
                    ),
                    patch.object(stock_entry_workflow, "authorize_approval_field_write") as sign,
                    patch.object(stock_entry_workflow, "validate_workflow"),
                    patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
                    patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
                    patch.object(stock_entry_workflow, "require_permission"),
                    patch.object(stock_entry_workflow, "require_distinct_actors"),
                    patch.object(stock_entry_workflow, "consume_approval_field_grant"),
                    self.assertRaises(frappe.ValidationError),
                ):
                    if stage == "maker":
                        stock_entry_workflow.capture_maker_snapshot(doc)
                    elif stage == "review":
                        stock_entry_workflow.capture_review_snapshot(doc)
                    elif stage == "approval":
                        stock_entry_workflow.capture_approval_snapshot(doc)
                    else:
                        stock_entry_workflow.validate_before_submit(doc)
                sign.assert_not_called()

    def test_submit_capture_reuses_the_exact_projection_bound_into_approval_digest(self) -> None:
        doc = self._transfer()
        doc.name = "SE-APPROVED-PROJECTION"
        doc.set("workflow_state", "Stock Transfer Submitted")
        doc.set("approval_critical_digest", "approved-digest")
        doc.docstatus = 0
        projection = {"ROW-1": {("", "BATCH-A"): Decimal(2)}}
        source_snapshot = [{"row": "ROW-1", "identities": [("", "BATCH-A", "2", "4")]}]
        persisted = {
            "workflow_state": "Stock Transfer Approved",
            "approval_maker_user": "maker@example.com",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "approval_critical_digest": "approved-digest",
            "checked_by": "EMP-CHECKER",
            "checked_at": datetime(2026, 9, 19),
            "checked_signature": "reviewer-signature",
            "authorized_by": "EMP-APPROVER",
            "authorized_at": datetime(2026, 9, 19),
            "authorized_signature": "approver-signature",
        }
        for field, value in persisted.items():
            if field != "workflow_state":
                doc.set(field, value)
        route = MagicMock(approved_state="Stock Transfer Approved", execution_roles=("Stock Manager",))
        with (
            patch.object(stock_entry_workflow, "validate_workflow"),
            patch.object(stock_entry_workflow, "get_route", return_value=route),
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "_validate_transfer_locations"),
            patch.object(stock_entry_workflow, "require_distinct_actors"),
            patch.object(stock_entry_workflow, "consume_approval_field_grant"),
            patch.object(
                stock_entry_workflow, "_tracked_source_projection", return_value=(projection, source_snapshot)
            ) as build_projection,
            patch.object(stock_entry_workflow, "_approval_digest", return_value="approved-digest") as digest,
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=persisted),
        ):
            stock_entry_workflow.validate_before_submit(doc)
        build_projection.assert_called_once_with(doc)
        digest.assert_called_once_with(doc, source_snapshot)
        capture = doc.flags[stock_entry_workflow._SUBMIT_IDENTITY_CAPTURE]
        self.assertEqual(capture["tracked_identities"], projection)
        self.assertEqual(capture["approval_critical_digest"], "approved-digest")

    def test_tracked_source_snapshot_rejects_identity_outside_exact_location(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.company = "COMPANY"
        doc.posting_date = "2026-10-03"
        row = doc.items[0]
        row.set("storage_location", "LOC-A")
        row.set("to_storage_location", "LOC-B")
        row.set("batch_no", "BATCH-OTHER-LOCATION")
        row.set("transfer_qty", 1)
        with (
            patch.object(
                stock_entry_workflow.frappe,
                "get_cached_value",
                return_value=frappe._dict(has_serial_no=0, has_batch_no=1),
            ),
            patch.object(
                stock_entry_workflow,
                "snapshot_location",
                return_value=frappe._dict(identities=(("", "BATCH-OTHER-LOCATION", Decimal(0)),)),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.get_approval_digest(doc)

    def test_location_read_denial_blocks_review(self) -> None:
        doc = self._transfer("SOURCE", "SOURCE")
        doc.items[0].set("storage_location", "LOC-A")
        doc.items[0].set("to_storage_location", "LOC-B")
        with (
            patch.object(stock_entry_workflow, "require_operational_warehouse"),
            patch.object(
                stock_entry_workflow, "require_location_warehouse", side_effect=frappe.PermissionError
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            stock_entry_workflow.capture_review_snapshot(doc)

    def test_direct_transfer_requires_approval(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Entry Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_before_submit(doc)

    def test_direct_transfer_starts_in_generic_entry_draft(self) -> None:
        doc = self._transfer()
        doc.set("workflow_state", "Stock Entry Draft")
        with patch.object(doc, "is_new", return_value=True):
            stock_entry_workflow.validate_workflow(doc)

    def test_direct_transfer_cannot_submit_from_generic_state(self) -> None:
        doc = self._transfer()
        doc.set("workflow_state", "Stock Entry Submitted")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_before_submit(doc)

    def test_transit_material_transfer_fails_closed_at_every_boundary(self) -> None:
        boundaries = (
            stock_entry_workflow.validate_workflow,
            stock_entry_workflow.authorize_submit_execution,
            stock_entry_workflow.authorize_cancel_execution,
            stock_entry_workflow.validate_before_submit,
            stock_entry_workflow.validate_before_cancel,
        )
        for transit_field, value in (("add_to_transit", 1), ("outgoing_stock_entry", "STE-OUT")):
            for boundary in boundaries:
                with self.subTest(transit_field=transit_field, boundary=boundary.__name__):
                    doc = self._transfer()
                    doc.set("workflow_state", "Stock Entry Draft")
                    doc.set(transit_field, value)
                    with self.assertRaises(frappe.ValidationError):
                        boundary(doc)

    def test_reviewed_transfer_cannot_escape_by_transit_flag_or_purpose(self) -> None:
        for change in (
            {"add_to_transit": 1},
            {"outgoing_stock_entry": "STE-OUT"},
            {"purpose": "Material Receipt"},
        ):
            with self.subTest(change=change):
                doc = self._transfer()
                doc.set("workflow_state", "Stock Entry Draft")
                previous = deepcopy(doc)
                previous.set("workflow_state", "Stock Transfer Reviewed")
                for field, value in change.items():
                    doc.set(field, value)
                with patch.object(doc, "get_doc_before_save", return_value=previous):
                    with self.assertRaises(frappe.ValidationError):
                        stock_entry_workflow.validate_workflow(doc)

    def test_new_transfer_cannot_start_in_approved_state_or_with_evidence(self) -> None:
        doc = self._transfer()
        doc.set("workflow_state", "Stock Transfer Approved")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(doc)
        doc.set("workflow_state", "Stock Entry Draft")
        doc.set("approval_maker_user", "forged@example.com")
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(doc)

    def test_direct_transfer_can_submit_only_from_persisted_approved_state(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-APPROVED",
                "owner": "maker@example.com",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Submitted",
                "docstatus": 1,
                "items": [
                    {
                        "item_code": "ITEM-A",
                        "s_warehouse": "SOURCE",
                        "t_warehouse": "SOURCE",
                        "storage_location": "LOC-A",
                        "to_storage_location": "LOC-B",
                        "qty": 1,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "conversion_factor": 1,
                    }
                ],
            }
        )
        digest = stock_entry_workflow.get_approval_digest(doc)
        evidence = {
            "approval_critical_digest": digest,
            "approval_maker_user": "maker@example.com",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_by": "EMP-CHECKER",
            "checked_at": datetime(2026, 9, 19),
            "checked_signature": "reviewer-signature",
            "authorized_by": "EMP-APPROVER",
            "authorized_at": datetime(2026, 9, 19),
            "authorized_signature": "approver-signature",
        }
        for field, value in evidence.items():
            doc.set(field, value)
        persisted = {"workflow_state": "Stock Transfer Approved", **evidence}
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Approved")
        previous.docstatus = 0
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "require_distinct_actors"),
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "consume_approval_field_grant") as consume,
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=persisted) as get_value,
        ):
            stock_entry_workflow.validate_before_submit(doc)

        get_value.assert_called_once_with(
            "Stock Entry",
            "STE-APPROVED",
            ["workflow_state", *sorted(stock_entry_workflow._APPROVAL_FIELDS)],
            as_dict=True,
            for_update=True,
        )
        consume.assert_called_once_with(doc, stock_entry_workflow.ROUTE, "Submit Stock Transfer")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "require_distinct_actors"),
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_submit(doc)

    def test_direct_submit_from_spoofed_persisted_state_is_denied(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-SPOOFED",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Submitted",
            }
        )
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Approved")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(
                stock_entry_workflow.frappe.db,
                "get_value",
                return_value={"workflow_state": "Stock Entry Draft"},
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_submit(doc)

    def test_mutation_after_review_invalidates_authorization(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "owner": "maker@example.com",
                "purpose": "Material Transfer",
                "items": [
                    {
                        "item_code": "ITEM-A",
                        "s_warehouse": "SOURCE",
                        "t_warehouse": "SOURCE",
                        "storage_location": "LOC-A",
                        "to_storage_location": "LOC-B",
                        "qty": 1,
                    }
                ],
            }
        )
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("approval_critical_digest", stock_entry_workflow.get_approval_digest(doc))
        actor = MagicMock(
            user="reviewer@example.com",
            employee="EMP-REVIEWER",
            acted_at=datetime(2026, 9, 19),
            signature="signed",
        )
        with patch.object(stock_entry_workflow, "authorize_approval_field_write", return_value=actor):
            stock_entry_workflow.capture_review_snapshot(doc)
        doc.items[0].qty = 2

        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.capture_approval_snapshot(doc)

    def test_maker_snapshot_is_authenticated_without_signature(self) -> None:
        doc = self._transfer()
        doc.name = "STE-1"
        doc.set("workflow_state", "Stock Transfer Pending Review")
        with (
            patch.object(
                frappe.db,
                "get_value",
                return_value=frappe._dict(
                    workflow_state="Stock Entry Draft", docstatus=0, approval_maker_user=None
                ),
            ),
            patch.object(
                stock_entry_workflow, "authorize_workflow_field_write", return_value="maker@example.com"
            ) as authorize,
            patch.object(stock_entry_workflow, "authorize_approval_field_write") as signed,
        ):
            stock_entry_workflow.capture_maker_snapshot(doc)
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
        self.assertEqual(doc.get("approval_critical_digest"), stock_entry_workflow.get_approval_digest(doc))
        authorize.assert_called_once_with(
            doc, stock_entry_workflow.ROUTE, "Send Stock Transfer for Review", ("Stock User",)
        )
        signed.assert_not_called()

    def test_resubmit_keeps_original_authenticated_maker(self) -> None:
        doc = self._transfer()
        doc.name = "STE-1"
        doc.set("workflow_state", "Stock Transfer Pending Review")
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("checked_signature", "old signature")
        with (
            patch.object(
                frappe.db,
                "get_value",
                return_value=frappe._dict(
                    workflow_state="Stock Transfer Returned",
                    docstatus=0,
                    approval_maker_user="maker@example.com",
                ),
            ) as locked,
            patch.object(stock_entry_workflow, "resolve_user", return_value="maker@example.com"),
            patch.object(
                stock_entry_workflow, "authorize_workflow_field_write", return_value="maker@example.com"
            ) as authorize,
        ):
            stock_entry_workflow.capture_maker_snapshot(doc)
        self.assertTrue(locked.call_args.kwargs["for_update"])
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
        self.assertFalse(doc.get("checked_signature"))
        authorize.assert_called_once_with(
            doc, stock_entry_workflow.ROUTE, "Resubmit Stock Transfer for Review", ("Stock User",)
        )

    def test_invalid_send_and_replacement_resubmit_never_mint_grant(self) -> None:
        cases = (
            ("Stock Entry Draft", 0, None, "forged@example.com", "maker@example.com"),
            ("Stock Entry Draft", 0, "maker@example.com", "maker@example.com", "maker@example.com"),
            ("Stock Transfer Returned", 0, None, None, "maker@example.com"),
            (
                "Stock Transfer Returned",
                0,
                "maker@example.com",
                "replacement@example.com",
                "replacement@example.com",
            ),
            (
                "Stock Transfer Returned",
                0,
                "maker@example.com",
                "maker@example.com",
                "replacement@example.com",
            ),
            ("Stock Transfer Returned", 1, "maker@example.com", "maker@example.com", "maker@example.com"),
            ("Stock Transfer Reviewed", 0, "maker@example.com", "maker@example.com", "maker@example.com"),
        )
        for state, status, maker, incoming, actor in cases:
            with self.subTest(state=state, status=status, incoming=incoming, actor=actor):
                doc = self._transfer()
                doc.name = "STE-1"
                doc.set("workflow_state", "Stock Transfer Pending Review")
                doc.set("approval_maker_user", incoming)
                with (
                    patch.object(
                        frappe.db,
                        "get_value",
                        return_value=frappe._dict(
                            workflow_state=state, docstatus=status, approval_maker_user=maker
                        ),
                    ),
                    patch.object(stock_entry_workflow, "resolve_user", return_value=actor),
                    patch.object(stock_entry_workflow, "authorize_workflow_field_write") as authorize,
                    self.assertRaises(frappe.ValidationError),
                ):
                    stock_entry_workflow.capture_maker_snapshot(doc)
                authorize.assert_not_called()

    def test_resubmit_validator_rejects_maker_delta_before_consuming_grant(self) -> None:
        doc = self._transfer()
        doc.name = "STE-1"
        doc.set("workflow_state", "Stock Transfer Pending Review")
        doc.set("approval_maker_user", "replacement@example.com")
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Returned")
        previous.set("approval_maker_user", "maker@example.com")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(stock_entry_workflow, "consume_approval_field_grant") as consume,
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_workflow(doc)
        consume.assert_not_called()

    def test_review_and_approval_capture_distinct_signed_snapshots(self) -> None:
        doc = self._transfer()
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("approval_critical_digest", stock_entry_workflow.get_approval_digest(doc))
        reviewer = MagicMock(
            user="reviewer@example.com",
            employee="EMP-REVIEWER",
            acted_at=datetime(2026, 9, 19),
            signature="reviewer-signed",
        )
        approver = MagicMock(
            user="approver@example.com",
            employee="EMP-APPROVER",
            acted_at=datetime(2026, 9, 20),
            signature="approver-signed",
        )
        with patch.object(
            stock_entry_workflow, "authorize_approval_field_write", side_effect=[reviewer, approver]
        ) as authorize:
            stock_entry_workflow.capture_review_snapshot(doc)
            stock_entry_workflow.capture_approval_snapshot(doc)
        self.assertEqual(doc.get("checked_signature"), "reviewer-signed")
        self.assertEqual(doc.get("authorized_signature"), "approver-signed")
        self.assertEqual(authorize.call_args_list[0].args[-1], "maker@example.com")
        self.assertEqual(
            authorize.call_args_list[1].args[-2:], ("maker@example.com", ("reviewer@example.com",))
        )

    def test_forged_state_and_evidence_require_one_use_grant(self) -> None:
        doc = self._transfer()
        doc.name = "STE-GRANT"
        doc.set("workflow_state", "Stock Transfer Pending Review")
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("approval_critical_digest", stock_entry_workflow.get_approval_digest(doc))
        previous = frappe.get_doc(doc.as_dict())
        previous.set("workflow_state", "Stock Entry Draft")
        previous.set("approval_maker_user", None)
        previous.set("approval_critical_digest", None)
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_workflow(doc)
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(approval_controls, "require_interactive_user", return_value="maker@example.com"),
        ):
            approval_controls.authorize_workflow_field_write(
                doc, stock_entry_workflow.ROUTE, "Send Stock Transfer for Review", ("Stock User",)
            )
            stock_entry_workflow.validate_workflow(doc)
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_workflow(doc)

    def test_same_state_evidence_edit_is_rejected(self) -> None:
        doc = self._transfer()
        doc.name = "STE-FORGED-EVIDENCE"
        doc.set("workflow_state", "Stock Transfer Pending Review")
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("approval_critical_digest", "forged")
        previous = frappe.get_doc(doc.as_dict())
        previous.set("approval_critical_digest", stock_entry_workflow.get_approval_digest(doc))
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_workflow(doc)

    def test_reviewed_transfer_cannot_escape_route_by_changing_purpose(self) -> None:
        doc = self._transfer()
        doc.name = "STE-ROUTE-ESCAPE"
        doc.set("workflow_state", "Stock Entry Draft")
        doc.set("purpose", "Material Issue")
        previous = frappe.get_doc(doc.as_dict())
        previous.set("workflow_state", "Stock Transfer Approved")
        previous.set("purpose", "Material Transfer")
        with (
            patch.object(doc, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_workflow(doc)

    def test_return_clears_current_approval_evidence(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Transfer Returned",
                "approval_critical_digest": "digest",
                "approval_reviewer_user": "reviewer@example.com",
                "approval_authorized_user": "approver@example.com",
                "checked_signature": "reviewer-signature",
                "authorized_signature": "approver-signature",
            }
        )

        with (
            patch.object(
                stock_entry_workflow.frappe.db, "get_value", return_value="Stock Transfer Pending Review"
            ),
            patch.object(stock_entry_workflow, "authorize_workflow_field_write") as authorize,
        ):
            stock_entry_workflow.reset_approval(doc)
        authorize.assert_called_once_with(
            doc,
            stock_entry_workflow.ROUTE,
            "Return Stock Transfer",
            ("Stock Manager",),
        )

        self.assertFalse(doc.approval_critical_digest)
        self.assertFalse(doc.approval_reviewer_user)
        self.assertFalse(doc.approval_authorized_user)
        self.assertFalse(doc.checked_signature)
        self.assertFalse(doc.authorized_signature)

    def test_reject_requires_distinct_final_approver_and_one_use_grant(self) -> None:
        doc = self._transfer()
        doc.name = "STE-REJECT"
        doc.set("workflow_state", "Stock Transfer Rejected")
        doc.set("approval_maker_user", "maker@example.com")
        doc.set("approval_reviewer_user", "reviewer@example.com")
        doc.set("approval_critical_digest", stock_entry_workflow.get_approval_digest(doc))
        doc.set("checked_by", "EMP-REVIEWER")
        doc.set("checked_at", datetime(2026, 9, 19))
        doc.set("checked_signature", "signed")
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Reviewed")
        with (
            patch.dict(stock_entry_workflow.frappe.session, {"user": "reviewer@example.com"}),
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(stock_entry_workflow, "resolve_user", side_effect=lambda identity: identity),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value="Stock Transfer Reviewed"),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.reject_approval(doc)
        with (
            patch.dict(stock_entry_workflow.frappe.session, {"user": "approver@example.com"}),
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(stock_entry_workflow, "resolve_user", side_effect=lambda identity: identity),
            patch.object(approval_controls, "require_interactive_user", return_value="approver@example.com"),
            patch.object(stock_entry_workflow.frappe.db, "get_value", return_value="Stock Transfer Reviewed"),
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
        ):
            stock_entry_workflow.reject_approval(doc)
            self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
            self.assertFalse(doc.get("approval_reviewer_user"))
            stock_entry_workflow.validate_workflow(doc)
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_workflow(doc)

    def test_forged_rejection_without_callback_grant_is_denied(self) -> None:
        doc = self._transfer()
        doc.name = "STE-FORGED-REJECT"
        doc.set("workflow_state", "Stock Transfer Rejected")
        previous = deepcopy(doc)
        previous.set("workflow_state", "Stock Transfer Reviewed")
        with (
            patch.object(doc, "is_new", return_value=False),
            patch.object(doc, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_workflow(doc)

    def test_transit_and_other_purposes_are_not_route(self) -> None:
        self.assertFalse(
            stock_entry_workflow.is_direct_transfer(
                frappe.get_doc(
                    {"doctype": "Stock Entry", "purpose": "Material Transfer", "add_to_transit": 1}
                )
            )
        )
        self.assertFalse(
            stock_entry_workflow.is_direct_transfer(
                frappe.get_doc({"doctype": "Stock Entry", "purpose": "Material Issue"})
            )
        )

    def test_completed_exception_without_current_execution_provenance_is_not_authorized(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NO-CURRENT-PROVENANCE",
                "purpose": "Material Transfer",
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Approved earlier but no current execution marker",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.object(stock_entry_workflow, "_has_current_freeze_scope", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_native_execution_task_is_required_after_approval_evidence(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NATIVE-EXECUTION",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Native execution task proof",
                "freeze_exception_reconciliation_scope": "[]",
            }
        )
        with patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True):
            with patch.object(stock_entry_workflow.frappe, "throw") as throw:
                stock_entry_workflow.authorize_freeze_exception_execution(doc)
            throw.assert_not_called()
            self.assertTrue(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_scope_rejects_new_freeze_before_execute(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-NEW-FREEZE",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "New Freeze must not be bypassed",
                "freeze_exception_reconciliation_scope": "[]",
            }
        )
        current_freeze = [
            {
                "item_code": "ITEM-A",
                "reconciliation": "SR-B",
                "warehouse": "WH-1",
                "modified": "2026-09-18 10:00:00",
            }
        ]
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.object(
                stock_entry_workflow,
                "_has_native_execution_provenance",
                return_value=True,
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.get_active_freeze_scope",
                return_value=current_freeze,
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_stale_completed_history_cannot_authorize_after_resubmit(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-STALE-RESUBMIT",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Old approval must not be reused",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(stock_entry_workflow.frappe.flags, {"freeze_exception_execution": None}),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_prior_history_and_spoofed_state_do_not_authorize_changed_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "SE-SPOOFED-ROUTE",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Transit must not use direct exception",
            }
        )
        with (
            patch.object(stock_entry_workflow.frappe.db, "exists", return_value=True),
            patch.dict(
                stock_entry_workflow.frappe.flags,
                {"freeze_exception_execution": {"doctype": doc.doctype, "name": doc.name}},
            ),
        ):
            self.assertFalse(stock_entry_workflow.is_authorized_freeze_exception(doc))

    def test_exception_requires_reason_and_direct_route(self) -> None:
        missing_reason = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "workflow_state": "Stock Entry Draft",
                "freeze_exception": 1,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(missing_reason)

        transit = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "workflow_state": "Stock Entry Draft",
                "freeze_exception": 1,
                "freeze_exception_reason": "Urgent controlled movement",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            stock_entry_workflow.validate_workflow(transit)

    def test_transit_outbound_and_receipt_are_not_direct_route(self) -> None:
        outbound = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 1,
                "outgoing_stock_entry": None,
            }
        )
        receipt = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "add_to_transit": 0,
                "outgoing_stock_entry": "STE-OUT",
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(outbound))
        self.assertFalse(stock_entry_workflow.is_direct_transfer(receipt))

    def test_other_stock_entry_purposes_are_not_direct_route(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Issue",
                "add_to_transit": 0,
                "outgoing_stock_entry": None,
            }
        )

        self.assertFalse(stock_entry_workflow.is_direct_transfer(doc))

    def test_non_transfer_submit_guard_is_a_noop(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Issue",
                "workflow_state": "Stock Entry Submitted",
            }
        )

        with patch.object(stock_entry_workflow.frappe.db, "get_value") as get_value:
            stock_entry_workflow.validate_before_submit(doc)

        get_value.assert_not_called()

    def test_ordinary_material_receipt_keeps_generic_workflow_passthrough(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "Stock Entry", "purpose": "Material Receipt", "workflow_state": "Stock Entry Draft"}
        )
        stock_entry_workflow.validate_workflow(doc)
        doc.set("workflow_state", "Stock Entry Submitted")
        stock_entry_workflow.validate_before_submit(doc)
        doc.set("workflow_state", "Stock Entry Cancelled")
        stock_entry_workflow.validate_before_cancel(doc)

    def test_direct_transfer_cancel_requires_workflow_transition(self) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "name": "STE-CANCEL",
                "purpose": "Material Transfer",
                "workflow_state": "Stock Entry Cancelled",
            }
        )
        with (
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(
                stock_entry_workflow.frappe.db,
                "get_value",
                return_value="Stock Transfer Submitted",
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_cancel(doc)

        doc.workflow_state = "Stock Transfer Cancelled"
        with (
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(stock_entry_workflow, "consume_approval_field_grant") as consume,
            patch.object(
                stock_entry_workflow.frappe.db, "get_value", return_value="Stock Transfer Submitted"
            ),
        ):
            stock_entry_workflow.validate_before_cancel(doc)
        consume.assert_called_once_with(doc, stock_entry_workflow.ROUTE, "Cancel Stock Transfer")
        with (
            patch.object(stock_entry_workflow, "resolve_user", return_value="executor@example.com"),
            patch.object(stock_entry_workflow.frappe, "get_roles", return_value=["Stock Manager"]),
            patch.object(stock_entry_workflow, "require_permission"),
            patch.object(
                stock_entry_workflow.frappe.db, "get_value", return_value="Stock Transfer Submitted"
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_entry_workflow.validate_before_cancel(doc)
