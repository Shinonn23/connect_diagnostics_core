# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.assets.doctype.asset.depreciation import (
    depreciate_asset as native_depreciate_asset,
)
from erpnext.assets.doctype.asset.depreciation import (
    make_depreciation_entry as native_make_depreciation_entry,
)
from erpnext.assets.doctype.asset.depreciation import (
    restore_asset as native_restore_asset,
)
from erpnext.assets.doctype.asset.depreciation import (
    scrap_asset as native_scrap_asset,
)
from erpnext.assets.doctype.asset.test_asset import (
    create_asset,
    create_asset_category,
    create_fixed_asset_item,
    set_depreciation_settings_in_company,
)
from frappe.model.workflow import apply_workflow
from frappe.permissions import add_permission
from frappe.tests import IntegrationTestCase
from frappe.tests.utils.generators import make_test_records
from frappe.utils import getdate, today

from connect_diagnostics_core.api.erpnext import asset_disposal_workflow as disposal
from connect_diagnostics_core.api.erpnext.tests.test_asset_movement_workflow import (
    TestAssetMovementWorkflowIntegration,
)


def _run_asset_disposal_operation_separately(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    request_name: str,
    user: str,
    operation: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        # Establish a repeatable-read snapshot before both sessions contend on the request lock.
        frappe.db.sql("SELECT docstatus FROM `tabAsset Disposal Request` WHERE name=%s", (request_name,))
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user(user)
        barrier.wait(timeout=30)
        if operation == "stage_depreciation":
            result = disposal.stage_depreciation(request_name)
        elif operation == "finalize_disposal":
            result = disposal.finalize_disposal(request_name)
        else:
            raise ValueError("Unsupported Asset disposal race operation.")
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish one independent native race result
        return json.dumps(result, sort_keys=True)
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def _run_asset_disposal_stage_after_asset_snapshot(
    site: str,
    sites_path: str,
    snapshot_ready: threading.Event,
    resume: threading.Event,
    request_name: str,
    asset_name: str,
    user: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user(user)
        # Force this connection to retain the pre-change Asset under RR isolation.
        frappe.db.sql("SELECT asset_name FROM `tabAsset` WHERE name=%s", (asset_name,))
        snapshot_ready.set()
        if not resume.wait(timeout=30):
            raise TimeoutError("Timed out waiting for the approved Asset change.")
        try:
            result = disposal.stage_depreciation(request_name)
        except frappe.ValidationError as exc:
            frappe.db.rollback()
            return f"denied:{exc}"
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish unexpected native stage for race assertion
        return json.dumps(result, sort_keys=True)
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def _run_unlinked_depreciation_after_asset_snapshot(
    site: str,
    sites_path: str,
    snapshot_ready: threading.Event,
    resume: threading.Event,
    lock_attempting: threading.Event,
    asset_name: str,
    schedule_name: str,
    user: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user(user)
        # The old RR snapshot contains no reservation for this Asset.
        frappe.db.get_values(
            disposal.DOCTYPE,
            {"asset": asset_name},
            ["name", "workflow_state"],
        )
        snapshot_ready.set()
        if not resume.wait(timeout=30):
            raise TimeoutError("Timed out waiting to contend on the Asset mutex.")
        lock_attempting.set()
        frappe.db.get_value("Asset", asset_name, "name", for_update=True)
        try:
            native_make_depreciation_entry(schedule_name, date=today())
        except frappe.ValidationError as exc:
            frappe.db.rollback()
            return f"denied:{exc}"
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish unexpected unlinked depreciation for race assertion
        return "posted"
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def _send_asset_disposal_request_for_review_separately(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    request_name: str,
    asset_name: str,
    user: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user(user)
        # Both sessions see only the two Drafts before they contend on the Asset mutex.
        frappe.db.sql(
            "SELECT name FROM `tabAsset Disposal Request` WHERE asset=%s AND workflow_state=%s",
            (asset_name, disposal.STATE_DRAFT),
        )
        barrier.wait(timeout=30)
        try:
            request = apply_workflow(frappe.get_doc(disposal.DOCTYPE, request_name), "Send for Review")
        except frappe.ValidationError as exc:
            frappe.db.rollback()
            return f"denied:{exc}"
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish one independent reservation transition
        return f"reserved:{request.name}:{request.workflow_state}"
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


class TestAssetDisposalNativeBoundaries(IntegrationTestCase):
    _location = TestAssetMovementWorkflowIntegration._location
    _asset = TestAssetMovementWorkflowIntegration._asset

    def setUp(self) -> None:
        super().setUp()
        old_request = getattr(frappe.local, "request", None)
        self.addCleanup(lambda: setattr(frappe.local, "request", old_request))
        frappe.local.request = frappe._dict(method="POST")

    def _native_asset(
        self,
        *,
        depreciable: bool = False,
        method: str = "Straight Line",
        finance_books: tuple[str, ...] | None = None,
    ) -> Any:
        make_test_records("Asset")
        if not getattr(self, "_native_asset_settings_ready", False):
            prior_auto_booking = frappe.db.get_single_value(
                "Accounts Settings", "book_asset_depreciation_entry_automatically"
            )
            self.addCleanup(
                lambda: frappe.db.set_single_value(
                    "Accounts Settings",
                    "book_asset_depreciation_entry_automatically",
                    prior_auto_booking,
                )
            )
            set_depreciation_settings_in_company()
            self._native_asset_settings_ready = True
        if not frappe.db.exists("Asset Category", "Computers"):
            create_asset_category()
        item_code = f"_Test Disposal {uuid4().hex[:8]}"
        create_fixed_asset_item(item_code=item_code, auto_create_assets=0)
        asset = create_asset(
            asset_name=f"_Test Disposal {uuid4().hex[:8]}",
            item_code=item_code,
            location=self._location(f"Disposal native {uuid4().hex[:8]}"),
            purchase_date="2025-01-01",
            available_for_use_date="2025-01-01",
            depreciation_start_date="2025-12-31",
            depreciation_method=method,
            rate_of_depreciation=10 if method == "Written Down Value" else 0,
            expected_value_after_useful_life=10000 if method == "Written Down Value" else 0,
            calculate_depreciation=int(depreciable),
            finance_book=finance_books[0] if finance_books else None,
            total_number_of_depreciations=3 if finance_books else 5,
            do_not_save=bool(finance_books),
            submit=not finance_books,
        )
        if finance_books:
            for finance_book in finance_books[1:]:
                asset.append(
                    "finance_books",
                    {
                        "finance_book": finance_book,
                        "depreciation_method": method,
                        "frequency_of_depreciation": 12,
                        "total_number_of_depreciations": 6,
                        "expected_value_after_useful_life": 0,
                        "depreciation_start_date": "2025-12-31",
                    },
                )
            asset.insert(ignore_permissions=True)
            asset.submit()
        return asset

    def _delete_committed_document(self, doctype: str, name: str) -> None:
        if not frappe.db.exists(doctype, name):
            return
        for field in frappe.get_meta(doctype).fields:
            if field.fieldtype == "Table" and field.options:
                frappe.db.delete(
                    field.options,
                    {"parent": name, "parenttype": doctype, "parentfield": field.fieldname},
                )
        frappe.db.delete(doctype, name)

    def _cleanup_committed_disposal(
        self,
        asset_name: str,
        request_name: str | tuple[str, ...],
        item_code: str,
        location_name: str,
        actor_users: tuple[str, ...],
        new_departments: tuple[str, ...],
        new_employment_types: tuple[str, ...],
        prior_auto_booking: Any,
    ) -> None:
        request_names = (request_name,) if isinstance(request_name, str) else request_name
        for current_request_name in request_names:
            if not frappe.db.exists(disposal.DOCTYPE, current_request_name):
                continue
            children = frappe.get_all(
                "Asset Disposal Journal Entry",
                filters={"parent": current_request_name},
                pluck="journal_entry",
            )
            invoice_name = frappe.db.get_value(disposal.DOCTYPE, current_request_name, "sales_invoice")
            voucher_pairs = [("Journal Entry", name) for name in children]
            if invoice_name:
                voucher_pairs.append(("Sales Invoice", invoice_name))
            for voucher_type, voucher_no in voucher_pairs:
                frappe.db.delete("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})
                if frappe.db.exists("DocType", "Payment Ledger Entry"):
                    frappe.db.delete(
                        "Payment Ledger Entry",
                        {"voucher_type": voucher_type, "voucher_no": voucher_no},
                    )
                if frappe.db.exists("Workflow Action"):
                    frappe.db.delete(
                        "Workflow Action",
                        {"reference_doctype": voucher_type, "reference_name": voucher_no},
                    )
            for voucher_type, voucher_no in voucher_pairs:
                self._delete_committed_document(voucher_type, voucher_no)
            frappe.db.delete(
                "Workflow Action",
                {"reference_doctype": disposal.DOCTYPE, "reference_name": current_request_name},
            )
            self._delete_committed_document(disposal.DOCTYPE, current_request_name)
        for schedule in frappe.get_all(
            "Asset Depreciation Schedule", filters={"asset": asset_name}, pluck="name"
        ):
            self._delete_committed_document("Asset Depreciation Schedule", schedule)
        self._delete_committed_document("Asset", asset_name)
        self._delete_committed_document("Item", item_code)
        frappe.db.delete("Location", location_name)
        for email in actor_users:
            for employee in frappe.get_all("Employee", filters={"user_id": email}, pluck="name"):
                self._delete_committed_document("Employee", employee)
            frappe.db.delete("User Permission", {"user": email})
            frappe.db.delete("Workflow Action", {"user": email})
            self._delete_committed_document("User", email)
        for department in new_departments:
            self._delete_committed_document("Department", department)
        for employment_type in new_employment_types:
            self._delete_committed_document("Employment Type", employment_type)
        frappe.db.set_single_value(
            "Accounts Settings",
            "book_asset_depreciation_entry_automatically",
            prior_auto_booking,
        )
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - remove fixtures committed for response-loss retry proof

    def _asset_permission_fixture(self, company: str, label: str) -> str:
        name = f"_TEST-DISPOSAL-SCOPE-{label}-{uuid4().hex[:8]}"
        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "name": name,
                "asset_name": name,
                "company": company,
                "purchase_date": today(),
                "status": "Submitted",
                "docstatus": 1,
            }
        )
        asset.db_insert()
        return name

    def _asset_admin_with_read(self, label: str) -> str:
        add_permission("Asset", "Asset Administrator", ptype="read")
        email = self._actor("Asset Administrator", label)
        frappe.clear_cache(user=email)
        return email

    def test_asset_disposal_requires_native_read_and_explicit_company_scope(self) -> None:
        companies = frappe.get_all("Company", pluck="name", order_by="name asc")
        self.assertGreaterEqual(len(companies), 2, "Integration fixture requires two Companies")
        allowed_company, other_company = companies[:2]
        allowed_asset = self._asset_permission_fixture(allowed_company, "ALLOWED")
        other_asset = self._asset_permission_fixture(other_company, "OTHER")
        maker = self._asset_admin_with_read("company_scope")
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": maker,
                "allow": "Company",
                "for_value": allowed_company,
                "applicable_for": "Asset",
                "apply_to_all_doctypes": 0,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(maker)
        self.assertEqual(disposal._lock_asset(allowed_asset).name, allowed_asset)
        denied_request = frappe.get_doc(
            {
                "doctype": disposal.DOCTYPE,
                "asset": other_asset,
                "company": other_company,
                "purpose": "Sale",
                "reason": "Cross-company permission regression",
                "disposal_date": today(),
                "posting_date": today(),
                "sell_qty": 1,
            }
        )
        with self.assertRaises(frappe.PermissionError):
            denied_request.insert(ignore_permissions=True)
        self.assertFalse(
            frappe.db.exists(disposal.DOCTYPE, {"asset": other_asset}),
            "Denied cross-company Request must not create a disposal reservation",
        )

    def test_asset_disposal_fails_closed_without_applicable_company_scope(self) -> None:
        company = frappe.get_all("Company", pluck="name", order_by="name asc")[0]
        asset_name = self._asset_permission_fixture(company, "NO-SCOPE")
        maker = self._asset_admin_with_read("no_company_scope")
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": maker,
                "allow": "Company",
                "for_value": company,
                "applicable_for": "Sales Invoice",
                "apply_to_all_doctypes": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(maker)
        denied_request = frappe.get_doc(
            {
                "doctype": disposal.DOCTYPE,
                "asset": asset_name,
                "company": company,
                "purpose": "Sale",
                "reason": "Wrong-DocType permission regression",
                "disposal_date": today(),
                "posting_date": today(),
                "sell_qty": 1,
            }
        )
        with self.assertRaises(frappe.PermissionError):
            denied_request.insert(ignore_permissions=True)
        self.assertFalse(frappe.db.exists(disposal.DOCTYPE, {"asset": asset_name}))

    def _actor(self, role: str, label: str) -> str:
        email = f"_test_disposal_{label}_{uuid4().hex[:8]}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": f"_Test Disposal {label}",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        company = "_Test Company"
        department = frappe.db.get_value("Department", {"company": company}, "name")
        employment_type = frappe.db.get_value("Employment Type", {}, "name")
        if not department:
            department = (
                frappe.get_doc(
                    {
                        "doctype": "Department",
                        "department_name": f"_Test Disposal {uuid4().hex[:8]}",
                        "company": company,
                        "is_group": 0,
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )
        if not employment_type:
            employment_type = (
                frappe.get_doc(
                    {"doctype": "Employment Type", "employee_type_name": "_Test Disposal Employee"}
                )
                .insert(ignore_permissions=True)
                .name
            )
        frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"_Test Disposal {label}",
                "company": company,
                "department": department,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "status": "Active",
                "employment_type": employment_type,
                "user_id": email,
                "approval_signature": "data:image/png;base64,c2ln",
            }
        ).insert(ignore_permissions=True)
        user.add_roles(role)
        frappe.clear_cache(user=email)
        return email

    def _approved_request(
        self, asset: Any, purpose: str, *, taxes_template: str | None = None
    ) -> tuple[Any, str, str, str]:
        if purpose == "Sale":
            make_test_records("Customer")
        maker = self._actor("Asset Administrator", "maker")
        reviewer = self._actor("Accounts User", "reviewer")
        approver = self._actor("C-Level Approver", "approver")
        frappe.set_user(maker)
        payload = {
            "doctype": disposal.DOCTYPE,
            "purpose": purpose,
            "reason": "_Test approved whole-Asset disposal",
            "asset": asset.name,
            "request_date": today(),
            "disposal_date": today(),
        }
        if purpose == "Sale":
            payload.update(
                {
                    "customer": "_Test Customer",
                    "posting_date": today(),
                    "item_code": asset.item_code,
                    "sell_qty": asset.asset_quantity,
                    "rate": 1000,
                    "currency": frappe.get_cached_value("Company", asset.company, "default_currency"),
                    "taxes_template": taxes_template,
                }
            )
        request = frappe.get_doc(payload).insert()
        request = apply_workflow(request, "Send for Review")
        frappe.set_user(reviewer)
        request = apply_workflow(request, "Review")
        frappe.set_user(approver)
        request = apply_workflow(request, "Approve")
        frappe.set_user(reviewer)
        request = apply_workflow(request, "Submit")
        self.assertEqual(request.workflow_state, disposal.STATE_SUBMITTED)
        return request, maker, reviewer, approver

    def test_committed_stage_and_final_response_loss_retries_return_native_results(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset()
        request, maker, reviewer, approver = self._approved_request(asset, "Sale")
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            cast(str, request.name),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker, reviewer, approver),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        frappe.set_user(reviewer)

        stage_result = disposal.stage_depreciation(cast(str, request.name))
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish the completed native stage before simulating a lost response
        request.reload()
        stage_snapshot = request.stage1_schedule_snapshot_json
        stage_digest = request.stage1_schedule_snapshot_digest
        stage_schedules_before = frappe.get_all(
            "Asset Depreciation Schedule", filters={"asset": asset.name}, pluck="name"
        )
        stage_journal_entries_before = frappe.db.count("Journal Entry")
        altered_stage_snapshot = json.loads(stage_snapshot)
        altered_stage_snapshot["operation_id"] = "mismatched-stage-operation"
        altered_stage_json = disposal._canonical(altered_stage_snapshot)
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "stage1_schedule_snapshot_json",
            altered_stage_json,
            update_modified=False,
        )
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "stage1_schedule_snapshot_digest",
            hashlib.sha256(altered_stage_json.encode()).hexdigest(),
            update_modified=False,
        )
        with self.assertRaisesRegex(frappe.ValidationError, "identity does not match"):
            disposal.stage_depreciation(cast(str, request.name))
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "stage1_schedule_snapshot_json",
            stage_snapshot,
            update_modified=False,
        )
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "stage1_schedule_snapshot_digest",
            stage_digest,
            update_modified=False,
        )
        self.assertEqual(
            disposal.stage_depreciation(cast(str, request.name)),
            stage_result,
            "A retry after commit must return the recorded stage result without restaging depreciation",
        )
        self.assertEqual(
            frappe.get_all("Asset Depreciation Schedule", filters={"asset": asset.name}, pluck="name"),
            stage_schedules_before,
        )
        self.assertEqual(frappe.db.count("Journal Entry"), stage_journal_entries_before)

        request.reload()
        invoice_count_before = frappe.db.count("Sales Invoice")
        final_result = disposal.finalize_disposal(cast(str, request.name))
        request.reload()
        invoice_name = request.sales_invoice
        self.assertTrue(invoice_name)
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish native disposal before simulating a lost response
        request.reload()
        final_snapshot = request.final_schedule_snapshot_json
        final_digest = request.final_schedule_snapshot_digest
        altered_final_snapshot = json.loads(final_snapshot)
        altered_final_snapshot["operation_id"] = "mismatched-final-operation"
        altered_final_json = disposal._canonical(altered_final_snapshot)
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "final_schedule_snapshot_json",
            altered_final_json,
            update_modified=False,
        )
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "final_schedule_snapshot_digest",
            hashlib.sha256(altered_final_json.encode()).hexdigest(),
            update_modified=False,
        )
        with self.assertRaisesRegex(frappe.ValidationError, "identity does not match"):
            disposal.finalize_disposal(cast(str, request.name))
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "final_schedule_snapshot_json",
            final_snapshot,
            update_modified=False,
        )
        frappe.db.set_value(
            disposal.DOCTYPE,
            request.name,
            "final_schedule_snapshot_digest",
            final_digest,
            update_modified=False,
        )
        invoice_gl_before = frappe.db.count(
            "GL Entry", {"voucher_type": "Sales Invoice", "voucher_no": invoice_name, "is_cancelled": 0}
        )
        self.assertEqual(
            disposal.finalize_disposal(cast(str, request.name)),
            final_result,
            "A retry after commit must return the recorded native final result",
        )
        request.reload()
        self.assertEqual(request.disposal_status, "Closed")
        self.assertEqual(request.sales_invoice, invoice_name)
        self.assertEqual(frappe.db.count("Sales Invoice"), invoice_count_before + 1)
        self.assertEqual(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": invoice_name, "is_cancelled": 0},
            ),
            invoice_gl_before,
        )

    def test_two_connections_finalize_scrap_once_with_exact_native_je(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset()
        request, maker, reviewer, approver = self._approved_request(asset, "Scrap")
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            cast(str, request.name),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker, reviewer, approver),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        frappe.set_user(reviewer)
        disposal.stage_depreciation(cast(str, request.name))
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish the staged native operation before finalization
        barrier = threading.Barrier(2)
        with patch(
            "erpnext.assets.doctype.asset.depreciation.scrap_asset", wraps=native_scrap_asset
        ) as native_scrap:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _run_asset_disposal_operation_separately,
                        str(frappe.local.site),
                        str(frappe.local.sites_path),
                        barrier,
                        cast(str, request.name),
                        reviewer,
                        "finalize_disposal",
                    )
                    for _ in range(2)
                ]
                final_results = [future.result(timeout=90) for future in futures]
        self.assertEqual(native_scrap.call_count, 1)
        self.assertEqual(final_results[0], final_results[1])
        final_result = json.loads(final_results[0])
        request.reload()
        je_name = request.disposal_journal_entry
        self.assertTrue(je_name)
        self.assertEqual(final_result["data"]["status"], "Disposal Accounting Pending")
        self.assertEqual(frappe.db.get_value("Journal Entry", je_name, "docstatus"), 0)
        frappe.db.commit()
        journal_entry_count = frappe.db.count("Journal Entry")
        request.reload()
        self.assertEqual(request.disposal_status, "Disposal Accounting Pending")
        self.assertEqual(request.disposal_journal_entry, je_name)
        self.assertEqual(frappe.db.count("Journal Entry"), journal_entry_count)

    def test_two_connections_replay_committed_stage_and_sale_finalize_once(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset()
        request, maker, reviewer, approver = self._approved_request(asset, "Sale")
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            cast(str, request.name),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker, reviewer, approver),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        frappe.set_user(reviewer)
        # Publish the complete native fixture before the two independent RR snapshots begin.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish fixtures for two-connection retry proof

        def race(operation: str) -> list[str]:
            barrier = threading.Barrier(2)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _run_asset_disposal_operation_separately,
                        str(frappe.local.site),
                        str(frappe.local.sites_path),
                        barrier,
                        cast(str, request.name),
                        reviewer,
                        operation,
                    )
                    for _ in range(2)
                ]
                return [future.result(timeout=90) for future in futures]

        with patch(
            "erpnext.assets.doctype.asset.depreciation.depreciate_asset",
            wraps=native_depreciate_asset,
        ) as native_stage:
            stage_results = race("stage_depreciation")
        self.assertEqual(native_stage.call_count, 1)
        self.assertEqual(stage_results[0], stage_results[1])
        frappe.db.commit()
        request.reload()
        self.assertEqual(request.disposal_status, "Ready to Dispose")
        self.assertTrue(request.stage1_operation_id)

        invoice_count_before = frappe.db.count("Sales Invoice")
        final_results = race("finalize_disposal")
        self.assertEqual(final_results[0], final_results[1])
        frappe.db.commit()
        request.reload()
        self.assertEqual(request.disposal_status, "Closed")
        self.assertTrue(request.sales_invoice)
        self.assertEqual(frappe.db.count("Sales Invoice"), invoice_count_before + 1)
        self.assertEqual(
            frappe.db.count("Sales Invoice Item", {"parent": request.sales_invoice, "asset": asset.name}),
            1,
        )
        self.assertGreater(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": request.sales_invoice, "is_cancelled": 0},
            ),
            0,
        )

    def test_asset_change_after_rr_snapshot_denies_stage_before_native_depreciation(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset()
        request, maker, reviewer, approver = self._approved_request(asset, "Sale")
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            cast(str, request.name),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker, reviewer, approver),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        asset_name = cast(str, asset.name)
        request_name = cast(str, request.name)
        original_asset_name = str(asset.asset_name)
        schedule_before = disposal._canonical(disposal._active_schedule_snapshot(asset))
        journal_entries_before = frappe.db.count("Journal Entry")
        frappe.set_user(reviewer)
        # The worker must see the approved data before the separate writer commits a drift.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish fixtures for stale-Asset race proof

        snapshot_ready = threading.Event()
        resume = threading.Event()
        with patch(
            "erpnext.assets.doctype.asset.depreciation.depreciate_asset",
            wraps=native_depreciate_asset,
        ) as native_stage:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _run_asset_disposal_stage_after_asset_snapshot,
                    str(frappe.local.site),
                    str(frappe.local.sites_path),
                    snapshot_ready,
                    resume,
                    request_name,
                    asset_name,
                    reviewer,
                )
                try:
                    self.assertTrue(
                        snapshot_ready.wait(timeout=30), "Worker did not establish its Asset snapshot"
                    )
                    frappe.db.set_value(
                        "Asset", asset_name, "asset_name", original_asset_name + " changed after approval"
                    )
                    frappe.db.commit()  # nosemgrep: frappe-manual-commit - commit the Asset drift while the worker retains its RR snapshot
                finally:
                    resume.set()
                outcome = future.result(timeout=60)
            self.assertEqual(native_stage.call_count, 0)

        self.assertTrue(outcome.startswith("denied:"), outcome)
        self.assertIn("configuration changed after approval", outcome)
        frappe.db.commit()
        request.reload()
        current_asset = frappe.get_doc("Asset", asset_name)
        self.assertFalse(request.stage1_operation_id)
        self.assertEqual(request.disposal_status, "Not Executed")
        self.assertEqual(frappe.db.count("Journal Entry"), journal_entries_before)
        self.assertEqual(
            disposal._canonical(disposal._active_schedule_snapshot(current_asset)), schedule_before
        )

    def test_unlinked_depreciation_waiting_on_asset_lock_sees_committed_reservation(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset(depreciable=True)
        maker = self._actor("Asset Administrator", "depreciation_reservation_race")
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": maker,
                "allow": "Company",
                "for_value": asset.company,
                "applicable_for": "Asset",
                "apply_to_all_doctypes": 0,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(maker)
        request = frappe.get_doc(
            {
                "doctype": disposal.DOCTYPE,
                "purpose": "Scrap",
                "reason": "_Test reservation versus unlinked depreciation",
                "asset": asset.name,
                "request_date": today(),
                "disposal_date": today(),
            }
        ).insert()
        schedule_name = frappe.db.get_value(
            "Asset Depreciation Schedule", {"asset": asset.name, "docstatus": 1}, "name"
        )
        self.assertTrue(schedule_name, "Depreciable Asset fixture must have a submitted schedule")
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            cast(str, request.name),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker,),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        asset_name = cast(str, asset.name)
        schedule_name = cast(str, schedule_name)
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish the Draft before the stale-reader race

        snapshot_ready = threading.Event()
        resume = threading.Event()
        lock_attempting = threading.Event()
        je_count_before = frappe.db.count("Journal Entry")
        gl_count_before = frappe.db.count("GL Entry")
        carrying_value_before = frappe.db.get_value("Asset", asset_name, "value_after_depreciation")
        frappe.set_user("Administrator")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _run_unlinked_depreciation_after_asset_snapshot,
                str(frappe.local.site),
                str(frappe.local.sites_path),
                snapshot_ready,
                resume,
                lock_attempting,
                asset_name,
                schedule_name,
                "Administrator",
            )
            try:
                self.assertTrue(
                    snapshot_ready.wait(timeout=30), "Worker did not establish its pre-reservation snapshot"
                )
                frappe.db.sql("SELECT name FROM `tabAsset` WHERE name=%s FOR UPDATE", (asset_name,))
                resume.set()
                self.assertTrue(lock_attempting.wait(timeout=30), "Worker did not attempt the Asset mutex")
                frappe.set_user(maker)
                request = apply_workflow(request, "Send for Review")
                self.assertEqual(request.workflow_state, disposal.STATE_REVIEW)
                frappe.db.commit()  # nosemgrep: frappe-manual-commit - release Asset mutex after reservation commit
            finally:
                resume.set()
            outcome = future.result(timeout=60)

        self.assertTrue(outcome.startswith("denied:"), outcome)
        self.assertIn("approved source operation", outcome)
        self.assertEqual(frappe.db.count("Journal Entry"), je_count_before)
        self.assertEqual(frappe.db.count("GL Entry"), gl_count_before)
        self.assertEqual(
            frappe.db.get_value("Asset", asset_name, "value_after_depreciation"), carrying_value_before
        )

    def test_two_rr_snapshots_allow_only_one_request_to_reserve_asset(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        prior_auto_booking = frappe.db.get_single_value(
            "Accounts Settings", "book_asset_depreciation_entry_automatically"
        )
        departments_before = set(
            frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name")
        )
        employment_types_before = set(frappe.get_all("Employment Type", pluck="name"))
        asset = self._native_asset()
        make_test_records("Customer")
        maker = self._actor("Asset Administrator", "reservation_race_maker")
        frappe.set_user(maker)
        request_names: list[str] = []
        for label in ("first", "second"):
            request = frappe.get_doc(
                {
                    "doctype": disposal.DOCTYPE,
                    "purpose": "Sale",
                    "reason": f"_Test reservation race {label}",
                    "asset": asset.name,
                    "request_date": today(),
                    "disposal_date": today(),
                    "customer": "_Test Customer",
                    "posting_date": today(),
                    "item_code": asset.item_code,
                    "sell_qty": asset.asset_quantity,
                    "rate": 1000,
                    "currency": frappe.get_cached_value("Company", asset.company, "default_currency"),
                }
            ).insert()
            request_names.append(cast(str, request.name))
        departments_created = tuple(
            sorted(
                set(frappe.get_all("Department", filters={"company": "_Test Company"}, pluck="name"))
                - departments_before
            )
        )
        employment_types_created = tuple(
            sorted(set(frappe.get_all("Employment Type", pluck="name")) - employment_types_before)
        )
        self.addCleanup(
            self._cleanup_committed_disposal,
            cast(str, asset.name),
            tuple(request_names),
            cast(str, asset.item_code),
            cast(str, asset.location),
            (maker,),
            departments_created,
            employment_types_created,
            prior_auto_booking,
        )
        asset_name = cast(str, asset.name)
        schedule_before = disposal._canonical(disposal._active_schedule_snapshot(asset))
        journal_entries_before = frappe.db.count("Journal Entry")
        sales_invoices_before = frappe.db.count("Sales Invoice")
        gl_entries_before = frappe.db.count("GL Entry")
        frappe.db.commit()  # nosemgrep: frappe-manual-commit - publish competing Draft requests for RR race proof

        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _send_asset_disposal_request_for_review_separately,
                    str(frappe.local.site),
                    str(frappe.local.sites_path),
                    barrier,
                    request_name,
                    asset_name,
                    maker,
                )
                for request_name in request_names
            ]
            outcomes = [future.result(timeout=90) for future in futures]

        self.assertEqual(sum(outcome.startswith("reserved:") for outcome in outcomes), 1, outcomes)
        self.assertEqual(sum(outcome.startswith("denied:") for outcome in outcomes), 1, outcomes)
        self.assertTrue(
            any("already reserved" in outcome for outcome in outcomes if outcome.startswith("denied:")),
            outcomes,
        )
        frappe.db.commit()
        requests = [frappe.get_doc(disposal.DOCTYPE, name) for name in request_names]
        self.assertEqual(
            sorted(request.workflow_state for request in requests),
            sorted((disposal.STATE_DRAFT, disposal.STATE_REVIEW)),
        )
        active = frappe.get_all(
            disposal.DOCTYPE,
            filters={
                "asset": asset_name,
                "workflow_state": (
                    "in",
                    [
                        disposal.STATE_REVIEW,
                        disposal.STATE_APPROVAL,
                        disposal.STATE_APPROVED,
                        disposal.STATE_SUBMITTED,
                        disposal.STATE_RETURNED,
                        disposal.STATE_RESET_REVIEW,
                        disposal.STATE_RESET_APPROVAL,
                        disposal.STATE_RESET_APPROVED,
                    ],
                ),
            },
            fields=["name"],
        )
        self.assertEqual(len(active), 1)
        self.assertEqual(frappe.db.count("Journal Entry"), journal_entries_before)
        self.assertEqual(frappe.db.count("Sales Invoice"), sales_invoices_before)
        self.assertEqual(frappe.db.count("GL Entry"), gl_entries_before)
        current_asset = frappe.get_doc("Asset", asset_name)
        self.assertEqual(
            disposal._canonical(disposal._active_schedule_snapshot(current_asset)), schedule_before
        )

    def _sales_tax_template(self, *, is_default: bool = False) -> str:
        account = frappe.db.get_value(
            "Account", {"company": "_Test Company", "is_group": 0, "account_type": "Tax"}, "name"
        ) or frappe.db.get_value(
            "Account", {"company": "_Test Company", "is_group": 0, "root_type": "Expense"}, "name"
        )
        self.assertTrue(account)
        template = frappe.get_doc(
            {
                "doctype": "Sales Taxes and Charges Template",
                "title": f"_Test Disposal Tax {uuid4().hex[:8]}",
                "company": "_Test Company",
                "is_default": int(is_default),
                "taxes": [{"charge_type": "On Net Total", "account_head": account, "rate": 7}],
            }
        ).insert(ignore_permissions=True)
        return cast(str, template.name)

    def _configure_native_tax_defaults(self, item_code: str) -> str:
        company_template = self._sales_tax_template(is_default=True)
        customer_template = self._sales_tax_template()
        tax_account = (
            frappe.get_doc("Sales Taxes and Charges Template", customer_template).taxes[0].account_head
        )
        frappe.get_doc(
            {
                "doctype": "Tax Rule",
                "tax_type": "Sales",
                "customer": "_Test Customer",
                "company": "_Test Company",
                "sales_tax_template": customer_template,
                "priority": 1000,
                "from_date": today(),
            }
        ).insert(ignore_permissions=True)
        item_template = frappe.get_doc(
            {
                "doctype": "Item Tax Template",
                "title": f"_Test Disposal Item Tax {uuid4().hex[:8]}",
                "company": "_Test Company",
                "taxes": [{"tax_type": tax_account, "tax_rate": 5}],
            }
        ).insert(ignore_permissions=True)
        item = frappe.get_doc("Item", item_code)
        item.append("taxes", {"item_tax_template": item_template.name, "valid_from": today()})
        item.save(ignore_permissions=True)
        previous_item_tax_setting = frappe.db.get_single_value(
            "Accounts Settings", "add_taxes_from_item_tax_template"
        )
        self.addCleanup(
            lambda: frappe.db.set_single_value(
                "Accounts Settings", "add_taxes_from_item_tax_template", previous_item_tax_setting
            )
        )
        frappe.db.set_single_value("Accounts Settings", "add_taxes_from_item_tax_template", 1)
        self.assertEqual(
            frappe.db.get_value("Sales Taxes and Charges Template", company_template, "is_default"), 1
        )
        return cast(str, tax_account)

    def test_native_sales_tax_methods_keep_item_tax_without_default_template(self) -> None:
        invoice = cast(SalesInvoice, frappe.new_doc("Sales Invoice"))
        self.assertIsInstance(invoice, disposal.AssetDisposalSalesInvoiceMixin)
        invoice.company = "_Test Company"
        invoice.customer = "_Test Customer"
        invoice.append(
            "items",
            {
                "asset": "AST-1",
                "is_fixed_asset": 1,
                "qty": 1,
                "item_tax_rate": {"ITEM-TAX": 5},
            },
        )
        request = frappe._dict(company="_Test Company", asset="AST-1", sell_qty=1, taxes_template=None)
        with (
            patch.object(frappe.db, "get_value", return_value=None) as default_lookup,
            patch(
                "erpnext.accounts.party._get_party_details",
                return_value={"taxes_and_charges": "CUSTOMER-DEFAULT"},
            ),
            patch(
                "erpnext.controllers.selling_controller.get_taxes_and_charges",
                return_value=[{"account_head": "CUSTOMER-TAX", "charge_type": "On Net Total", "rate": 7}],
            ),
            patch(
                "erpnext.controllers.accounts_controller.frappe.get_single_value",
                side_effect=lambda _dt, field: field == "add_taxes_from_item_tax_template",
            ),
            disposal._sale_tax_context(request, invoice),
        ):
            invoice.set_taxes()
            invoice.set_missing_lead_customer_details()
            invoice.set_taxes_and_charges()
            self.assertIsNone(invoice.taxes_and_charges)
            self.assertEqual([row.account_head for row in invoice.taxes], ["ITEM-TAX"])
            default_lookup.assert_not_called()

        invoice.set("taxes", [])
        request.taxes_template = "SELECTED-TEMPLATE"
        with (
            patch.object(frappe.db, "get_value", return_value="COMPANY-DEFAULT") as default_lookup,
            patch(
                "erpnext.controllers.accounts_controller.get_taxes_and_charges",
                return_value=[{"account_head": "COMPANY-TAX", "charge_type": "On Net Total", "rate": 7}],
            ),
            disposal._sale_tax_context(request, invoice),
        ):
            invoice.set_taxes()
            self.assertEqual(invoice.taxes_and_charges, "COMPANY-DEFAULT")
            self.assertEqual([row.account_head for row in invoice.taxes], ["COMPANY-TAX"])
            default_lookup.assert_called_once()

    def test_direct_native_scrap_refuses_unapproved_submitted_asset(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        location = self._location(f"Disposal {uuid4().hex[:8]}")
        asset = self._asset(location)
        with self.assertRaises(frappe.ValidationError):
            native_scrap_asset(asset.name, today())
        self.assertFalse(frappe.db.get_value("Asset", asset.name, "disposal_date"))

    def test_direct_terminal_asset_status_write_is_denied_without_approval(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._asset(self._location(f"Disposal status {uuid4().hex[:8]}"))
        with self.assertRaisesRegex(frappe.ValidationError, "Native Asset terminal status requires"):
            asset.db_set("status", "Sold")
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Submitted")

    def _disposal_request(self, asset_name: str, state: str, progress: str) -> str:
        request = frappe.get_doc(
            {
                "doctype": disposal.DOCTYPE,
                "name": f"_TEST-ADR-{uuid4().hex[:8]}",
                "asset": asset_name,
                "company": "_Test Company",
                "purpose": "Sale",
                "workflow_state": state,
                "disposal_status": progress,
                "docstatus": 1
                if state in {disposal.STATE_SUBMITTED, disposal.STATE_EXECUTION_ABANDONED}
                else 0,
            }
        )
        request.db_insert()
        return cast(str, request.name)

    def test_direct_native_restore_cannot_reopen_closed_non_depreciable_sale(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._asset(self._location(f"Disposal restore {uuid4().hex[:8]}"))
        # Fabricate a historical closed sale without invoking the guarded native write.
        frappe.db.set_value("Asset", asset.name, "status", "Sold")
        self._disposal_request(cast(str, asset.name), disposal.STATE_SUBMITTED, "Closed")
        with self.assertRaises(frappe.ValidationError):
            native_restore_asset(asset.name)
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")

    def test_native_restore_released_request_does_not_block_native_path(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._asset(self._location(f"Disposal released {uuid4().hex[:8]}"))
        self._disposal_request(
            cast(str, asset.name), disposal.STATE_EXECUTION_ABANDONED, "Abandoned/Released"
        )
        native_restore_asset(asset.name)
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Submitted")

    def test_direct_wdv_restore_denied_before_finance_book_rate_write(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset(depreciable=True, method="Written Down Value")
        row_name = asset.finance_books[0].name
        asset.finance_books[0].db_set("rate_of_depreciation", 10)
        asset.reload()
        original_rate = frappe.db.get_value("Asset Finance Book", row_name, "rate_of_depreciation")
        predicted_rate = asset.get_depreciation_rate(asset.finance_books[0])
        self.assertNotEqual(predicted_rate, original_rate)
        self._disposal_request(cast(str, asset.name), disposal.STATE_SUBMITTED, "Depreciation Pending")
        original_schedules = frappe.get_all(
            "Asset Depreciation Schedule", filters={"asset": asset.name}, pluck="name"
        )
        with self.assertRaisesRegex(frappe.ValidationError, "Protected Asset depreciation rate requires"):
            native_restore_asset(cast(str, asset.name))
        self.assertEqual(
            frappe.db.get_value("Asset Finance Book", row_name, "rate_of_depreciation"), original_rate
        )
        self.assertEqual(
            frappe.get_all("Asset Depreciation Schedule", filters={"asset": asset.name}, pluck="name"),
            original_schedules,
        )

    def test_approved_native_sale_submits_once_and_closes_request(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset()
        make_test_records("Customer")
        item_tax_account = self._configure_native_tax_defaults(cast(str, asset.item_code))
        request, _maker, reviewer, _approver = self._approved_request(asset, "Sale")
        approved_taxes = json.loads(request.sale_candidate_projection)["taxes"]
        self.assertEqual([row["account_head"] for row in approved_taxes], [item_tax_account])
        frappe.set_user(reviewer)
        disposal.stage_depreciation(cast(str, request.name))
        request.reload()
        self.assertEqual(request.disposal_status, "Ready to Dispose")
        disposal.finalize_disposal(cast(str, request.name))
        request.reload()
        self.assertEqual(request.disposal_status, "Closed")
        self.assertEqual(frappe.db.get_value("Sales Invoice", request.sales_invoice, "docstatus"), 1)
        submitted_invoice = frappe.get_doc("Sales Invoice", request.sales_invoice)
        self.assertFalse(submitted_invoice.taxes_and_charges)
        self.assertEqual([row.account_head for row in submitted_invoice.taxes], [item_tax_account])
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")
        self.assertGreater(
            frappe.db.count(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": request.sales_invoice, "is_cancelled": 0},
            ),
            0,
        )
        with self.assertRaises(frappe.ValidationError):
            disposal.finalize_disposal(cast(str, request.name))

    def test_multi_book_native_disposal_posts_each_book_and_protects_final_effect(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        finance_books = ("Test Finance Book 1", "Test Finance Book 2")
        self.assertTrue(
            all(frappe.db.exists("Finance Book", name) for name in finance_books),
            "ERPNext Asset test fixtures must provide both Finance Books",
        )

        for purpose in ("Sale", "Scrap"):
            with self.subTest(purpose=purpose):
                frappe.set_user("Administrator")
                asset = self._native_asset(depreciable=True, finance_books=finance_books)
                initial_values = {
                    row.finance_book: row.value_after_depreciation for row in asset.finance_books
                }
                je_checker = self._actor("Accounts Manager", f"multi_book_{purpose}_checker")
                request, _maker, reviewer, approver = self._approved_request(asset, purpose)

                frappe.set_user(reviewer)
                disposal.stage_depreciation(cast(str, request.name))
                request.reload()
                staged = [
                    row
                    for row in request.generated_journal_entries
                    if row.stage == "pre_disposal_depreciation"
                ]
                self.assertTrue(staged, "Native disposal-date depreciation should create entries")
                self.assertEqual({row.finance_book for row in staged}, set(finance_books))

                staged_by_je = {cast(str, row.journal_entry): row for row in staged}
                for child in staged:
                    je = frappe.get_doc("Journal Entry", child.journal_entry)
                    self.assertEqual(je.docstatus, 0)
                    self.assertEqual(je.finance_book, child.finance_book)
                    je = apply_workflow(je, "Send Journal Entry for Review")
                    frappe.set_user(je_checker)
                    je = apply_workflow(je, "Review Journal Entry")
                    frappe.set_user(approver)
                    je = apply_workflow(je, "Approve Journal Entry")
                    frappe.set_user(je.approval_checker_user)
                    je = apply_workflow(je, "Submit Journal Entry")
                    self.assertEqual(je.docstatus, 1)

                # The native depreciation schedule is the independent expectation source. Native JE
                # submission should link each scheduled row to exactly one tracked child JE.
                scheduled_amount_by_book: dict[str, float] = {name: 0 for name in finance_books}
                linked_rows_by_je: dict[str, list[Any]] = {name: [] for name in staged_by_je}
                active_schedules = frappe.get_all(
                    "Asset Depreciation Schedule",
                    filters={"asset": asset.name, "docstatus": 1, "status": "Active"},
                    fields=["name", "finance_book"],
                )
                for schedule_info in active_schedules:
                    schedule_doc = frappe.get_doc("Asset Depreciation Schedule", schedule_info.name)
                    for schedule_row in schedule_doc.depreciation_schedule:
                        if schedule_row.journal_entry in staged_by_je:
                            child = staged_by_je[cast(str, schedule_row.journal_entry)]
                            self.assertEqual(schedule_info.finance_book, child.finance_book)
                            self.assertEqual(getdate(schedule_row.schedule_date), getdate(child.posting_date))
                            linked_rows_by_je[cast(str, schedule_row.journal_entry)].append(schedule_row)
                            scheduled_amount_by_book[cast(str, child.finance_book)] += float(
                                schedule_row.depreciation_amount
                            )

                self.assertTrue(
                    all(len(rows) == 1 for rows in linked_rows_by_je.values()),
                    "Every staged native JE must be linked from exactly one active schedule row",
                )
                for je_name, schedule_rows in linked_rows_by_je.items():
                    schedule_row = schedule_rows[0]
                    journal_entries = frappe.get_doc("Journal Entry", je_name)
                    je_debits = sum(float(row.debit or 0) for row in journal_entries.accounts)
                    gl_entries = frappe.get_all(
                        "GL Entry",
                        filters={"voucher_type": "Journal Entry", "voucher_no": je_name, "is_cancelled": 0},
                        fields=["debit", "credit", "account", "finance_book", "posting_date"],
                    )
                    self.assertTrue(gl_entries, f"Submitted depreciation JE {je_name} must post GL")
                    self.assertEqual(len(gl_entries), 2, "Native depreciation JE must post its two GL legs")
                    self.assertTrue(
                        all(row.finance_book == staged_by_je[je_name].finance_book for row in gl_entries),
                        "Both native GL legs must carry the tracked Finance Book",
                    )
                    self.assertTrue(
                        all(
                            getdate(row.posting_date) == getdate(schedule_row.schedule_date)
                            for row in gl_entries
                        ),
                        "Native GL date must match the linked schedule date",
                    )
                    self.assertAlmostEqual(
                        sum(float(row.debit or 0) for row in gl_entries),
                        float(schedule_row.depreciation_amount),
                        places=2,
                        msg=f"Depreciation JE {je_name} GL debit must match its scheduled amount",
                    )
                    self.assertAlmostEqual(
                        je_debits,
                        float(schedule_row.depreciation_amount),
                        places=2,
                        msg=f"Depreciation JE {je_name} debit must match its linked schedule row",
                    )
                    self.assertAlmostEqual(
                        sum(float(row.credit or 0) for row in gl_entries),
                        float(schedule_row.depreciation_amount),
                        places=2,
                        msg=f"Depreciation JE {je_name} credit must match its linked schedule row",
                    )

                asset.reload()
                for row in asset.finance_books:
                    self.assertAlmostEqual(
                        initial_values[row.finance_book] - scheduled_amount_by_book[row.finance_book],
                        row.value_after_depreciation,
                        places=2,
                        msg=f"Native JE depreciation must update only {row.finance_book}",
                    )
                request.reload()
                self.assertEqual(request.disposal_status, "Ready to Dispose")

                frappe.set_user(reviewer)
                disposal.finalize_disposal(cast(str, request.name))
                request.reload()
                self.assertEqual(
                    request.disposal_status, "Closed" if purpose == "Sale" else "Disposal Accounting Pending"
                )
                if purpose == "Sale":
                    invoice_name = cast(str, request.sales_invoice)
                    invoice = frappe.get_doc("Sales Invoice", invoice_name)
                    self.assertEqual(invoice.docstatus, 1)
                    self.assertTrue(
                        frappe.db.exists(
                            "GL Entry",
                            {
                                "voucher_type": "Sales Invoice",
                                "voucher_no": invoice_name,
                                "is_cancelled": 0,
                            },
                        )
                    )
                    with self.assertRaises(frappe.ValidationError):
                        invoice.cancel()
                else:
                    disposal_children = [
                        row for row in request.generated_journal_entries if row.stage == "final_disposal"
                    ]
                    self.assertEqual(len(disposal_children), 1)
                    disposal_je = frappe.get_doc("Journal Entry", disposal_children[0].journal_entry)
                    self.assertEqual(disposal_je.docstatus, 0)
                    disposal_je = apply_workflow(disposal_je, "Send Journal Entry for Review")
                    frappe.set_user(je_checker)
                    disposal_je = apply_workflow(disposal_je, "Review Journal Entry")
                    frappe.set_user(approver)
                    disposal_je = apply_workflow(disposal_je, "Approve Journal Entry")
                    frappe.set_user(disposal_je.approval_checker_user)
                    disposal_je = apply_workflow(disposal_je, "Submit Journal Entry")
                    self.assertEqual(disposal_je.docstatus, 1)
                    self.assertTrue(
                        frappe.db.exists(
                            "GL Entry",
                            {
                                "voucher_type": "Journal Entry",
                                "voucher_no": disposal_je.name,
                                "is_cancelled": 0,
                            },
                        )
                    )
                    with self.assertRaises(frappe.ValidationError):
                        disposal_je.cancel()
                    request.reload()
                    self.assertEqual(request.disposal_status, "Closed")

    def test_disabled_selected_sale_tax_template_blocks_before_depreciation_stage(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset(depreciable=True)
        template_name = self._sales_tax_template()
        request, _maker, reviewer, _approver = self._approved_request(
            asset, "Sale", taxes_template=template_name
        )
        frappe.set_user("Administrator")
        frappe.db.set_value("Sales Taxes and Charges Template", template_name, "disabled", 1)
        before_journal_entries = frappe.db.count("Journal Entry")
        frappe.set_user(reviewer)
        with self.assertRaises(frappe.ValidationError):
            disposal.stage_depreciation(cast(str, request.name))
        request.reload()
        self.assertFalse(request.stage1_operation_id)
        self.assertEqual(frappe.db.count("Journal Entry"), before_journal_entries)

    def test_sale_candidate_tax_projection_survives_native_insert_validation(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset()
        make_test_records("Customer")
        item_tax_account = self._configure_native_tax_defaults(cast(str, asset.item_code))
        request = frappe._dict(
            asset=asset.name,
            item_code=asset.item_code,
            company=asset.company,
            sell_qty=asset.asset_quantity,
            customer="_Test Customer",
            posting_date=today(),
            disposal_date=today(),
            currency=frappe.get_cached_value("Company", asset.company, "default_currency"),
            taxes_template=None,
            rate=1000,
        )
        invoice = disposal._sale_candidate(cast(Any, request))
        approved_projection = disposal._normalized(disposal._projection(invoice))
        self.assertFalse(invoice.taxes_and_charges)
        self.assertEqual([row.account_head for row in invoice.taxes], [item_tax_account])
        with disposal._sale_tax_context(request, invoice):
            invoice.insert(ignore_permissions=True)
        self.assertEqual(disposal._normalized(disposal._projection(invoice)), approved_projection)

    def test_native_sale_insert_failure_rolls_back_final_stage_for_retry(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset()
        request, _maker, reviewer, _approver = self._approved_request(asset, "Sale")
        frappe.set_user(reviewer)
        disposal.stage_depreciation(cast(str, request.name))
        request.reload()
        self.assertEqual(request.disposal_status, "Ready to Dispose")
        frappe.db.savepoint("test_disposal_final_retry")
        with (
            patch.object(SalesInvoice, "insert", side_effect=RuntimeError("native insert failed")),
            self.assertRaisesRegex(RuntimeError, "native insert failed"),
        ):
            disposal.finalize_disposal(cast(str, request.name))
        frappe.db.rollback(save_point="test_disposal_final_retry")
        request.reload()
        self.assertEqual(request.disposal_status, "Ready to Dispose")
        self.assertFalse(request.sales_invoice)
        self.assertNotEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")

    def test_scrap_and_writeoff_close_after_independent_native_je_submit(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        for purpose in ("Scrap", "Write-off"):
            with self.subTest(purpose=purpose):
                frappe.set_user("Administrator")
                asset = self._native_asset()
                je_checker = self._actor("Accounts Manager", "je_checker")
                request, _maker, reviewer, approver = self._approved_request(asset, purpose)
                frappe.set_user(reviewer)
                disposal.stage_depreciation(cast(str, request.name))
                disposal.finalize_disposal(cast(str, request.name))
                request.reload()
                self.assertEqual(request.disposal_status, "Disposal Accounting Pending")
                children = [row for row in request.generated_journal_entries if row.stage == "final_disposal"]
                self.assertEqual(len(children), 1)
                je = frappe.get_doc("Journal Entry", children[0].journal_entry)
                self.assertEqual(je.docstatus, 0)
                je = apply_workflow(je, "Send Journal Entry for Review")
                frappe.set_user(je_checker)
                je = apply_workflow(je, "Review Journal Entry")
                frappe.set_user(approver)
                je = apply_workflow(je, "Approve Journal Entry")
                frappe.set_user(je.approval_checker_user)
                je = apply_workflow(je, "Submit Journal Entry")
                self.assertEqual(je.docstatus, 1)
                request.reload()
                self.assertEqual(request.disposal_status, "Closed")
                self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Scrapped")
                self.assertGreater(
                    frappe.db.count("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": je.name}),
                    0,
                )

    def test_staged_depreciation_requires_je_review_and_reset_preserves_posted_history(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset(depreciable=True)
        je_checker = self._actor("Accounts Manager", "stage_checker")
        request, maker, reviewer, approver = self._approved_request(asset, "Scrap")
        frappe.set_user(reviewer)
        disposal.stage_depreciation(cast(str, request.name))
        request.reload()
        staged = [
            row for row in request.generated_journal_entries if row.stage == "pre_disposal_depreciation"
        ]
        self.assertGreater(len(staged), 0)
        self.assertEqual(request.disposal_status, "Depreciation Pending")
        with self.assertRaises(frappe.ValidationError):
            disposal.finalize_disposal(cast(str, request.name))
        for child in staged:
            frappe.set_user(reviewer)
            je = apply_workflow(
                frappe.get_doc("Journal Entry", child.journal_entry), "Send Journal Entry for Review"
            )
            frappe.set_user(je_checker)
            je = apply_workflow(je, "Review Journal Entry")
            frappe.set_user(approver)
            je = apply_workflow(je, "Approve Journal Entry")
            frappe.set_user(je_checker)
            je = apply_workflow(je, "Submit Journal Entry")
            self.assertEqual(je.docstatus, 1)
        request.reload()
        self.assertEqual(request.disposal_status, "Ready to Dispose")
        active_schedule_before_restore = frappe.get_all(
            "Asset Depreciation Schedule",
            filters={"asset": asset.name, "docstatus": 1},
            pluck="name",
        )
        frappe.set_user("Administrator")
        with self.assertRaisesRegex(
            frappe.ValidationError, "A protected Asset Depreciation Schedule requires"
        ):
            native_restore_asset(cast(str, asset.name))
        self.assertEqual(
            frappe.get_all(
                "Asset Depreciation Schedule",
                filters={"asset": asset.name, "docstatus": 1},
                pluck="name",
            ),
            active_schedule_before_restore,
        )
        frappe.set_user(maker)
        disposal.apply_reasoned_action(
            cast(str, request.name), "Request Abandonment Reset", "_Test correction before disposal"
        )
        request.reload()
        frappe.set_user(reviewer)
        request = apply_workflow(request, "Review Abandonment Reset")
        frappe.set_user(approver)
        request = apply_workflow(request, "Approve Abandonment Reset")
        frappe.set_user(reviewer)
        disposal.reset_and_abandon(cast(str, request.name))
        request.reload()
        self.assertEqual(request.workflow_state, disposal.STATE_EXECUTION_ABANDONED)
        self.assertEqual(request.disposal_status, "Abandoned/Released")
        self.assertTrue(
            all(
                frappe.db.get_value("Journal Entry", child.journal_entry, "docstatus") == 1
                for child in staged
            )
        )

    def test_closed_depreciable_sale_cannot_be_restored_by_direct_python(self) -> None:
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        asset = self._native_asset(depreciable=True)
        je_checker = self._actor("Accounts Manager", "closed_checker")
        request, _maker, reviewer, approver = self._approved_request(asset, "Sale")
        frappe.set_user(reviewer)
        disposal.stage_depreciation(cast(str, request.name))
        request.reload()
        staged = [
            row for row in request.generated_journal_entries if row.stage == "pre_disposal_depreciation"
        ]
        self.assertGreater(len(staged), 0)
        for child in staged:
            frappe.set_user(reviewer)
            je = apply_workflow(
                frappe.get_doc("Journal Entry", child.journal_entry), "Send Journal Entry for Review"
            )
            frappe.set_user(je_checker)
            je = apply_workflow(je, "Review Journal Entry")
            frappe.set_user(approver)
            je = apply_workflow(je, "Approve Journal Entry")
            frappe.set_user(je_checker)
            je = apply_workflow(je, "Submit Journal Entry")
            self.assertEqual(je.docstatus, 1)
        frappe.set_user(reviewer)
        disposal.finalize_disposal(cast(str, request.name))
        request.reload()
        self.assertEqual(request.disposal_status, "Closed")
        invoice = request.sales_invoice
        frappe.set_user("Administrator")
        with (
            patch("erpnext.assets.doctype.asset.depreciation.reverse_depreciation_entry_made_on_disposal"),
            self.assertRaisesRegex(
                frappe.ValidationError, "A protected Asset Depreciation Schedule requires"
            ),
        ):
            native_restore_asset(cast(str, asset.name))
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")
        self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "docstatus"), 1)
