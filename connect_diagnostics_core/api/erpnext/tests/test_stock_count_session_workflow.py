# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Count lease overlap and native correction-shape unit checks."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from unittest.mock import Mock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_count_session_workflow as workflow


def _line(name: str, location: str, qty: float, serial: str = "") -> frappe._dict:
    return frappe._dict(
        name=name,
        line_key=name,
        item_code="_Test Item",
        company="_Test Company",
        warehouse="_Test Warehouse",
        storage_location=location,
        stock_uom="Nos",
        batch_no="",
        serial_no=serial,
        evidence_revision=1,
        variance_qty=qty,
    )


class TestStockCountSessionWorkflow(UnitTestCase):
    def test_approved_candidate_posting_timestamp_stays_stable_through_close_digest(self) -> None:
        frozen_at = "2026-10-02 09:30:15"
        doc = cast(
            Document,
            frappe._dict(name="COUNT-1", evidence_revision=1, frozen_at=frozen_at),
        )
        posting_stamp = workflow._count_effective_timestamp(doc)
        entry = cast(
            Document,
            frappe._dict(
                name="SE-count", posting_date=posting_stamp.date(), posting_time=posting_stamp.time()
            ),
        )
        with patch.object(
            workflow,
            "_candidate_projection",
            side_effect=lambda _doc, entries: {
                "frozen_at": str(doc.get("frozen_at")),
                "posting_policy": workflow._COUNT_POSTING_POLICY,
                "entries": [
                    {
                        "name": candidate.name,
                        "posting_date": str(candidate.get("posting_date")),
                        "posting_time": str(candidate.get("posting_time")),
                    }
                    for candidate in entries
                ],
            },
        ):
            approved_digest = workflow._candidate_digest(doc, [entry])
            candidate_stamp = workflow._candidate_posting_stamp(entry)
            close_digest = workflow._candidate_digest(doc, [entry])
            cast(Any, doc)["frozen_at"] = "2026-10-02 09:31:00"
            changed_cutoff_digest = workflow._candidate_digest(doc, [entry])

        self.assertEqual(candidate_stamp, posting_stamp)
        self.assertEqual(posting_stamp.date(), date(2026, 10, 2))
        self.assertEqual(posting_stamp.time(), time(9, 30, 15))
        self.assertEqual(close_digest, approved_digest)
        self.assertNotEqual(changed_cutoff_digest, approved_digest)

    def test_unchanged_approved_count_reaches_close_metadata_after_candidate_check(self) -> None:
        frozen_at = "2026-10-02 09:30:15"
        projection = {
            "entries": [],
            "frozen_at": frozen_at,
            "posting_policy": workflow._COUNT_POSTING_POLICY,
        }
        approved_digest = sha256(
            b'{"entries":[],"frozen_at":"2026-10-02 09:30:15","posting_policy":"Scope Freeze Time"}'
        ).hexdigest()
        doc = cast(
            Document,
            frappe._dict(
                name="COUNT-1",
                frozen_at=frozen_at,
                workflow_state="Closed",
                checker_user="checker@example.com",
                evidence_invalidated=0,
                approved_digest="evidence-digest",
                has_variance=0,
                accounting_review_required=0,
                accounting_settings_digest="settings-digest",
                accounting_candidate_digest=approved_digest,
                accounting_reviewed_digest="",
                scope=[],
                items=[],
            ),
        )
        cast(Any, doc)["set"] = lambda field, value: cast(Any, doc).__setitem__(field, value)
        with (
            patch.object(workflow, "_lock_session"),
            patch.object(workflow, "_actor", return_value=("checker@example.com", None)),
            patch.object(workflow, "_evidence_digest", return_value="evidence-digest"),
            patch.object(workflow, "_verify_complete", return_value=False),
            patch.object(workflow, "_accounting_settings", return_value=(False, "settings-digest")),
            patch.object(workflow, "_prepared_candidates", return_value=[]),
            patch.object(workflow, "_candidate_digest", return_value=approved_digest),
            patch.object(workflow, "_current_baseline_is_unchanged"),
            patch.object(workflow, "_correction_rows", return_value={}),
            patch.object(workflow, "_candidate_projection", return_value=projection),
            patch.object(workflow, "_cancellation_gl_source", return_value=(False, "", ())),
            patch.object(workflow, "_authorize_transition_save") as authorize_save,
            patch.object(workflow.frappe.db, "get_value", return_value="Approved"),
        ):
            workflow.close_count(doc)

        self.assertIsNotNone(doc.get("posted_at"))
        self.assertEqual(str(doc.get("posted_at")), frozen_at)
        self.assertEqual(doc.get("posting_date"), date(2026, 10, 2))
        self.assertEqual(doc.get("posting_time"), time(9, 30, 15))
        self.assertEqual(doc.get("posting_policy"), "Scope Freeze Time")
        self.assertIsNotNone(doc.get("closed_at"))
        authorize_save.assert_called_once()

    def test_full_and_cycle_lease_intersections(self) -> None:
        full = workflow.ActiveCountScope("session", "scope", "warehouse", "", 1)
        cycle = workflow.ActiveCountScope("session", "scope", "warehouse", "item-a", 1)
        self.assertTrue(full.intersects("item-b", "warehouse"))
        self.assertTrue(cycle.intersects("item-a", "warehouse"))
        self.assertFalse(cycle.intersects("item-b", "warehouse"))
        self.assertFalse(full.intersects("item-a", "other"))

    def test_proven_relocated_serial_uses_one_transfer_with_two_count_links(self) -> None:
        source = _line("source", "rack-a", -1, "SER-1")
        target = _line("target", "rack-b", 1, "SER-1")
        doc = cast(Document, frappe._dict(name="_Test Count", evidence_revision=1, items=[source, target]))
        result = workflow._correction_rows(doc)
        self.assertEqual(set(result), {("Material Transfer", "_Test Warehouse")})
        row = result[("Material Transfer", "_Test Warehouse")][0]
        self.assertEqual(row["stock_count_session_source_item"], "source")
        self.assertEqual(row["stock_count_session_target_item"], "target")
        self.assertEqual((row["storage_location"], row["to_storage_location"]), ("rack-a", "rack-b"))

    def test_unpaired_serial_and_batch_stay_native_issue_and_receipt(self) -> None:
        source = _line("source", "rack-a", -1, "SER-1")
        target = _line("target", "rack-b", 1, "SER-2")
        doc = cast(Document, frappe._dict(name="_Test Count", evidence_revision=1, items=[source, target]))
        result = workflow._correction_rows(doc)
        self.assertEqual(
            set(result),
            {
                ("Material Issue", "_Test Warehouse"),
                ("Material Receipt", "_Test Warehouse"),
            },
        )

    def test_effect_key_identifies_native_candidate_without_changing_count_revision(self) -> None:
        line = _line("same-line", "rack-a", 1)
        doc = cast(Document, frappe._dict(name="_Test Count", evidence_revision=3))
        first = workflow._effect_key(doc, "MAT-STE-1", None, cast(Document, line), "Material Receipt")
        again = workflow._effect_key(doc, "MAT-STE-1", None, cast(Document, line), "Material Receipt")
        replacement = workflow._effect_key(doc, "MAT-STE-2", None, cast(Document, line), "Material Receipt")
        self.assertEqual(first, again)
        self.assertNotEqual(first, replacement)

    def test_prior_retired_candidate_does_not_block_new_same_revision_review(self) -> None:
        doc = cast(Document, frappe._dict(name="_Test Count", evidence_revision=3))
        historical = frappe._dict(
            name="MAT-STE-old", docstatus=0, workflow_state="Stock Count Correction Retired"
        )
        with (
            patch.object(workflow.frappe.db, "get_values", return_value=[historical]),
            patch.object(workflow, "_correction_rows", return_value={}),
            patch.object(workflow.frappe, "get_doc") as get_doc,
        ):
            self.assertEqual(workflow._prepared_candidates(doc), [])
            get_doc.assert_not_called()

    def test_nonterminal_prior_candidate_blocks_replacement_review(self) -> None:
        doc = cast(Document, frappe._dict(name="_Test Count", evidence_revision=3))
        historical = frappe._dict(name="MAT-STE-old", docstatus=1, workflow_state="Stock Entry Submitted")
        with patch.object(workflow.frappe.db, "get_values", return_value=[historical]):
            with self.assertRaises(frappe.ValidationError):
                workflow._prepared_candidates(doc, require_complete=False)

    def test_direct_count_linked_stock_entry_requires_private_proof(self) -> None:
        entry = cast(Document, frappe._dict(doctype="Stock Entry", stock_count_session="_Test Count"))
        with patch.object(workflow.frappe.local, "_stock_count_effect_proof", None, create=True):
            with self.assertRaises(frappe.ValidationError):
                workflow.guard_count_stock_entry(entry, "before_submit")

    def test_unmarked_stock_entry_before_v6_skips_missing_persisted_columns(self) -> None:
        entry = Mock()
        entry.name = "MAT-STE-ordinary"
        entry.get.return_value = None
        entry.is_new.return_value = False
        entry.get_doc_before_save.return_value = None
        missing_meta = Mock()
        missing_meta.has_field.return_value = False
        with (
            patch.object(workflow.frappe, "get_meta", return_value=missing_meta),
            patch.object(workflow.frappe.db, "get_value") as get_value,
            patch.object(workflow.frappe.db, "get_values") as get_values,
        ):
            self.assertFalse(workflow.is_count_stock_entry(cast(Document, entry)))
            get_value.assert_not_called()
            get_values.assert_not_called()

    def test_partial_v6_child_schema_still_detects_persisted_effect_key(self) -> None:
        entry = Mock()
        entry.name = "MAT-STE-partial"
        entry.get.return_value = None
        entry.is_new.return_value = False
        entry.get_doc_before_save.return_value = None
        header_meta = Mock()
        header_meta.has_field.return_value = False
        detail_meta = Mock()
        detail_meta.has_field.side_effect = lambda field: field == "stock_count_effect_key"
        with (
            patch.object(workflow.frappe, "get_meta", side_effect=[header_meta, detail_meta]),
            patch.object(workflow.frappe.db, "get_value") as get_value,
            patch.object(
                workflow.frappe.db,
                "get_values",
                return_value=[{"stock_count_effect_key": "sealed-key"}],
            ) as get_values,
        ):
            self.assertTrue(workflow.is_count_stock_entry(cast(Document, entry)))
            get_value.assert_not_called()
            self.assertEqual(get_values.call_args.args[2], ["stock_count_effect_key"])

    def test_supplied_count_marker_fails_closed_without_installed_schema(self) -> None:
        entry = Mock()
        entry.get.side_effect = lambda field: "COUNT" if field == "stock_count_session" else None
        with patch.object(workflow.frappe, "get_meta") as get_meta:
            self.assertTrue(workflow.is_count_stock_entry(cast(Document, entry)))
            get_meta.assert_not_called()

    def test_count_correction_cannot_be_deleted_even_when_retired(self) -> None:
        entry = cast(
            Document,
            frappe._dict(
                doctype="Stock Entry",
                stock_count_session="_Test Count",
                workflow_state="Stock Count Correction Retired",
            ),
        )
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be deleted"):
            workflow.guard_count_stock_entry(entry, "on_trash")

    def test_recapture_accepts_evidence_until_another_emergency(self) -> None:
        source = frappe._dict(
            name="_Test Count",
            workflow_state="Recapture Required",
            evidence_revision=2,
            evidence_invalidated=1,
        )
        doc = cast(Document, source)
        with patch.object(workflow.frappe.db, "get_values", return_value=[]):
            self.assertTrue(workflow.count_revision_accepts_observations(doc))
        with patch.object(workflow.frappe.db, "get_values", return_value=["current-emergency"]):
            self.assertFalse(workflow.count_revision_accepts_observations(doc))
        cast(Any, source)["workflow_state"] = "Frozen"
        with patch.object(workflow.frappe.db, "get_values") as query:
            self.assertFalse(workflow.count_revision_accepts_observations(doc))
            query.assert_not_called()

    def test_native_count_close_rejects_wrong_serial_bundle_identity(self) -> None:
        line = _line("serial-line", "rack-a", 1, "SER-1")
        line.counted_qty = 1
        doc = cast(Document, frappe._dict(company="_Test Company", evidence_revision=1, items=[line]))
        wrong = frappe._dict(quantity=Decimal(1), identities=(("SER-2", "", Decimal(1)),))
        with patch.object(workflow, "snapshot_location", return_value=wrong):
            with self.assertRaises(frappe.ValidationError):
                workflow._verify_final_location_balances(doc)

    def test_native_count_ledger_bundle_must_match_linked_count_line(self) -> None:
        line = _line("count-line", "rack-a", 1, "SER-1")
        doc = cast(Document, frappe._dict(evidence_revision=1, items=[line]))
        detail = frappe._dict(
            name="entry-line",
            item_code="_Test Item",
            qty=1,
            transfer_qty=1,
            t_warehouse="_Test Warehouse",
            to_storage_location="rack-a",
            stock_count_session_target_item="count-line",
        )
        entry = cast(Document, frappe._dict(name="SE-test", items=[detail]))
        leg = frappe._dict(
            voucher_detail_no="entry-line",
            item_code="_Test Item",
            warehouse="_Test Warehouse",
            storage_location="rack-a",
            actual_qty=1,
            serial_and_batch_bundle="SABB-test",
        )
        wrong_child = frappe._dict(parent="SABB-test", serial_no="SER-2", batch_no="", qty=1)
        with patch.object(workflow.frappe.db, "get_values", side_effect=[[leg], [wrong_child]]):
            with self.assertRaises(frappe.ValidationError):
                workflow._verify_native_entry(entry, False, doc)

    def test_native_count_rejects_sle_value_different_from_approved_projection(self) -> None:
        line = _line("count-line", "rack-a", 2)
        line.counted_qty = 2
        doc = cast(Document, frappe._dict(evidence_revision=1, items=[line]))
        detail = frappe._dict(
            name="entry-line",
            item_code="_Test Item",
            qty=2,
            transfer_qty=2,
            t_warehouse="_Test Warehouse",
            to_storage_location="rack-a",
            stock_count_session_target_item="count-line",
        )
        entry = cast(Document, frappe._dict(name="SE-test", items=[detail]))
        sle = frappe._dict(
            voucher_detail_no="entry-line",
            item_code="_Test Item",
            warehouse="_Test Warehouse",
            storage_location="rack-a",
            actual_qty=2,
            valuation_rate=6,
            stock_value_difference=12,
            serial_and_batch_bundle="",
        )
        approved = {
            "rows": [{"name": "entry-line", "numbers": {"valuation_rate": "5", "incoming_rate": "5"}}]
        }
        with (
            patch.object(workflow.frappe.db, "get_values", return_value=[sle]),
            patch.object(workflow.frappe, "get_precision", return_value=2),
        ):
            with self.assertRaisesRegex(frappe.ValidationError, "approved Count valuation"):
                workflow._verify_native_entry(entry, False, doc, approved)

    def test_native_source_cache_refresh_is_narrow(self) -> None:
        from erpnext.stock.utils import get_valuation_method

        wrapped = cast(Any, get_valuation_method).__wrapped__
        request_cache = {wrapped: {("ITEM-A", "COMPANY-A"): "FIFO", ("ITEM-B", "COMPANY-A"): "LIFO"}}
        flags = frappe.flags
        old_maps = getattr(flags, "warehouse_account_map", None)
        old_request_cache = frappe.local.request_cache
        flags.warehouse_account_map = {"COMPANY-A": {"old": "map"}, "COMPANY-B": {"keep": "map"}}
        frappe.local.request_cache = request_cache
        try:
            with patch.object(workflow.frappe, "clear_document_cache") as clear:
                workflow._refresh_native_source_caches(
                    "COMPANY-A", {"ITEM-A"}, {"WH-A"}, {"GROUP-A"}, {"BRAND-A"}, {"ACCOUNT-A"}
                )
            self.assertEqual(request_cache[wrapped], {("ITEM-B", "COMPANY-A"): "LIFO"})
            self.assertEqual(flags.warehouse_account_map, {"COMPANY-B": {"keep": "map"}})
            self.assertEqual(clear.call_count, 7)
        finally:
            if old_maps is None:
                flags.pop("warehouse_account_map", None)
            else:
                flags.warehouse_account_map = old_maps
            frappe.local.request_cache = old_request_cache

    def test_full_revision_seal_changes_with_draft_business_reason(self) -> None:
        source = frappe._dict(
            company="_Test Company",
            scope_type="Full",
            scope=[frappe._dict(scope_kind="Warehouse", warehouse="_Test Warehouse", item_code="")],
            evidence_revision=1,
            cutoff_datetime="2026-10-02 09:00:00",
            locations=[],
            items=[],
            description="First",
            reason="Annual count",
        )
        doc = cast(Document, source)
        original = workflow._evidence_digest(doc)
        source["reason"] = "Different count purpose"
        self.assertNotEqual(workflow._evidence_digest(doc), original)
