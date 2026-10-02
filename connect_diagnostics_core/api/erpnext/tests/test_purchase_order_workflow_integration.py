# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import patch

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import (
    PurchaseOrder,
    make_purchase_invoice,
    make_purchase_receipt,
)
from frappe.client import save as client_save
from frappe.client import set_value as client_set_value
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from connect_diagnostics_core.api.erpnext import purchase_order_workflow as po_workflow

COMPANY = "_Test Company"
ITEM = "_Test Item"
WAREHOUSE = "_Test Warehouse - _TC"
MAKER = "_test.po.maker@example.com"
REVIEWER = "_test.po.reviewer@example.com"
APPROVER = "_test.po.approver@example.com"
UNAUTHORIZED = "_test.po.unauthorized@example.com"
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"


def _ordered_qty() -> float:
    return float(
        frappe.db.get_value(
            "Bin",
            {"item_code": ITEM, "warehouse": WAREHOUSE},
            "ordered_qty",
        )
        or 0
    )


def _ensure_user(user: str, roles: tuple[str, ...]) -> None:
    if not frappe.db.exists("User", user):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": user,
                "send_welcome_email": 0,
                "user_type": "System User",
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)
    else:
        user_doc = frappe.get_doc("User", user)
        current_roles = {row.role for row in user_doc.roles}
        for role in roles:
            if role not in current_roles:
                user_doc.append("roles", {"role": role})
        user_doc.user_type = "System User"
        user_doc.save(ignore_permissions=True)

    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if employee_name:
        employee = frappe.get_doc("Employee", employee_name)
        employee.status = "Active"
        employee.approval_signature = SIGNATURE
        employee.save(ignore_permissions=True)
        frappe.clear_cache(user=user)
        return

    department = frappe.db.get_value("Department", {"company": COMPANY}, "name")
    employment_type = frappe.db.get_value("Employment Type", {}, "name")
    if not (department and employment_type):
        raise AssertionError("Employee test prerequisites are unavailable")
    frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": user,
            "company": COMPANY,
            "department": department,
            "gender": "Female",
            "date_of_birth": "1990-05-08",
            "date_of_joining": "2020-01-01",
            "status": "Active",
            "employment_type": employment_type,
            "user_id": user,
            "company_email": user,
            "approval_signature": SIGNATURE,
        }
    ).insert(ignore_permissions=True)
    frappe.clear_cache(user=user)


def _draft_order() -> PurchaseOrder:
    order = cast(PurchaseOrder, frappe.new_doc("Purchase Order"))
    order.company = COMPANY
    order.supplier = "_Test Supplier"
    order.schedule_date = add_days(nowdate(), 1)
    order.currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
    order.append(
        "items",
        {
            "item_code": ITEM,
            "warehouse": WAREHOUSE,
            "qty": 2,
            "rate": 100,
            "schedule_date": add_days(nowdate(), 1),
        },
    )
    order.set_missing_values()
    order.insert()
    evidence = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": f"_test_po_selection_{frappe.generate_hash(length=12)}.txt",
            "content": b"Direct supplier selected for test order",
            "is_private": 1,
            "attached_to_doctype": "Purchase Order",
            "attached_to_name": order.name,
            "attached_to_field": "supplier_selection_evidence",
        }
    ).insert(ignore_permissions=True)
    order.set("supplier_selection_reason", "Direct test supplier selection")
    order.set("supplier_selection_evidence", evidence.file_url)
    return order.save()


def _prepare_users() -> None:
    frappe.set_user("Administrator")
    _ensure_user(MAKER, ("Purchase User",))
    _ensure_user(REVIEWER, ("Purchase User", "Purchase Manager"))
    _ensure_user(APPROVER, ("Purchase User", "C-Level Approver"))
    _ensure_user(UNAUTHORIZED, ("Purchase User",))


