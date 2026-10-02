# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import asset_disposal_workflow as disposal


class TestAssetDisposalWorkflow(UnitTestCase):
    def test_asset_read_is_checked_before_company_lock_and_rechecked_after_load(self) -> None:
        events: list[str] = []
        asset = frappe._dict(name="AST-1", company="COMPANY-1")

        def has_permission(doctype: str, ptype: str, doc: Any = None) -> bool:
            events.append("name_read" if doc == "AST-1" else "document_read")
            return True

        def get_value(doctype: str, name: str, field: str, **kwargs: Any) -> str:
            events.append("company_lock")
            self.assertEqual((doctype, name, field), ("Asset", "AST-1", "company"))
            self.assertTrue(kwargs["for_update"])
            return "COMPANY-1"

        def get_all(*args: Any, **kwargs: Any) -> list[Any]:
            events.append("company_scope")
            return [frappe._dict(applicable_for="Asset", apply_to_all_doctypes=0)]

        def get_doc(doctype: str, name: str, **kwargs: Any) -> Any:
            events.append("load_asset")
            self.assertTrue(kwargs["for_update"])
            return asset

        with (
            patch.object(disposal.frappe, "has_permission", side_effect=has_permission),
            patch.object(disposal.frappe.db, "get_value", side_effect=get_value),
            patch.object(disposal.frappe, "get_all", side_effect=get_all),
            patch.object(disposal.frappe, "get_doc", side_effect=get_doc),
        ):
            self.assertIs(disposal._lock_asset("AST-1"), asset)

        self.assertEqual(
            events,
            ["name_read", "company_lock", "company_scope", "load_asset", "document_read"],
        )

    def test_asset_read_denial_happens_before_any_asset_lookup(self) -> None:
        with (
            patch.object(disposal.frappe, "has_permission", return_value=False) as permission,
            patch.object(disposal.frappe.db, "get_value") as asset_lookup,
            patch.object(disposal.frappe, "get_doc") as asset_load,
            self.assertRaisesRegex(frappe.PermissionError, "permission to access this Asset"),
        ):
            disposal._lock_asset("GUESSED-ASSET")
        permission.assert_called_once_with("Asset", "read", "GUESSED-ASSET")
        asset_lookup.assert_not_called()
        asset_load.assert_not_called()

    def test_asset_company_scope_fails_closed_for_missing_or_wrong_scope(self) -> None:
        for row in (
            frappe._dict(applicable_for="Sales Invoice", apply_to_all_doctypes=0),
            frappe._dict(applicable_for="Sales Invoice", apply_to_all_doctypes=1),
        ):
            with patch.object(disposal.frappe, "get_all", return_value=[row]):
                self.assertFalse(disposal._has_explicit_asset_company_scope("COMPANY-1"))
        with patch.object(disposal.frappe, "get_all", return_value=[]):
            self.assertFalse(disposal._has_explicit_asset_company_scope("COMPANY-1"))

    def test_missing_asset_company_scope_denies_before_loading_asset(self) -> None:
        with (
            patch.object(disposal.frappe, "has_permission", return_value=True),
            patch.object(disposal.frappe.db, "get_value", return_value="COMPANY-1"),
            patch.object(disposal.frappe, "get_all", return_value=[]) as permission_rows,
            patch.object(disposal.frappe, "get_doc") as asset_load,
            self.assertRaisesRegex(frappe.PermissionError, "permission to access this Asset"),
        ):
            disposal._lock_asset("AST-1")
        self.assertEqual(
            permission_rows.call_args.kwargs["filters"],
            {
                "user": frappe.session.user,
                "allow": "Company",
                "for_value": "COMPANY-1",
            },
        )
        asset_load.assert_not_called()

    def test_reservation_check_uses_nonwaiting_current_locking_read(self) -> None:
        with patch.object(disposal.frappe.db, "get_values", return_value=[]) as reservation_query:
            disposal._assert_unreserved("AST-1", "ADR-NEW")

        reservation_query.assert_called_once()
        self.assertEqual(reservation_query.call_args.args[0], disposal.DOCTYPE)
        self.assertEqual(reservation_query.call_args.kwargs["filters"]["asset"], "AST-1")
        self.assertTrue(reservation_query.call_args.kwargs["for_update"])
        self.assertFalse(reservation_query.call_args.kwargs["wait"])
        self.assertEqual(reservation_query.call_args.kwargs["fieldname"], ["name", "disposal_status"])

    def test_competing_active_reservation_is_denied_after_current_locking_read(self) -> None:
        with (
            patch.object(
                disposal.frappe.db,
                "get_values",
                return_value=[frappe._dict(name="ADR-OTHER", disposal_status="Not Executed")],
            ) as reservation_query,
            self.assertRaisesRegex(frappe.ValidationError, "already reserved"),
        ):
            disposal._assert_unreserved("AST-1", "ADR-NEW")

        self.assertTrue(reservation_query.call_args.kwargs["for_update"])
        self.assertFalse(reservation_query.call_args.kwargs["wait"])

    def test_asset_company_scope_accepts_asset_or_all_doctype_permission(self) -> None:
        for row in (
            frappe._dict(applicable_for="Asset", apply_to_all_doctypes=0),
            frappe._dict(applicable_for=None, apply_to_all_doctypes=0),
            frappe._dict(applicable_for="", apply_to_all_doctypes=0),
            frappe._dict(applicable_for="", apply_to_all_doctypes=1),
        ):
            with patch.object(disposal.frappe, "get_all", return_value=[row]):
                self.assertTrue(disposal._has_explicit_asset_company_scope("COMPANY-1"))

    def test_explicit_blank_sale_template_preserves_item_tax_rows(self) -> None:
        class NativeTaxBehavior:
            def __init__(self) -> None:
                self.doctype = "Sales Invoice"
                self.company = "C"
                self.items = [frappe._dict(asset="AST-1", is_fixed_asset=1, qty=1)]
                self.taxes_and_charges = None
                self.taxes = [frappe._dict(account_head="ITEM-TAX")]

            def get(self, field: str) -> Any:
                return getattr(self, field)

            def set(self, field: str, value: Any) -> None:
                setattr(self, field, value)

            def set_taxes(self) -> None:
                self.taxes_and_charges = "COMPANY-DEFAULT"

            def set_missing_lead_customer_details(self, for_validate: bool = False) -> None:
                self.taxes_and_charges = "CUSTOMER-DEFAULT"
                self.taxes.append(frappe._dict(account_head="CUSTOMER-TAX"))

        class Invoice(disposal.AssetDisposalSalesInvoiceMixin, NativeTaxBehavior):
            pass

        invoice = Invoice()
        request = frappe._dict(company="C", asset="AST-1", sell_qty=1, taxes_template=None)
        with disposal._sale_tax_context(request, invoice):
            invoice.set_taxes()
            self.assertIsNone(invoice.taxes_and_charges)
            invoice.set_missing_lead_customer_details()
            self.assertIsNone(invoice.taxes_and_charges)
            self.assertEqual([row.account_head for row in invoice.taxes], ["ITEM-TAX"])
        request.taxes_template = "SELECTED"
        with disposal._sale_tax_context(request, invoice):
            invoice.set_taxes()
            self.assertEqual(invoice.taxes_and_charges, "COMPANY-DEFAULT")

    def test_approved_intent_digest_is_stable_across_storage_round_trip(self) -> None:
        payload = {"asset": "AST-1", "sale": {"base_net_amount": 101.25, "taxes": [7.09]}}
        self.assertEqual(
            disposal._digest(payload), disposal._digest(json.loads(disposal._canonical(payload)))
        )
        self.assertNotEqual(
            disposal._digest(payload),
            disposal._digest({**payload, "sale": {"base_net_amount": 101.26, "taxes": [7.09]}}),
        )

    def test_native_forecast_passes_exact_predicted_book_value_to_native_gl(self) -> None:
        asset = frappe._dict(
            name="AST-1",
            value_after_depreciation=100,
            finance_books=[frappe._dict(finance_book="MAIN", value_after_depreciation=100)],
        )
        request = frappe._dict(disposal_date="2026-10-02")
        invoice = SimpleNamespace(items=[frappe._dict(base_net_amount=79.6, finance_book="MAIN")])

        def native_gl(candidate, sale_amount, book, *, date):
            self.assertEqual(candidate.finance_books[0].value_after_depreciation, 75)
            self.assertEqual(candidate.value_after_depreciation, 75)
            self.assertEqual(sale_amount, 79.6)
            self.assertEqual(book, "MAIN")
            self.assertEqual(str(date), "2026-10-02")
            return [{"account": "GAIN", "debit": 0, "credit": 4.6}]

        with (
            patch(
                "erpnext.assets.doctype.asset.depreciation.get_value_after_depreciation_on_disposal_date",
                return_value=75,
            ) as forecast,
            patch(
                "erpnext.assets.doctype.asset.depreciation.get_gl_entries_on_asset_disposal",
                side_effect=native_gl,
            ),
        ):
            rows = disposal._forecast_disposal_gl(cast(Any, request), cast(Any, asset), cast(Any, invoice))
        forecast.assert_called_once_with("AST-1", "2026-10-02", "MAIN")
        self.assertEqual(rows[0]["account"], "GAIN")
        self.assertEqual(cast(Any, asset).finance_books[0].value_after_depreciation, 100)

    def test_sale_candidate_validates_native_save_payload_before_sealing(self) -> None:
        events: list[str] = []
        item = frappe._dict(asset="AST-1", is_fixed_asset=1, qty=1, rate=0)
        item.precision = lambda field: 2

        class Invoice:
            def __init__(self) -> None:
                self.doctype = "Sales Invoice"
                self.company = "C"
                self.items = [item]

            def get(self, field: str) -> Any:
                return getattr(self, field, None)

            def set(self, field: str, value: Any) -> None:
                setattr(self, field, value)

            def set_missing_values(self) -> None:
                events.append("missing")

            def set_taxes_and_charges(self) -> None:
                events.append("item_taxes")

            def calculate_taxes_and_totals(self) -> None:
                events.append("totals")

            def validate(self) -> None:
                self_check = self.get("_action")
                if self_check != "save":
                    raise AssertionError("Native save action is required during preflight")
                events.append("validate")

        invoice = Invoice()
        request = frappe._dict(
            asset="AST-1",
            item_code="ITEM",
            company="C",
            sell_qty=1,
            customer="CUSTOMER",
            posting_date="2026-10-02",
            currency="THB",
            taxes_template=None,
            rate=100,
        )
        with patch("erpnext.assets.doctype.asset.asset.make_sales_invoice", return_value=invoice):
            self.assertIs(disposal._sale_candidate(cast(Any, request)), invoice)
        self.assertEqual(events, ["missing", "item_taxes", "totals", "validate"])
        self.assertIsNone(invoice.get("_action"))

        def altered_rate() -> None:
            item.rate = 99

        with (
            patch("erpnext.assets.doctype.asset.asset.make_sales_invoice", return_value=invoice),
            patch.object(invoice, "validate", side_effect=altered_rate),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal._sale_candidate(cast(Any, request))

    def test_native_execute_capability_is_exact_and_removed_after_failure(self) -> None:
        request = frappe._dict(doctype=disposal.DOCTYPE, name="ADR-1", asset="AST-1", docstatus=1)
        with self.assertRaisesRegex(RuntimeError, "native failure"):
            with disposal.native_disposal_capability(request, "final", "OP-1"):
                self.assertIsNotNone(disposal._native_grant("AST-1", "final"))
                self.assertIsNone(disposal._native_grant("AST-2", "final"))
                self.assertIsNone(disposal._native_grant("AST-1", "stage1"))
                raise RuntimeError("native failure")
        self.assertIsNone(disposal._native_grant("AST-1", "final"))

    def test_direct_scrap_wrapper_refuses_unapproved_native_call(self) -> None:
        with (
            patch.object(disposal.frappe, "has_permission", return_value=True),
            patch.object(disposal, "_lock_asset", return_value=frappe._dict(name="AST-1")),
        ):
            with self.assertRaises(frappe.ValidationError):
                disposal.scrap_asset("AST-1")

    def test_unlinked_asset_disposal_je_is_rejected_even_without_reservation(self) -> None:
        je = frappe._dict(
            voucher_type="Asset Disposal",
            accounts=[frappe._dict(reference_type="Asset", reference_name="AST-1")],
        )
        with (
            patch.object(disposal, "_lock_asset"),
            patch.object(disposal, "_active_request_for_asset", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.guard_disposal_journal_entry_submit(cast(Any, je))

    def test_sale_rejects_distinct_posting_and_disposal_dates_before_stage(self) -> None:
        request = frappe._dict(
            purpose="Sale",
            company="C",
            asset_quantity=1,
            sell_qty=1,
            item_code="ITEM",
            customer="CUSTOMER",
            posting_date="2026-10-01",
            disposal_date="2026-10-02",
            rate=100,
            reason="Replace equipment",
        )
        asset = frappe._dict(
            docstatus=1,
            status="Submitted",
            company="C",
            asset_quantity=1,
            item_code="ITEM",
        )
        with self.assertRaises(frappe.ValidationError):
            disposal._validate_asset(cast(Any, request), cast(Any, asset))

    def test_asset_linked_invoice_cannot_hide_behind_false_fixed_asset_flag(self) -> None:
        invoice = frappe._dict(items=[frappe._dict(asset="AST-1", is_fixed_asset=0)])
        with self.assertRaises(frappe.ValidationError):
            disposal.guard_disposal_sales_invoice_submit(cast(Any, invoice))

    def test_posted_depreciation_link_must_be_unique_across_finance_books(self) -> None:
        child = frappe._dict(journal_entry="JE-1", stage="pre_disposal_depreciation")
        request = frappe._dict(generated_journal_entries=[child])
        asset = frappe._dict()
        je = frappe._dict(name="JE-1", docstatus=1, finance_book="MAIN")
        schedules = [
            {"finance_book": "MAIN", "rows": [{"journal_entry": "JE-1"}]},
            {"finance_book": "TAX", "rows": [{"journal_entry": "JE-1"}]},
        ]
        with (
            patch.object(disposal, "_active_schedule_snapshot", return_value=schedules),
            patch.object(disposal, "_verify_child"),
            patch.object(disposal.frappe, "get_doc", return_value=je),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal._verify_posted_depreciation_schedule_bijection(cast(Any, request), cast(Any, asset))

    def test_unsubmitted_depreciation_cannot_claim_a_schedule_row(self) -> None:
        child = frappe._dict(journal_entry="JE-1", stage="pre_disposal_depreciation")
        request = frappe._dict(generated_journal_entries=[child])
        asset = frappe._dict()
        je = frappe._dict(name="JE-1", docstatus=0, finance_book="MAIN")
        schedules = [{"finance_book": "MAIN", "rows": [{"journal_entry": "JE-1"}]}]
        with (
            patch.object(disposal, "_active_schedule_snapshot", return_value=schedules),
            patch.object(disposal, "_verify_child"),
            patch.object(disposal.frappe, "get_doc", return_value=je),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal._verify_posted_depreciation_schedule_bijection(cast(Any, request), cast(Any, asset))

    def test_linked_depreciation_je_cannot_cancel_while_request_is_pending(self) -> None:
        request = frappe._dict(
            disposal_status="Depreciation Pending",
            generated_journal_entries=[frappe._dict(journal_entry="JE-1")],
        )
        je = frappe._dict(
            name="JE-1",
            approval_source_doctype=disposal.DOCTYPE,
            approval_source_name="ADR-1",
        )
        with (
            patch.object(disposal, "_lock_request", return_value=request),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.guard_disposal_journal_entry_cancel(cast(Any, je))

    def test_native_wdv_rate_delta_is_bound_before_stage(self) -> None:
        row = frappe._dict(
            name="BOOK-ROW-1",
            finance_book="MAIN",
            depreciation_method="Written Down Value",
            value_after_depreciation=100,
            expected_value_after_useful_life=10,
            rate_of_depreciation=8,
        )
        row.precision = lambda field: 2
        asset = frappe._dict(calculate_depreciation=1, finance_books=[row])
        asset.get_depreciation_rate = lambda current: 12.5
        expected = disposal._native_stage1_rates(cast(Any, asset))
        self.assertEqual(expected[0]["before"], 8)
        self.assertEqual(expected[0]["after"], 12.5)
        row.rate_of_depreciation = 12.5
        disposal._actual_stage1_rates(cast(Any, asset), expected)
        row.rate_of_depreciation = 13
        with self.assertRaises(frappe.ValidationError):
            disposal._actual_stage1_rates(cast(Any, asset), expected)

    def test_generated_je_credit_account_change_invalidates_draft_financial_seal(self) -> None:
        request = frappe._dict(name="ADR-1", asset="AST-1", company="C")
        row = frappe._dict(
            journal_entry="JE-1",
            operation_id="OP-1",
            source_proof="PROOF-1",
            draft_payload_digest="je-approval-v1:ORIGINAL",
            kind="depreciation",
            stage="pre_disposal_depreciation",
            posting_date="2026-10-02",
            finance_book="MAIN",
        )
        je = frappe._dict(
            name="JE-1",
            approval_source_proof="PROOF-1",
            company="C",
            voucher_type="Depreciation Entry",
            posting_date="2026-10-02",
            finance_book="MAIN",
            accounts=[frappe._dict(reference_type="Asset", reference_name="AST-1")],
        )
        with (
            patch(
                "connect_diagnostics_core.api.erpnext.journal_entry_generators._validate_source_provenance",
                return_value=(disposal.DOCTYPE, "ADR-1", "asset_disposal_stage1", "OP-1"),
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.journal_entry_workflow.get_approval_digest",
                return_value="je-approval-v1:CHANGED_CREDIT_ACCOUNT",
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal._verify_child(cast(Any, je), cast(Any, request), cast(Any, row))

    def test_schedule_guard_uses_nowait_current_reads_and_denies_restore(self) -> None:
        schedule = frappe._dict(asset="AST-1")
        protected = [frappe._dict(name="ADR-1", disposal_status="Closed")]
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="AST-1") as asset_read,
            patch.object(disposal.frappe.db, "get_values", return_value=protected) as request_read,
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.guard_asset_depreciation_schedule_change(schedule, "before_cancel")
        asset_read.assert_called_once_with("Asset", "AST-1", "name", for_update=True, wait=False)
        self.assertTrue(request_read.call_args.kwargs["for_update"])
        self.assertFalse(request_read.call_args.kwargs["wait"])

    def test_schedule_guard_allows_exact_native_phase_and_released_request(self) -> None:
        schedule = frappe._dict(asset="AST-1")
        request = frappe._dict(doctype=disposal.DOCTYPE, name="ADR-1", asset="AST-1", docstatus=1)
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="AST-1"),
            patch.object(
                disposal.frappe.db,
                "get_values",
                return_value=[frappe._dict(name="ADR-1", disposal_status="Depreciation Pending")],
            ),
            disposal.native_disposal_capability(request, "stage1", "OP-1"),
        ):
            disposal.guard_asset_depreciation_schedule_change(schedule, "before_cancel")
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="AST-1"),
            patch.object(
                disposal.frappe.db,
                "get_values",
                return_value=[frappe._dict(name="ADR-1", disposal_status="Abandoned/Released")],
            ),
        ):
            disposal.guard_asset_depreciation_schedule_change(schedule, "before_submit")

    def test_completed_non_depreciable_asset_status_cannot_be_restored(self) -> None:
        asset = frappe._dict(name="AST-1", docstatus=1, status="Sold")
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="Sold"),
            patch.object(disposal, "_protected_request_for_asset", return_value="ADR-1"),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.guard_asset_disposal_mutation(asset, {"status"})

    def test_direct_terminal_asset_status_needs_exact_native_disposal(self) -> None:
        asset = frappe._dict(name="AST-1", docstatus=1, status="Submitted")
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="Submitted"),
            patch.object(disposal, "_protected_request_for_asset", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.guard_asset_disposal_mutation(asset, {"status"}, {"status": "Sold"})
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="Submitted"),
            patch.object(disposal, "_protected_request_for_asset", return_value="ADR-1"),
            patch.object(disposal, "_posted_disposal_journal_entry_allows_status", return_value=True),
        ):
            disposal.guard_asset_disposal_mutation(asset, {"status"}, {"status": "Scrapped"})

    def test_restore_wrapper_releases_rejected_or_reset_abandoned_requests(self) -> None:
        with (
            patch.object(disposal.frappe, "has_permission", return_value=True),
            patch.object(disposal, "_lock_asset", return_value=frappe._dict(name="AST-1")) as lock_asset,
            patch.object(disposal, "_protected_request_for_asset", return_value=None),
            patch(
                "erpnext.assets.doctype.asset.depreciation.restore_asset", return_value="restored"
            ) as native_restore,
        ):
            self.assertEqual(disposal.restore_asset("AST-1"), "restored")
        lock_asset.assert_called_once_with("AST-1", wait=False)
        native_restore.assert_called_once_with("AST-1")

    def test_restore_wrapper_denies_protected_asset_before_native_call(self) -> None:
        calls: list[str] = []
        asset = frappe._dict(name="AST-1")

        def lock_asset(name: str, *, wait: bool = True) -> frappe._dict:
            calls.append("lock")
            self.assertEqual((name, wait), ("AST-1", False))
            return asset

        def protected_request(name: str) -> str:
            calls.append("protection")
            self.assertEqual(name, "AST-1")
            return "ADR-1"

        with (
            patch.object(disposal.frappe, "has_permission", return_value=True),
            patch.object(disposal, "_lock_asset", side_effect=lock_asset) as lock_asset_mock,
            patch.object(
                disposal, "_protected_request_for_asset", side_effect=protected_request
            ) as protected_request_mock,
            patch("erpnext.assets.doctype.asset.depreciation.restore_asset") as native_restore,
            self.assertRaisesRegex(
                frappe.ValidationError,
                "retained Asset Disposal Request protects this Asset from Restore",
            ),
        ):
            disposal.restore_asset("AST-1")
        self.assertEqual(calls, ["lock", "protection"])
        lock_asset_mock.assert_called_once_with("AST-1", wait=False)
        protected_request_mock.assert_called_once_with("AST-1")
        native_restore.assert_not_called()

    def test_protected_finance_book_rate_is_denied_before_native_write(self) -> None:
        class NativeBook:
            parent = "AST-1"
            parenttype = "Asset"
            parentfield = "finance_books"
            rate_of_depreciation = 8

            def db_set(self, fieldname: str, value: Any = None) -> None:
                setattr(self, fieldname, value)

        class Book(disposal.AssetDisposalFinanceBookMixin, NativeBook):
            pass

        row = Book()
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="AST-1") as asset_read,
            patch.object(disposal, "_protected_request_for_asset", return_value="ADR-1"),
            self.assertRaises(frappe.ValidationError),
        ):
            row.db_set("rate_of_depreciation", 12)
        self.assertEqual(row.rate_of_depreciation, 8)
        asset_read.assert_called_once_with("Asset", "AST-1", "name", for_update=True, wait=False)

        request = frappe._dict(doctype=disposal.DOCTYPE, name="ADR-1", asset="AST-1", docstatus=1)
        with (
            patch.object(disposal.frappe.db, "get_value", return_value="AST-1"),
            patch.object(disposal, "_protected_request_for_asset", return_value="ADR-1"),
            disposal.native_disposal_capability(request, "stage1", "OP-1"),
        ):
            row.db_set("rate_of_depreciation", 12)
        self.assertEqual(row.rate_of_depreciation, 12)

    def test_sale_tax_context_is_exact_and_cleared_after_failure(self) -> None:
        request = frappe._dict(company="C", asset="AST-1", sell_qty=1, taxes_template=None)
        invoice = frappe._dict(
            doctype="Sales Invoice",
            company="C",
            items=[frappe._dict(asset="AST-1", is_fixed_asset=1, qty=1)],
        )
        other = frappe._dict(
            doctype="Sales Invoice",
            company="C",
            items=[frappe._dict(asset="AST-2", is_fixed_asset=1, qty=1)],
        )
        with self.assertRaisesRegex(RuntimeError, "posting failed"):
            with disposal._sale_tax_context(request, invoice):
                self.assertTrue(disposal._explicit_no_template_invoice(invoice))
                self.assertFalse(disposal._explicit_no_template_invoice(other))
                raise RuntimeError("posting failed")
        self.assertFalse(disposal._explicit_no_template_invoice(invoice))
        request.taxes_template = "TAXED"
        with disposal._sale_tax_context(request, invoice):
            self.assertFalse(disposal._explicit_no_template_invoice(invoice))

    def test_reset_native_grant_cannot_capture_a_generated_journal_entry(self) -> None:
        request = frappe._dict(doctype=disposal.DOCTYPE, name="ADR-1", asset="AST-1", docstatus=1)
        je = frappe._dict(
            voucher_type="Depreciation Entry",
            accounts=[frappe._dict(reference_type="Asset", reference_name="AST-1")],
        )
        with (
            disposal.native_disposal_capability(request, "reset", "OP-1"),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal.before_insert_generated_disposal_journal_entry(je)

    def test_scrap_draft_preflight_rejects_invalid_native_journal_entry(self) -> None:
        je = frappe._dict(accounts=[])
        je.append = lambda field, row: je[field].append(row)

        def reject() -> None:
            self.assertEqual(je.get("_action"), "save")
            self.assertEqual(je["accounts"][0]["reference_name"], "AST-1")
            raise frappe.ValidationError("invalid account company")

        je.validate = reject
        request = frappe._dict(company="C", asset="AST-1", disposal_date="2026-10-02")
        with (
            patch.object(disposal.frappe, "new_doc", return_value=je),
            patch.object(disposal.frappe, "get_cached_value", return_value="DEPR-"),
            self.assertRaises(frappe.ValidationError),
        ):
            disposal._scrap_journal_entry_preflight(
                cast(Any, request), [{"account": "WRONG-COMPANY", "debit": 100}]
            )
        self.assertIsNone(je.get("_action"))
