# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native Count evidence, candidate lifecycle, posting and cancellation journeys."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.stock.doctype.landed_cost_voucher.test_landed_cost_voucher import (
    make_landed_cost_voucher,
)
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.model.document import Document
from frappe.model.workflow import WorkflowTransitionError, apply_workflow, get_workflow
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import (
    repost_item_valuation_reservation,
    stock_reconciliation_freeze,
)
from connect_diagnostics_core.api.erpnext import (
    stock_count_session_workflow as count_workflow,
)
from connect_diagnostics_core.api.erpnext.stock_count_session import (
    record_location_coverage,
    record_observation,
    set_stock_count_decision_reason,
)
from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import _cancellation_gl_source
from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location
from connect_diagnostics_core.api.erpnext.tests.test_stock_entry_workflow_integration import _ensure_user
from connect_diagnostics_core.setup.storage_location import ensure_configuration


class TestCountEffectLeaseIntersection(UnitTestCase):
    def test_exact_count_effect_ignores_disjoint_cycle_lease_in_same_warehouse(self) -> None:
        entry = Document(
            {
                "doctype": "Stock Entry",
                "name": "SE-COUNT-ITEM-A",
                "items": [
                    {
                        "name": "SE-COUNT-ITEM-A-ROW",
                        "item_code": "ITEM-A",
                        "s_warehouse": "WH-1",
                        "t_warehouse": "WH-DEST",
                    }
                ],
            }
        )
        proof = {
            "document": entry,
            "session": "COUNT-A",
            "revision": 4,
            "phase": "before_submit",
            "actor": "stock.manager@example.com",
            "guarded": True,
            "consumed": False,
            "items": count_workflow._count_effect_item_links(entry),
        }
        own_lease = count_workflow.ActiveCountScope(
            session="COUNT-A", row="SCOPE-A", warehouse="WH-1", item_code="ITEM-A", revision=4
        )
        disjoint_lease = count_workflow.ActiveCountScope(
            session="COUNT-B", row="SCOPE-B", warehouse="WH-1", item_code="ITEM-B", revision=2
        )
        previous = getattr(frappe.local, "_stock_count_effect_proof", None)
        frappe.local._stock_count_effect_proof = proof
        try:
            with (
                patch.object(count_workflow, "lock_warehouses"),
                patch.object(
                    count_workflow, "get_active_count_scopes", return_value=(own_lease, disjoint_lease)
                ),
            ):
                count_workflow.enforce_count_freeze(entry, "before_submit")

            overlapping_lease = count_workflow.ActiveCountScope(
                session="COUNT-C", row="SCOPE-C", warehouse="WH-1", item_code="ITEM-A", revision=1
            )
            with (
                patch.object(count_workflow, "lock_warehouses"),
                patch.object(
                    count_workflow,
                    "get_active_count_scopes",
                    return_value=(own_lease, overlapping_lease),
                ),
                self.assertRaisesRegex(frappe.ValidationError, "active Stock Count Session"),
            ):
                count_workflow.enforce_count_freeze(entry, "before_submit")
        finally:
            frappe.local._stock_count_effect_proof = previous


class TestStockCountSessionIntegrity(IntegrationTestCase):
    def test_submitted_or_preleased_parent_cannot_be_inserted(self) -> None:
        company = frappe.db.get_value("Company", {"name": ("like", "_Test%")}, "name")
        warehouse = frappe.db.get_value(
            "Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name"
        )
        self.assertTrue(company and warehouse)
        base = {
            "doctype": "Stock Count Session",
            "company": company,
            "scope_type": "Full",
            "scope": [
                {
                    "scope_kind": "Warehouse",
                    "warehouse": warehouse,
                    "company": company,
                }
            ],
        }
        before = frappe.db.count("Stock Count Session Scope", {"warehouse": warehouse, "freeze_active": 1})
        for forged in (
            {"docstatus": 1},
            {"evidence_revision": 1},
            {
                "scope": [
                    {
                        "scope_kind": "Warehouse",
                        "warehouse": warehouse,
                        "company": company,
                        "freeze_active": 1,
                    }
                ]
            },
        ):
            with self.subTest(forged=forged), self.assertRaises(frappe.ValidationError):
                frappe.get_doc({**base, **forged}).insert()
        self.assertEqual(
            frappe.db.count("Stock Count Session Scope", {"warehouse": warehouse, "freeze_active": 1}),
            before,
        )