class TestPurchaseOrderWorkflowIntegration(IntegrationTestCase):
    def _submitted_quote(self) -> Document:
        quotation = frappe.get_doc(
            {
                "doctype": "Supplier Quotation",
                "supplier": "_Test Supplier",
                "company": COMPANY,
                "currency": frappe.get_cached_value("Company", COMPANY, "default_currency"),
                "valid_till": add_days(nowdate(), 7),
                "items": [{"item_code": ITEM, "qty": 2, "rate": 100, "warehouse": WAREHOUSE}],
            }
        ).insert()
        quotation.submit()
        return quotation

    def _quoted_order(self, quotation: Document) -> PurchaseOrder:
        order = _draft_order()
        order.set("supplier_selection_reason", None)
        order.set("supplier_selection_evidence", None)
        order.get("items")[0].supplier_quotation = quotation.name
        order.get("items")[0].supplier_quotation_item = quotation.get("items")[0].name
        order.save()
        return order

    def _assert_rejected_review_has_no_submit_effects(
        self, order: PurchaseOrder, ordered_before: float
    ) -> None:
        self.assertEqual(frappe.db.get_value("Purchase Order", order.name, "docstatus"), 0)
        self.assertEqual(_ordered_qty(), ordered_before)
        self.assertFalse(frappe.db.exists("Purchase Receipt Item", {"purchase_order": order.name}))
        self.assertFalse(frappe.db.exists("Purchase Invoice Item", {"purchase_order": order.name}))

    def _cleanup_committed_quotation(self, name: str) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        frappe.set_user("Administrator")
        if frappe.db.exists("Supplier Quotation", name):
            frappe.delete_doc("Supplier Quotation", name, ignore_permissions=True)
            # Remove only the native fixture committed for the second-session proof.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self.assertFalse(frappe.db.exists("Supplier Quotation", name))

    def test_cancelled_quotation_cannot_pass_a_stale_submitted_snapshot(self) -> None:
        previous_user = frappe.session.user
        self.addCleanup(frappe.set_user, previous_user)
        frappe.set_user("Administrator")
        quotation = frappe.get_doc(
            {
                "doctype": "Supplier Quotation",
                "supplier": "_Test Supplier",
                "company": COMPANY,
                "currency": frappe.get_cached_value("Company", COMPANY, "default_currency"),
                "valid_till": add_days(nowdate(), 7),
                "items": [{"item_code": ITEM, "qty": 1, "rate": 100, "warehouse": WAREHOUSE}],
            }
        ).insert()
        quotation.submit()
        self.addCleanup(self._cleanup_committed_quotation, str(quotation.name))
        # Publish the submitted quotation for the second MariaDB session.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Supplier Quotation", quotation.name, "docstatus"), 1)
        with self.primary_connection():
            frappe.get_doc("Supplier Quotation", quotation.name).cancel()
            # Keep the second session's earlier repeatable-read snapshot intact.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        candidate = Document(
            {
                "doctype": "Purchase Order",
                "supplier": "_Test Supplier",
                "company": COMPANY,
                "currency": quotation.currency,
                "items": [
                    {
                        "item_code": ITEM,
                        "supplier_quotation": quotation.name,
                        "supplier_quotation_item": quotation.get("items")[0].name,
                    }
                ],
            }
        )
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Supplier Quotation", quotation.name, "docstatus"), 1)
            # A stale repeatable-read snapshot may report either the current
            # submitted-state denial or a NOWAIT retry after cancellation.
            # Both reject this selection until the caller retries with fresh state.
            with self.assertRaisesRegex(
                frappe.ValidationError,
                r"Supplier Quotation (?:must be submitted for the same supplier, company, and currency|is being updated\. Please retry\.)",
            ):
                po_workflow._validate_supplier_selection(candidate)
            frappe.db.rollback()

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_submitted_quotation_row_is_selection_evidence_without_direct_attachment(
        self, _mail: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        frappe.set_user("Administrator")
        quotation = frappe.get_doc(
            {
                "doctype": "Supplier Quotation",
                "supplier": "_Test Supplier",
                "company": COMPANY,
                "currency": frappe.get_cached_value("Company", COMPANY, "default_currency"),
                "valid_till": add_days(nowdate(), 7),
                "items": [
                    {
                        "item_code": ITEM,
                        "qty": 2,
                        "rate": 100,
                        "warehouse": WAREHOUSE,
                    }
                ],
            }
        ).insert()
        quotation.submit()
        frappe.set_user(MAKER)
        order = _draft_order()
        order.set("supplier_selection_reason", None)
        order.set("supplier_selection_evidence", None)
        order.get("items")[0].supplier_quotation = quotation.name
        order.get("items")[0].supplier_quotation_item = quotation.get("items")[0].name
        order.save()
        apply_workflow(order, "Submit Purchase Order for Review")
        frappe.set_user(REVIEWER)
        apply_workflow(order.reload(), "Review Purchase Order")
        frappe.set_user(APPROVER)
        apply_workflow(order.reload(), "Approve Purchase Order")
        frappe.set_user(REVIEWER)
        submitted = apply_workflow(order.reload(), "Post Purchase Order")
        self.assertEqual(submitted.docstatus, 1)
        self.assertEqual(submitted.items[0].supplier_quotation_item, quotation.get("items")[0].name)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_quotation_header_supplier_company_and_currency_mismatches_block_review(
        self, _mail: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        frappe.set_user("Administrator")
        changes = (
            ("supplier", frappe.db.get_value("Supplier", {"name": ["!=", "_Test Supplier"]}, "name")),
            ("company", frappe.db.get_value("Company", {"name": ["!=", COMPANY]}, "name")),
            (
                "currency",
                frappe.db.get_value(
                    "Currency",
                    {"name": ["!=", frappe.get_cached_value("Company", COMPANY, "default_currency")]},
                    "name",
                ),
            ),
        )
        self.assertTrue(all(value for _field, value in changes), "Mismatch fixtures are unavailable")
        for field, value in changes:
            frappe.set_user("Administrator")
            quotation = self._submitted_quote()
            frappe.set_user(MAKER)
            order = self._quoted_order(quotation)
            ordered_before = _ordered_qty()
            apply_workflow(order, "Submit Purchase Order for Review")
            frappe.set_user("Administrator")
            frappe.db.set_value("Supplier Quotation", quotation.name, field, value)
            frappe.set_user(REVIEWER)
            with self.assertRaisesRegex(
                frappe.ValidationError,
                "Supplier Quotation must be submitted for the same supplier, company, and currency",
            ):
                apply_workflow(order.reload(), "Review Purchase Order")
            self._assert_rejected_review_has_no_submit_effects(order, ordered_before)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_missing_foreign_and_remote_direct_po_evidence_block_review(self, _mail: object) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        cases = ("missing", "foreign", "remote")
        for case in cases:
            frappe.set_user(MAKER)
            order = _draft_order()
            file_name = frappe.db.get_value(
                "File",
                {
                    "file_url": order.get("supplier_selection_evidence"),
                    "attached_to_doctype": "Purchase Order",
                    "attached_to_name": order.name,
                    "attached_to_field": "supplier_selection_evidence",
                },
                "name",
            )
            self.assertTrue(file_name)
            ordered_before = _ordered_qty()
            apply_workflow(order, "Submit Purchase Order for Review")
            frappe.set_user("Administrator")
            if case == "foreign":
                file = frappe.get_doc("File", file_name)
                file.attached_to_name = "OTHER-PURCHASE-ORDER"
                file.save(ignore_permissions=True)
            else:
                frappe.db.set_value(
                    "Purchase Order",
                    order.name,
                    "supplier_selection_evidence",
                    None if case == "missing" else "https://supplier.example/evidence.pdf",
                )
            frappe.set_user(REVIEWER)
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(order.reload(), "Review Purchase Order")
            self._assert_rejected_review_has_no_submit_effects(order, ordered_before)
            self.assertEqual(frappe.db.get_value("Purchase Order", order.name, "docstatus"), 0)

    def test_attached_file_binding_is_rechecked_against_native_file_row(self) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        order = _draft_order()
        digest = po_workflow.get_commitment_digest(order)
        evidence = frappe.db.get_value(
            "File",
            {
                "file_url": order.get("supplier_selection_evidence"),
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": order.name,
                "attached_to_field": "supplier_selection_evidence",
            },
            "name",
        )
        self.assertTrue(evidence)
        file = frappe.get_doc("File", evidence)
        file.attached_to_name = "OTHER-PO"
        file.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            po_workflow.get_commitment_digest(order)
        file.attached_to_name = order.name
        file.save(ignore_permissions=True)
        self.assertEqual(po_workflow.get_commitment_digest(order), digest)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_same_url_file_byte_replacement_invalidates_review_before_posting(self, _mail: object) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        frappe.set_user(MAKER)
        order = _draft_order()
        file_name = frappe.db.get_value(
            "File",
            {
                "file_url": order.get("supplier_selection_evidence"),
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": order.name,
                "attached_to_field": "supplier_selection_evidence",
            },
            "name",
        )
        self.assertTrue(file_name)
        file = frappe.get_doc("File", file_name)
        path = Path(file.get_full_path())
        original = path.read_bytes()
        ordered_before = _ordered_qty()
        try:
            apply_workflow(order, "Submit Purchase Order for Review")
            frappe.set_user(REVIEWER)
            apply_workflow(order.reload(), "Review Purchase Order")
            reviewed = frappe.get_doc("Purchase Order", order.name)
            reviewed_digest = reviewed.approval_critical_digest
            path.write_bytes(b"Replacement evidence with the original File URL")
            self.assertNotEqual(po_workflow.get_commitment_digest(reviewed), reviewed_digest)
            frappe.set_user(APPROVER)
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(reviewed.reload(), "Approve Purchase Order")
            self.assertEqual(frappe.db.get_value("Purchase Order", order.name, "docstatus"), 0)
            self.assertEqual(_ordered_qty(), ordered_before)
        finally:
            path.write_bytes(original)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_direct_order_without_selection_reason_cannot_pass_review(self, _mail: object) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        frappe.set_user(MAKER)
        order = _draft_order()
        order.set("supplier_selection_reason", None)
        order.save()
        ordered_before = _ordered_qty()
        apply_workflow(order, "Submit Purchase Order for Review")
        frappe.set_user(REVIEWER)
        with self.assertRaisesRegex(frappe.ValidationError, "Direct Purchase Orders"):
            apply_workflow(order.reload(), "Review Purchase Order")
        self.assertEqual(frappe.db.get_value("Purchase Order", order.name, "docstatus"), 0)
        self.assertEqual(
            frappe.db.get_value("Purchase Order", order.name, "workflow_state"), po_workflow.REVIEW_STATE
        )
        self.assertEqual(_ordered_qty(), ordered_before)

    def test_persisted_order_json_roundtrip_keeps_v1_digest_and_detects_temporal_changes(self) -> None:
        frappe.set_user("Administrator")
        order = _draft_order()
        persisted = frappe.get_doc("Purchase Order", order.name)
        native_digest = po_workflow.get_commitment_digest(persisted)
        serialized = frappe.get_doc(json.loads(frappe.as_json(persisted.as_dict())))
        self.assertEqual(po_workflow.get_commitment_digest(serialized), native_digest)
        serialized.transaction_time = "12:34:56.123456"
        self.assertNotEqual(po_workflow.get_commitment_digest(serialized), native_digest)
        serialized = frappe.get_doc(json.loads(frappe.as_json(persisted.as_dict())))
        serialized.items[0].schedule_date = add_days(nowdate(), 2)
        self.assertNotEqual(po_workflow.get_commitment_digest(serialized), native_digest)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_v5_c_level_return_completes_original_pm_action_after_save(self, _mail: object) -> None:
        from connect_diagnostics_core.patches.v1_0.tests.test_upgrade_workflow_baseline_v5 import (
            isolated_v4_baseline,
        )

        with isolated_v4_baseline():
            self._assert_v5_c_level_return_completes_original_pm_action_after_save()

    def _assert_v5_c_level_return_completes_original_pm_action_after_save(self) -> None:
        from connect_diagnostics_core.api.erpnext import purchase_order_workflow as po_workflow
        from connect_diagnostics_core.patches.v1_0.tests import test_upgrade_workflow_baseline_v5 as rehearsal

        self.addCleanup(frappe.set_user, "Administrator")
        old_request = getattr(frappe.local, "request", None)
        frappe.local.request = frappe._dict(method="POST")
        self.addCleanup(setattr, frappe.local, "request", old_request)
        savepoint = "po_v5_return_completion"
        frappe.db.savepoint(savepoint)
        try:
            rehearsal.prepare_inflight(commit=False)
            name = frappe.db.get_value("Purchase Order", {"title": rehearsal.REHEARSAL_MARKER}, "name")
            order = frappe.get_doc("Purchase Order", name)
            old_action = frappe.db.get_value(
                "Workflow Action",
                {"reference_doctype": "Purchase Order", "reference_name": name, "status": "Open"},
                "name",
            )
            self.assertEqual(
                {row.role for row in frappe.get_doc("Workflow Action", old_action).permitted_roles},
                {"Purchase Manager"},
            )
            rehearsal.v5.execute()
            rehearsal.v5.verify()
            rehearsal.procure_to_pay.activate_standard_permissions()
            rehearsal.procure_to_pay._preflight_master_read_permissions()
            for doctype in ("Supplier", "Item", "Account"):
                frappe.clear_cache(doctype=doctype)
            frappe.set_user(rehearsal.RETURN_USER)
            rehearsal._assert_return_roles()
            order.reload()
            ordered_before = _ordered_qty()
            digest_before = frappe.db.get_value("Purchase Order", name, "approval_critical_digest")

            def assert_source_unchanged() -> None:
                self.assertEqual(
                    frappe.db.get_value("Purchase Order", name, "workflow_state"), "Purchase Order Approved"
                )
                self.assertEqual(
                    frappe.db.get_value("Purchase Order", name, "approval_critical_digest"), digest_before
                )
                self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "status"), "Open")

            order.workflow_state = "Purchase Order Draft"
            with (
                patch.object(
                    po_workflow,
                    "consume_approval_field_grant",
                    wraps=po_workflow.consume_approval_field_grant,
                ) as consumed,
                self.assertRaises(frappe.ValidationError),
            ):
                order.save()
            consumed.assert_called_once_with(order, po_workflow._RETURN_ROUTE, po_workflow._RETURN_ACTION)
            assert_source_unchanged()
            order.reload()
            forged = order.as_dict()
            forged["workflow_state"] = "Purchase Order Draft"
            with (
                patch.object(
                    po_workflow,
                    "consume_approval_field_grant",
                    wraps=po_workflow.consume_approval_field_grant,
                ) as consumed,
                self.assertRaisesRegex(frappe.ValidationError, "Approval field write is not authorized"),
            ):
                client_save(frappe.as_json(forged))
            consumed.assert_called_once()
            self.assertEqual(
                consumed.call_args.args[1:], (po_workflow._RETURN_ROUTE, po_workflow._RETURN_ACTION)
            )
            assert_source_unchanged()
            with (
                patch.object(
                    po_workflow,
                    "consume_approval_field_grant",
                    wraps=po_workflow.consume_approval_field_grant,
                ) as consumed,
                self.assertRaises(frappe.ValidationError) as error,
            ):
                client_set_value("Purchase Order", name, "workflow_state", "Purchase Order Draft")
            self.assertEqual(consumed.call_count, 1, str(error.exception))
            self.assertEqual(
                consumed.call_args.args[1:], (po_workflow._RETURN_ROUTE, po_workflow._RETURN_ACTION)
            )
            assert_source_unchanged()
            order.reload()

            frappe.set_user(rehearsal.REVIEWER)
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(order.reload(), "Return Purchase Order")
            assert_source_unchanged()
            self_approval_savepoint = "po_return_self_actor"
            frappe.db.savepoint(self_approval_savepoint)
            try:
                frappe.set_user("Administrator")
                maker_user = frappe.get_doc("User", rehearsal.MAKER)
                maker_user.append("roles", {"role": "C-Level Approver"})
                maker_user.save(ignore_permissions=True)
                frappe.clear_cache(user=rehearsal.MAKER)
                frappe.set_user(rehearsal.MAKER)
                self.assertIn("C-Level Approver", frappe.get_roles(rehearsal.MAKER))
                with self.assertRaises(frappe.ValidationError):
                    apply_workflow(order.reload(), "Return Purchase Order")
                assert_source_unchanged()
            finally:
                frappe.set_user("Administrator")
                frappe.db.rollback(save_point=self_approval_savepoint)
                frappe.clear_cache(user=rehearsal.MAKER)
            frappe.set_user(rehearsal.RETURN_USER)

            for case in ("missing", "duplicate", "conflicting_roles"):
                case_savepoint = f"po_return_{case}"
                frappe.db.savepoint(case_savepoint)
                try:
                    frappe.set_user("Administrator")
                    if case == "missing":
                        frappe.db.set_value("Workflow Action", old_action, "status", "Completed")
                    elif case == "duplicate":
                        duplicate = frappe.copy_doc(frappe.get_doc("Workflow Action", old_action))
                        duplicate.insert(ignore_permissions=True)
                    else:
                        changed = frappe.get_doc("Workflow Action", old_action)
                        changed.append("permitted_roles", {"role": "Purchase User"})
                        changed.save(ignore_permissions=True)
                    action_rows_before = frappe.get_all(
                        "Workflow Action",
                        filters={"reference_doctype": "Purchase Order", "reference_name": name},
                        fields=["name", "status", "completed_by", "completed_by_role"],
                        order_by="name",
                    )
                    frappe.set_user(rehearsal.RETURN_USER)
                    with self.assertRaises(frappe.ValidationError):
                        apply_workflow(order.reload(), "Return Purchase Order")
                    self.assertEqual(
                        frappe.get_all(
                            "Workflow Action",
                            filters={"reference_doctype": "Purchase Order", "reference_name": name},
                            fields=["name", "status", "completed_by", "completed_by_role"],
                            order_by="name",
                        ),
                        action_rows_before,
                    )
                    self.assertEqual(
                        frappe.db.get_value("Purchase Order", name, "workflow_state"),
                        "Purchase Order Approved",
                    )
                    self.assertEqual(
                        frappe.db.get_value("Purchase Order", name, "approval_critical_digest"), digest_before
                    )
                finally:
                    frappe.set_user("Administrator")
                    frappe.db.rollback(save_point=case_savepoint)
                    frappe.set_user(rehearsal.RETURN_USER)
                assert_source_unchanged()
                order.reload()

            with (
                patch.object(PurchaseOrder, "db_update", side_effect=frappe.ValidationError("before save")),
                self.assertRaises(frappe.ValidationError),
            ):
                apply_workflow(order, "Return Purchase Order")
            self.assertEqual(
                frappe.db.get_value("Purchase Order", name, "workflow_state"), "Purchase Order Approved"
            )
            self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "status"), "Open")
            order.reload()
            native_complete = po_workflow.update_completed_workflow_actions_using_role

            def complete_after_save(*args: object, **kwargs: object) -> None:
                self.assertEqual(
                    frappe.db.get_value("Purchase Order", name, "workflow_state"), "Purchase Order Draft"
                )
                self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "status"), "Open")
                self.assertFalse(
                    frappe.db.exists(
                        "Workflow Action",
                        {
                            "reference_doctype": "Purchase Order",
                            "reference_name": name,
                            "workflow_state": "Purchase Order Draft",
                            "status": "Open",
                        },
                    )
                )
                native_complete(*args, **kwargs)

            with patch.object(
                po_workflow, "update_completed_workflow_actions_using_role", side_effect=complete_after_save
            ) as completed:
                apply_workflow(order, "Return Purchase Order")
            completed.assert_called_once()
            order.reload()
            self.assertEqual((order.workflow_state, order.docstatus), ("Purchase Order Draft", 0))
            self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "status"), "Completed")
            self.assertEqual(
                frappe.db.get_value("Workflow Action", old_action, "completed_by"), rehearsal.RETURN_USER
            )
            self.assertEqual(
                frappe.db.get_value("Workflow Action", old_action, "completed_by_role"), "C-Level Approver"
            )
            self.assertEqual(
                {row.role for row in frappe.get_doc("Workflow Action", old_action).permitted_roles},
                {"Purchase Manager"},
            )
            self.assertEqual(_ordered_qty(), ordered_before)
            self.assertTrue(
                frappe.db.exists(
                    "Workflow Action",
                    {
                        "reference_doctype": "Purchase Order",
                        "reference_name": name,
                        "workflow_state": "Purchase Order Draft",
                        "status": "Open",
                    },
                )
            )
            rehearsal.v5.preflight()
            rehearsal.v5.verify()
            with self.assertRaises(frappe.ValidationError):
                rehearsal.recovery._preflight()
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback(save_point=savepoint)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_distinct_actor_workflow_submits_once_maps_downstream_and_cancels(
        self, _send_workflow_action_email: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()
        ordered_before = _ordered_qty()

        frappe.set_user(MAKER)
        order = _draft_order()
        with self.assertRaises(frappe.ValidationError):
            order.submit()
        order.reload()
        apply_workflow(order, "Submit Purchase Order for Review")

        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        order.reload()
        self.assertEqual(order.get("approval_reviewer_user"), REVIEWER)
        self.assertEqual(order.get("checked_signature"), SIGNATURE)
        order.items[0].rate = 125
        with self.assertRaises(frappe.ValidationError):
            order.save()

        frappe.set_user(APPROVER)
        order.reload()
        apply_workflow(order, "Approve Purchase Order")
        order.reload()
        self.assertEqual(order.get("approval_authorized_user"), APPROVER)
        self.assertEqual(order.get("authorized_signature"), SIGNATURE)

        frappe.set_user(REVIEWER)
        frappe.db.set_value("Purchase Order", order.name, "owner", APPROVER, update_modified=False)
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Post Purchase Order")
        frappe.db.set_value("Purchase Order", order.name, "owner", MAKER, update_modified=False)
        order.reload()
        apply_workflow(order, "Post Purchase Order")
        order.reload()
        self.assertEqual(order.docstatus, 1)
        self.assertEqual(order.get("workflow_state"), "Purchase Order Submitted")
        self.assertEqual(_ordered_qty(), ordered_before + 2)

        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Post Purchase Order")
        self.assertEqual(_ordered_qty(), ordered_before + 2)

        frappe.set_user("Administrator")
        receipt = make_purchase_receipt(order.name)
        invoice = make_purchase_invoice(order.name)
        self.assertEqual(receipt.items[0].purchase_order, order.name)
        self.assertEqual(invoice.items[0].purchase_order, order.name)
        self.assertEqual(receipt.items[0].qty, 2)
        self.assertEqual(invoice.items[0].qty, 2)

        frappe.set_user(REVIEWER)
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            order.cancel()
        order.reload()
        apply_workflow(order, "Cancel Purchase Order")
        order.reload()
        self.assertEqual(order.docstatus, 2)
        self.assertEqual(order.get("workflow_state"), "Purchase Order Cancelled")
        self.assertEqual(_ordered_qty(), ordered_before)

        frappe.set_user(MAKER)
        amended = cast(PurchaseOrder, frappe.copy_doc(order, ignore_no_copy=False))
        amended.docstatus = 0
        for child in amended.get_all_children():
            child.docstatus = 0
        amended.amended_from = order.name
        amended.insert()
        self.assertEqual(amended.docstatus, 0)
        self.assertEqual(amended.get("workflow_state"), "Purchase Order Draft")
        self.assertFalse(amended.get("approval_critical_digest"))
        self.assertFalse(amended.get("approval_authorized_user"))

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_return_and_reject_never_submit(self, _send_workflow_action_email: object) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        previous_request = getattr(frappe.local, "request", None)
        frappe.local.request = frappe._dict(method="POST")
        self.addCleanup(setattr, frappe.local, "request", previous_request)
        _prepare_users()

        frappe.set_user(MAKER)
        order = _draft_order()
        apply_workflow(order, "Submit Purchase Order for Review")

        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        frappe.set_user(APPROVER)
        order.reload()
        old_action = frappe.db.get_value(
            "Workflow Action",
            {"reference_doctype": "Purchase Order", "reference_name": order.name, "status": "Open"},
            "name",
        )
        file_name = frappe.db.get_value(
            "File",
            {
                "file_url": order.get("supplier_selection_evidence"),
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": order.name,
                "attached_to_field": "supplier_selection_evidence",
            },
            "name",
        )
        self.assertTrue(file_name)
        evidence_path = Path(frappe.get_doc("File", file_name).get_full_path())
        missing_path = evidence_path.with_name(
            f"{evidence_path.name}.{frappe.generate_hash(length=12)}.absent"
        )
        evidence_path.rename(missing_path)
        try:
            order.set("workflow_state", "Purchase Order Draft")
            with self.assertRaises(frappe.ValidationError):
                order.save()
            order.reload()
            apply_workflow(order, "Return Purchase Order")
        finally:
            missing_path.rename(evidence_path)
        order.reload()
        self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "status"), "Completed")
        self.assertEqual(frappe.db.get_value("Workflow Action", old_action, "completed_by"), APPROVER)
        self.assertEqual(
            frappe.db.get_value("Workflow Action", old_action, "completed_by_role"), "C-Level Approver"
        )
        self.assertEqual(order.get("workflow_state"), "Purchase Order Draft")
        self.assertFalse(order.get("approval_critical_digest"))
        self.assertFalse(order.get("checked_signature"))

        frappe.set_user(MAKER)
        apply_workflow(order, "Submit Purchase Order for Review")
        frappe.set_user(REVIEWER)
        order.reload()
        apply_workflow(order, "Review Purchase Order")
        frappe.set_user(APPROVER)
        order.reload()
        apply_workflow(order, "Reject Purchase Order")
        order.reload()
        self.assertEqual(order.get("workflow_state"), "Purchase Order Rejected")
        self.assertEqual(order.docstatus, 0)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_maker_and_unauthorized_actor_cannot_collapse_stages(
        self, _send_workflow_action_email: object
    ) -> None:
        self.addCleanup(frappe.set_user, "Administrator")
        _prepare_users()

        frappe.set_user(MAKER)
        order = _draft_order()
        apply_workflow(order, "Submit Purchase Order for Review")
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Purchase Order")

        frappe.set_user(UNAUTHORIZED)
        order.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(order, "Review Purchase Order")