class TestStockCountNativeCandidateJourney(IntegrationTestCase):
    """Exercise real Count and Stock Entry Workflow transitions in one transaction."""

    def setUp(self) -> None:
        super().setUp()
        self._savepoint = f"count_native_{uuid4().hex[:12]}"
        frappe.db.savepoint(self._savepoint)

        def restore_db() -> None:
            frappe.db.rollback(save_point=self._savepoint)
            frappe.clear_cache(doctype="Company")

        self.addCleanup(restore_db)
        previous_user = frappe.session.user
        previous_request = getattr(frappe.local, "request", None)
        self.addCleanup(frappe.set_user, previous_user)
        self.addCleanup(setattr, frappe.local, "request", previous_request)
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user("Administrator")
        ensure_configuration()
        frappe.db.set_value("Company", "_Test Company", "enable_perpetual_inventory", 1)
        frappe.clear_cache(doctype="Company")
        suffix = uuid4().hex[:8]
        self.maker = f"_test.count.maker.{suffix}@example.com"
        self.recounter = f"_test.count.recounter.{suffix}@example.com"
        self.checker = f"_test.count.checker.{suffix}@example.com"
        self.approver = f"_test.count.approver.{suffix}@example.com"
        self.accounts = f"_test.count.accounts.{suffix}@example.com"
        self.executive = f"_test.count.executive.{suffix}@example.com"
        for user, roles in (
            (self.maker, ("Stock User",)),
            (self.recounter, ("Stock User",)),
            (self.checker, ("Stock Manager",)),
            (self.approver, ("Stock Manager",)),
            (self.accounts, ("Accounts Manager",)),
            (self.executive, ("C-Level Approver",)),
        ):
            _ensure_user(user, roles)
        self.warehouse = (
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": f"_Test Count Warehouse {suffix}",
                    "company": "_Test Company",
                    "is_group": 0,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.other_warehouse = (
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": f"_Test Count Destination {suffix}",
                    "company": "_Test Company",
                    "is_group": 0,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.other_location = (
            frappe.get_doc(
                {
                    "doctype": "Storage Location",
                    "location_code": f"COUNT-DEST-{suffix}",
                    "warehouse": self.other_warehouse,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.location = (
            frappe.get_doc(
                {
                    "doctype": "Storage Location",
                    "location_code": f"COUNT-{suffix}",
                    "warehouse": self.warehouse,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        self.assertTrue(item_group)
        self.item = (
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": f"_Test Count Item {suffix}",
                    "item_name": f"_Test Count Item {suffix}",
                    "item_group": item_group,
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self._seed(self.item, 5)

    def _seed(self, item: str, qty: float, batch_no: str | None = None) -> None:
        seed = make_stock_entry(
            item_code=item,
            target=self.warehouse,
            qty=qty,
            basic_rate=100,
            batch_no=batch_no,
            do_not_save=True,
        )
        seed.items[0].to_storage_location = self.location
        seed.insert(ignore_permissions=True)
        seed.submit()
        self.seed_entry = str(seed.name)

    def _action(self, doc: Document, user: str, action: str) -> Document:
        frappe.set_user(user)
        return apply_workflow(frappe.get_doc("Stock Count Session", doc.name), action)

    def _draft_direct_transfer(self) -> Document:
        entry = make_stock_entry(
            item_code=self.item,
            company="_Test Company",
            from_warehouse=self.warehouse,
            to_warehouse=self.other_warehouse,
            qty=1,
            purpose="Material Transfer",
            do_not_save=True,
            do_not_submit=True,
        )
        entry.items[0].storage_location = self.location
        entry.items[0].to_storage_location = self.other_location
        return entry.insert(ignore_permissions=True)

    def _start_review(self, counted_qty: float = 4) -> tuple[Document, str]:
        frappe.set_user(self.maker)
        doc = frappe.get_doc(
            {
                "doctype": "Stock Count Session",
                "company": "_Test Company",
                "scope_type": "Cycle",
                "description": "Native candidate lifecycle test",
                "reason": "Cycle count",
                "scope": [
                    {
                        "scope_kind": "Item/Warehouse",
                        "warehouse": self.warehouse,
                        "item_code": self.item,
                        "company": "_Test Company",
                    }
                ],
            }
        ).insert()
        doc = self._action(doc, self.maker, "Freeze Count")
        revision = int(doc.get("evidence_revision") or 0)
        line = next(row for row in doc.get("items") or [] if row.get("evidence_revision") == revision)
        location = next(row for row in doc.get("locations") or [] if row.get("evidence_revision") == revision)
        record_location_coverage(doc.name, location.scope_row, self.location, revision)
        record_observation(doc.name, line.line_key, revision, "Initial", counted_qty)
        frappe.set_user(self.recounter)
        record_observation(doc.name, line.line_key, revision, "Recount", counted_qty)
        doc = self._action(doc, self.maker, "Send Count for Review")
        return doc, str(line.line_key)

    def test_approved_emergency_cannot_bypass_active_count_lease(self) -> None:
        _session, _line_key = self._start_review()
        entry = self._draft_direct_transfer()
        name = str(entry.name)
        frappe.db.set_value(
            "Stock Entry",
            name,
            {
                "workflow_state": "Emergency Stock Movement Submitted",
                "freeze_exception": 1,
                "freeze_exception_reason": "Urgent relocation",
            },
        )
        entry = frappe.get_doc("Stock Entry", name)
        with (
            patch(
                "connect_diagnostics_core.api.erpnext.stock_entry_workflow.is_authorized_freeze_exception",
                return_value=True,
            ) as authorization,
            self.assertRaisesRegex(frappe.ValidationError, "Stock Count Session"),
        ):
            stock_reconciliation_freeze.validate_transaction(entry, "before_submit")
        authorization.assert_not_called()
        self.assertFalse(
            frappe.db.exists("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": name})
        )

    def test_native_emergency_submit_action_is_denied_without_wf03_route(self) -> None:
        """WF-03 must install the approved Emergency action before a positive path exists."""
        _session, _line_key = self._start_review()
        entry = self._draft_direct_transfer()
        name = str(entry.name)
        frappe.db.set_value(
            "Stock Entry",
            name,
            {
                "workflow_state": "Emergency Stock Movement Approved",
                "freeze_exception": 1,
                "freeze_exception_reason": "Urgent relocation",
            },
        )
        frappe.clear_document_cache("Stock Entry", name)
        current = frappe.get_doc("Stock Entry", name)
        workflow = get_workflow(current.doctype)
        self.assertFalse(
            any(
                (
                    transition.state,
                    transition.action,
                    transition.next_state,
                )
                == (
                    "Emergency Stock Movement Approved",
                    "Post Emergency Stock Movement",
                    "Emergency Stock Movement Submitted",
                )
                for transition in workflow.transitions
            ),
            "The exact WF-03 emergency transition must be installed before native posting is accepted",
        )
        with self.assertRaisesRegex(WorkflowTransitionError, "Not a valid Workflow Action"):
            apply_workflow(current, "Post Emergency Stock Movement")
        self.assertEqual(frappe.db.get_value("Stock Entry", name, "docstatus"), 0)
        self.assertFalse(
            frappe.db.exists("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": name})
        )

    def test_pick_list_submission_is_allowed_during_count_freeze_without_ledger(self) -> None:
        _session, _line_key = self._start_review()
        pick_list = frappe.get_doc(
            {
                "doctype": "Pick List",
                "company": "_Test Company",
                "customer": "_Test Customer",
                "items_based_on": "Sales Order",
                "purpose": "Delivery",
                "locations": [
                    {
                        "item_code": self.item,
                        "qty": 1,
                        "stock_qty": 1,
                        "conversion_factor": 1,
                        "warehouse": self.warehouse,
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

    def test_registered_native_purchase_receipt_hooks_deny_counted_submit_and_cancel(self) -> None:
        draft = make_purchase_receipt(
            item=self.item,
            company="_Test Company",
            warehouse=self.warehouse,
            qty=1,
            do_not_submit=True,
        )
        draft.items[0].storage_location = self.location
        draft.save()
        submitted = make_purchase_receipt(
            item=self.item,
            company="_Test Company",
            warehouse=self.warehouse,
            qty=1,
            do_not_submit=True,
        )
        submitted.items[0].storage_location = self.location
        submitted.save()
        submitted.submit()
        submitted_effects = self._voucher_effects("Purchase Receipt", str(submitted.name))
        self._start_review()

        with self.assertRaisesRegex(frappe.ValidationError, "Stock Count Session"):
            draft.submit()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", draft.name, "docstatus"), 0)
        self.assertEqual(self._voucher_effects("Purchase Receipt", str(draft.name)), ([], []))

        with self.assertRaisesRegex(frappe.ValidationError, "Stock Count Session"):
            submitted.cancel()
        self.assertEqual(frappe.db.get_value("Purchase Receipt", submitted.name, "docstatus"), 1)
        self.assertEqual(self._voucher_effects("Purchase Receipt", str(submitted.name)), submitted_effects)

    def test_active_count_denies_every_registered_physical_boundary_before_ledger(self) -> None:
        receipt = make_purchase_receipt(
            item=self.item,
            company="_Test Company",
            warehouse=self.warehouse,
            qty=1,
            do_not_submit=True,
        )
        receipt.items[0].storage_location = self.location
        receipt.save()
        receipt.submit()
        _session, _line_key = self._start_review()
        lcv = make_landed_cost_voucher(
            receipt_document_type="Purchase Receipt",
            receipt_document=receipt.name,
            company="_Test Company",
            charges=5,
            do_not_submit=True,
        )
        source_effects = self._voucher_effects("Purchase Receipt", str(receipt.name))
        cases: list[tuple[str, Document]] = [
            (
                "Stock Entry source warehouse",
                Document(
                    {
                        "doctype": "Stock Entry",
                        "items": [
                            {
                                "item_code": self.item,
                                "s_warehouse": self.warehouse,
                                "t_warehouse": self.other_warehouse,
                            }
                        ],
                    }
                ),
            ),
            (
                "Delivery Note packed item",
                Document(
                    {
                        "doctype": "Delivery Note",
                        "items": [{"item_code": "PARENT", "warehouse": self.other_warehouse}],
                        "packed_items": [{"item_code": self.item, "warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Purchase Receipt destination warehouse",
                Document(
                    {
                        "doctype": "Purchase Receipt",
                        "items": [{"item_code": self.item, "warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Purchase Receipt outgoing source",
                Document(
                    {
                        "doctype": "Purchase Receipt",
                        "items": [{"item_code": self.item, "from_warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Purchase Receipt rejected warehouse",
                Document(
                    {
                        "doctype": "Purchase Receipt",
                        "items": [{"item_code": self.item, "rejected_warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Purchase Receipt old subcontracting supplied item",
                Document(
                    {
                        "doctype": "Purchase Receipt",
                        "is_old_subcontracting_flow": 1,
                        "supplier_warehouse": self.warehouse,
                        "supplied_items": [{"rm_item_code": self.item}],
                    }
                ),
            ),
            (
                "stock-updating Sales Invoice packed item",
                Document(
                    {
                        "doctype": "Sales Invoice",
                        "update_stock": 1,
                        "items": [{"item_code": "PARENT", "warehouse": self.other_warehouse}],
                        "packed_items": [{"item_code": self.item, "warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "stock-updating Purchase Invoice source",
                Document(
                    {
                        "doctype": "Purchase Invoice",
                        "update_stock": 1,
                        "items": [{"item_code": self.item, "from_warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Subcontracting Receipt supplier warehouse",
                Document(
                    {
                        "doctype": "Subcontracting Receipt",
                        "items": [
                            {
                                "item_code": self.item,
                                "warehouse": self.warehouse,
                                "rejected_warehouse": self.warehouse,
                            }
                        ],
                        "supplier_warehouse": self.warehouse,
                        "supplied_items": [{"rm_item_code": self.item}],
                    }
                ),
            ),
            (
                "Stock Reconciliation item warehouse",
                Document(
                    {
                        "doctype": "Stock Reconciliation",
                        "items": [{"item_code": self.item, "warehouse": self.warehouse}],
                    }
                ),
            ),
            (
                "Asset Capitalization stock item",
                Document(
                    {
                        "doctype": "Asset Capitalization",
                        "stock_items": [{"item_code": self.item, "warehouse": self.warehouse}],
                    }
                ),
            ),
            ("Landed Cost Voucher source replay", lcv),
        ]
        for label, doc in cases:
            for method in ("before_submit", "before_cancel"):
                with (
                    self.subTest(boundary=label, method=method),
                    self.assertRaisesRegex(frappe.ValidationError, "Stock Count Session"),
                ):
                    if doc.doctype == "Landed Cost Voucher":
                        doc.docstatus = 0 if method == "before_submit" else 2
                    stock_reconciliation_freeze.validate_transaction(doc, method)
        for doctype in ("Sales Invoice", "Purchase Invoice"):
            with self.subTest(doctype=doctype, update_stock=0):
                stock_reconciliation_freeze.validate_transaction(
                    Document(
                        {
                            "doctype": doctype,
                            "update_stock": 0,
                            "items": [{"item_code": self.item, "warehouse": self.warehouse}],
                        }
                    ),
                    "before_submit",
                )
        self.assertEqual(self._voucher_effects("Purchase Receipt", str(receipt.name)), source_effects)

    def test_failed_native_submit_then_same_document_retry_uses_fresh_count_proof(self) -> None:
        doc, _line_key = self._start_review()
        doc = self._action(doc, self.checker, "Review Count")
        doc = self._action(doc, self.approver, "Approve Count Requiring Accounting")
        doc = self._action(doc, self.accounts, "Approve Count Accounting")
        frappe.set_user(self.checker)
        candidates = count_workflow._prepared_candidates(doc)
        self.assertEqual(len(candidates), 1)
        entry = candidates[0]
        approved = count_workflow._candidate_projection(doc, candidates)
        stamp = count_workflow._count_effective_timestamp(doc)
        approved_entry = next(row for row in approved["entries"] if row["name"] == entry.name)
        original_apply = apply_workflow
        proofs: list[dict[str, object]] = []
        targets: list[Document] = []

        def fail_once_then_apply(target: Document, action: str) -> Document:
            proof = getattr(frappe.local, "_stock_count_effect_proof", None)
            self.assertIsInstance(proof, dict)
            assert isinstance(proof, dict)
            proofs.append(proof)
            targets.append(target)
            return original_apply(target, action)

        original_verify = count_workflow._verify_native_entry

        def verify_after_native_hook_then_fail_once(
            target: Document,
            accounting_required: bool,
            session: Document,
            approved: dict[str, object],
        ) -> None:
            if len(proofs) == 1:
                proof = getattr(frappe.local, "_stock_count_effect_proof", None)
                self.assertIsInstance(proof, dict)
                assert isinstance(proof, dict)
                self.assertIs(proof, proofs[0])
                self.assertTrue(proof["guarded"])
                self.assertFalse(proof["consumed"])
                self.assertEqual(target.docstatus, 1)
                self.assertTrue(
                    frappe.db.exists(
                        "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": target.name}
                    )
                )
                frappe.throw("Injected post-native-hook failure before Count proof completion")
            original_verify(target, accounting_required, session, approved)

        previous = getattr(frappe.local, "_stock_count_effect_proof", None)
        savepoint = f"count_effect_retry_{uuid4().hex[:12]}"
        frappe.db.savepoint(savepoint)
        with (
            patch("frappe.model.workflow.apply_workflow", side_effect=fail_once_then_apply),
            patch.object(
                count_workflow,
                "_verify_native_entry",
                side_effect=verify_after_native_hook_then_fail_once,
            ),
        ):
            with self.assertRaisesRegex(frappe.ValidationError, "post-native-hook failure"):
                count_workflow._submit_prepared_candidate(doc, entry, stamp, approved_entry)
            self.assertIs(getattr(frappe.local, "_stock_count_effect_proof", None), previous)
            self.assertTrue(proofs[0]["guarded"])
            self.assertFalse(proofs[0]["consumed"])
            frappe.db.rollback(save_point=savepoint)
            self.assertFalse(
                frappe.db.exists(
                    "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": entry.name}
                )
            )
            entry.reload()
            submitted = count_workflow._submit_prepared_candidate(doc, entry, stamp, approved_entry)

        self.assertEqual(submitted.docstatus, 1)
        self.assertIs(targets[0], targets[1])
        self.assertIsNot(proofs[0], proofs[1])
        self.assertTrue(proofs[1]["consumed"])
        self.assertIs(getattr(frappe.local, "_stock_count_effect_proof", None), previous)
        self.assertTrue(
            frappe.db.exists("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": entry.name})
        )

    def _voucher_effects(self, doctype: str, name: str) -> tuple[list[dict], list[dict]]:
        filters = {"voucher_type": doctype, "voucher_no": name}
        stock = frappe.get_all(
            "Stock Ledger Entry",
            filters=filters,
            fields=["name", "actual_qty", "is_cancelled"],
            order_by="name",
        )
        general = frappe.get_all(
            "GL Entry", filters=filters, fields=["name", "debit", "credit", "is_cancelled"], order_by="name"
        )
        return [dict(row) for row in stock], [dict(row) for row in general]

    def test_return_recount_review_replaces_retired_native_candidate(self) -> None:
        doc, line_key = self._start_review()
        doc = self._action(doc, self.checker, "Review Count")
        first = frappe.get_doc(
            "Stock Entry",
            frappe.db.get_value("Stock Entry", {"stock_count_session": doc.name}, "name"),
        )
        self.assertEqual(first.docstatus, 0)
        self.assertFalse(first.items[0].serial_and_batch_bundle)
        first_key = first.items[0].stock_count_effect_key
        self.assertTrue(first_key)
        self.assertFalse(
            frappe.db.exists("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": first.name})
        )
        frappe.set_user(self.checker)
        set_stock_count_decision_reason(doc.name, "Return Count from Stock Approval", "Recount independently")
        doc = self._action(doc, self.checker, "Return Count from Stock Approval")
        first.reload()
        self.assertEqual(first.workflow_state, "Stock Count Correction Retired")
        self.assertEqual(first.items[0].stock_count_effect_key, first_key)
        self.assertTrue(
            frappe.db.exists(
                "Workflow Action",
                {
                    "reference_doctype": "Stock Entry",
                    "reference_name": first.name,
                    "status": "Completed",
                    "completed_by": self.checker,
                },
            )
        )
        self.assertEqual(doc.get("evidence_revision"), 1)
        frappe.set_user(self.recounter)
        record_observation(doc.name, line_key, 1, "Recount", 4)
        doc = self._action(doc, self.maker, "Resubmit Count for Review")

        # A failed request after the native Draft insert must leave no partial
        # replacement once its DB transaction is rolled back.
        savepoint = f"failed_second_review_{uuid4().hex[:12]}"
        frappe.db.savepoint(savepoint)
        original_prepare = count_workflow._prepare_candidates

        def fail_after_prepare(parent: Document) -> None:
            original_prepare(parent)
            frappe.throw("Injected failure after second Count candidate preparation")

        try:
            with patch.object(count_workflow, "_prepare_candidates", fail_after_prepare):
                with self.assertRaisesRegex(frappe.ValidationError, "Injected failure"):
                    self._action(doc, self.checker, "Review Count")
        finally:
            frappe.db.rollback(save_point=savepoint)
        self.assertEqual(
            frappe.db.get_value("Stock Count Session", doc.name, "workflow_state"), "Pending Review"
        )
        self.assertFalse(
            frappe.db.exists(
                "Stock Entry",
                {"stock_count_session": doc.name, "workflow_state": "Stock Entry Draft"},
            )
        )

        doc = self._action(doc, self.checker, "Review Count")
        active = frappe.db.get_values(
            "Stock Entry",
            {"stock_count_session": doc.name, "workflow_state": "Stock Entry Draft"},
            "name",
            pluck=True,
        )
        self.assertEqual(len(active), 1)
        second = frappe.get_doc("Stock Entry", active[0])
        self.assertNotEqual(second.name, first.name)
        self.assertNotEqual(second.items[0].stock_count_effect_key, first_key)
        with self.assertRaises(frappe.ValidationError):
            self._action(doc, self.checker, "Review Count")
        self.assertEqual(
            frappe.db.count(
                "Stock Entry", {"stock_count_session": doc.name, "workflow_state": "Stock Entry Draft"}
            ),
            1,
        )
        doc = self._action(doc, self.approver, "Approve Count Requiring Accounting")
        doc = self._action(doc, self.accounts, "Approve Count Accounting")
        doc = self._action(doc, self.checker, "Post Corrections and Close Count")
        self.assertEqual(doc.docstatus, 1)
        self.assertIsNone(getattr(frappe.local, "_stock_count_effect_proof", None))
        self.assertEqual(frappe.db.get_value("Stock Entry", first.name, "docstatus"), 0)
        self.assertEqual(frappe.db.get_value("Stock Entry", second.name, "docstatus"), 1)
        self.assertFalse(
            frappe.db.exists("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": first.name})
        )
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": second.name}),
            1,
        )
        self.assertEqual(frappe.db.count("Stock Entry", {"stock_count_session": doc.name, "docstatus": 1}), 1)
        self.assertEqual(
            snapshot_location(
                company="_Test Company",
                item_code=self.item,
                warehouse=self.warehouse,
                storage_location=self.location,
                cutoff=frappe.utils.now(),
            ).quantity,
            4,
        )

    def test_tracked_batch_draft_does_not_create_bundle_or_post_stock(self) -> None:
        frappe.set_user("Administrator")
        suffix = uuid4().hex[:8]
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        self.assertTrue(item_group)
        self.item = (
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": f"_Test Count Batch Item {suffix}",
                    "item_name": f"_Test Count Batch Item {suffix}",
                    "item_group": item_group,
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                    "has_batch_no": 1,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        batch = frappe.get_doc(
            {"doctype": "Batch", "batch_id": f"COUNT-BATCH-{suffix}", "item": self.item}
        ).insert(ignore_permissions=True)
        self._seed(self.item, 2, str(batch.name))
        doc, _line_key = self._start_review(counted_qty=1)
        doc = self._action(doc, self.checker, "Review Count")
        candidate = frappe.get_doc(
            "Stock Entry",
            frappe.db.get_value("Stock Entry", {"stock_count_session": doc.name}, "name"),
        )
        self.assertEqual(candidate.docstatus, 0)
        self.assertEqual(candidate.items[0].batch_no, batch.name)
        self.assertFalse(candidate.items[0].serial_and_batch_bundle)
        self.assertFalse(
            frappe.db.exists(
                "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": candidate.name}
            )
        )

    def test_approved_count_posts_native_correction_and_cancels_with_actual_gl_route(self) -> None:
        doc, _line_key = self._start_review()
        doc = self._action(doc, self.checker, "Review Count")
        self.assertEqual(doc.get("accounting_review_required"), 1)
        doc = self._action(doc, self.approver, "Approve Count Requiring Accounting")
        doc = self._action(doc, self.accounts, "Approve Count Accounting")
        doc = self._action(doc, self.checker, "Post Corrections and Close Count")
        self.assertEqual(doc.docstatus, 1)
        self.assertIsNone(getattr(frappe.local, "_stock_count_effect_proof", None))
        freeze_timestamp = frappe.utils.get_datetime(doc.get("frozen_at"))
        assert freeze_timestamp is not None
        self.assertEqual(doc.get("posting_policy"), "Scope Freeze Time")
        self.assertEqual(frappe.utils.get_datetime(doc.get("posted_at")), freeze_timestamp)
        self.assertEqual(str(doc.get("posting_date")), str(freeze_timestamp.date()))
        self.assertEqual(frappe.utils.get_time(doc.get("posting_time")), freeze_timestamp.time())
        corrections = frappe.get_all(
            "Stock Entry", filters={"stock_count_session": doc.name, "docstatus": 1}, pluck="name"
        )
        self.assertEqual(len(corrections), 1)
        correction = frappe.get_doc("Stock Entry", corrections[0])
        self.assertEqual(str(correction.get("posting_date")), str(freeze_timestamp.date()))
        self.assertEqual(frappe.utils.get_time(correction.get("posting_time")), freeze_timestamp.time())
        self.assertTrue(
            frappe.db.exists(
                "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": corrections[0]}
            )
        )
        self.assertEqual(
            snapshot_location(
                company="_Test Company",
                item_code=self.item,
                warehouse=self.warehouse,
                storage_location=self.location,
                cutoff=frappe.utils.now(),
            ).quantity,
            4,
        )
        has_gl, _digest, _names = _cancellation_gl_source(doc)
        if has_gl:
            frappe.set_user(self.checker)
            set_stock_count_decision_reason(
                doc.name, "Request Count Cancellation Accounting Review", "Reverse approved Count"
            )
            doc = self._action(doc, self.checker, "Request Count Cancellation Accounting Review")
            doc = self._action(doc, self.accounts, "Approve Count Cancellation")
        doc = self._action(doc, self.checker, "Cancel Closed Count")
        self.assertEqual(doc.docstatus, 2)
        self.assertEqual(frappe.db.get_value("Stock Entry", corrections[0], "docstatus"), 2)

    def test_close_rejects_item_valuation_change_after_accounting_approval(self) -> None:
        from erpnext.stock.utils import get_valuation_method

        doc, _line_key = self._start_review()
        doc = self._action(doc, self.checker, "Review Count")
        doc = self._action(doc, self.approver, "Approve Count Requiring Accounting")
        doc = self._action(doc, self.accounts, "Approve Count Accounting")
        cached_method = get_valuation_method(self.item, "_Test Company")
        self.assertTrue(cached_method)
        self.assertEqual(doc.get("workflow_state"), "Approved")
        candidate = frappe.db.get_value("Stock Entry", {"stock_count_session": doc.name}, "name")
        self.assertTrue(candidate)

        # Model an independent committed master-data change between approval and
        # execution. The resolver's old request-cache value must not authorize it.
        frappe.db.set_value("Item", self.item, "valuation_method", "Moving Average")
        before_sle = frappe.db.count(
            "Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": candidate}
        )
        with self.assertRaisesRegex(frappe.ValidationError, "current settings changed"):
            self._action(doc, self.checker, "Post Corrections and Close Count")
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_type": "Stock Entry", "voucher_no": candidate}),
            before_sle,
        )
        self.assertEqual(frappe.db.get_value("Stock Entry", candidate, "docstatus"), 0)
        self.assertEqual(frappe.db.get_value("Stock Count Session", doc.name, "workflow_state"), "Approved")

    def test_failed_retirement_rolls_back_parent_and_native_candidate(self) -> None:
        doc, _line_key = self._start_review()
        doc = self._action(doc, self.checker, "Review Count")
        candidate = frappe.db.get_value("Stock Entry", {"stock_count_session": doc.name}, "name")
        self.assertTrue(candidate)
        frappe.set_user(self.checker)
        set_stock_count_decision_reason(doc.name, "Return Count from Stock Approval", "Retry review")
        savepoint = f"failed_count_retire_{uuid4().hex[:12]}"
        frappe.db.savepoint(savepoint)
        original = count_workflow._retire_candidates

        def fail_after_native_retirement(parent: Document, action: str, source: str, target: str) -> None:
            original(parent, action, source, target)
            frappe.throw("Injected failure after native retirement")

        try:
            with patch.object(count_workflow, "_retire_candidates", fail_after_native_retirement):
                with self.assertRaisesRegex(frappe.ValidationError, "Injected failure"):
                    self._action(doc, self.checker, "Return Count from Stock Approval")
        finally:
            frappe.db.rollback(save_point=savepoint)
        self.assertEqual(
            frappe.db.get_value("Stock Count Session", doc.name, "workflow_state"), "Pending Stock Approval"
        )
        self.assertEqual(frappe.db.get_value("Stock Entry", candidate, "workflow_state"), "Stock Entry Draft")


class TestStockCountActivationPhysicalConcurrency(IntegrationTestCase):
    """A real Count Freeze lease publication serializes concurrent LCV and repost work."""

    def test_count_freeze_mutex_blocks_landed_cost_and_repost_before_effect(self) -> None:
        frappe.set_user("Administrator")
        previous_request = getattr(frappe.local, "request", None)
        self.addCleanup(setattr, frappe.local, "request", previous_request)
        frappe.local.request = frappe._dict(method="POST")

        receipt: Document | None = None
        for row in frappe.get_all(
            "Purchase Receipt",
            filters={"docstatus": 1},
            fields=["name"],
            order_by="name",
        ):
            candidate = frappe.get_doc("Purchase Receipt", row.name)
            if any(
                item.get("item_code") and item.get("warehouse") for item in candidate.get("items") or []
            ) and frappe.db.exists(
                "Stock Ledger Entry",
                {"voucher_type": "Purchase Receipt", "voucher_no": candidate.name, "is_cancelled": 0},
            ):
                receipt = candidate
                break
        if receipt is None:
            self.skipTest(
                "A submitted Purchase Receipt with active SLE rows is required for collision coverage"
            )
        source_item = next(
            item for item in receipt.get("items") or [] if item.get("item_code") and item.get("warehouse")
        )
        item_code = str(source_item.get("item_code"))
        warehouse = str(source_item.get("warehouse"))
        company = str(receipt.get("company"))
        session = frappe.get_doc(
            {
                "doctype": "Stock Count Session",
                "company": company,
                "scope_type": "Cycle",
                "description": "Count/LCV/repost mutex collision test",
                "reason": "Concurrency test",
                "scope": [
                    {
                        "scope_kind": "Item/Warehouse",
                        "warehouse": warehouse,
                        "item_code": item_code,
                        "company": company,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        before = self._source_effects(str(receipt.name))

        with self.primary_connection():
            session = apply_workflow(session, "Freeze Count")
            self.assertEqual(session.get("workflow_state"), "Frozen")
            self.assertEqual(session.scope[0].get("lease_state"), "Active")
            with self.secondary_connection():
                lcv = Document(
                    {
                        "doctype": "Landed Cost Voucher",
                        "purchase_receipts": [
                            {
                                "receipt_document_type": "Purchase Receipt",
                                "receipt_document": receipt.name,
                            }
                        ],
                    }
                )
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    stock_reconciliation_freeze.validate_transaction(lcv, "before_submit")
                frappe.db.rollback()
            with self.secondary_connection():
                repost = frappe.get_doc(
                    {
                        "doctype": "Repost Item Valuation",
                        "based_on": "Transaction",
                        "voucher_type": "Purchase Receipt",
                        "voucher_no": receipt.name,
                        "posting_date": receipt.get("posting_date"),
                        "posting_time": receipt.get("posting_time"),
                        "recreate_stock_ledgers": 1,
                    }
                ).insert(ignore_permissions=True)
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    repost.submit()
                frappe.db.rollback()
            self.assertEqual(self._source_effects(str(receipt.name)), before)

    def _source_effects(self, receipt_name: str) -> tuple[list[dict], list[dict]]:
        filters = {"voucher_type": "Purchase Receipt", "voucher_no": receipt_name}
        stock = frappe.get_all(
            "Stock Ledger Entry",
            filters=filters,
            fields=["name", "actual_qty", "is_cancelled"],
            order_by="name",
        )
        general = frappe.get_all(
            "GL Entry", filters=filters, fields=["name", "debit", "credit", "is_cancelled"], order_by="name"
        )
        return [dict(row) for row in stock], [dict(row) for row in general]
