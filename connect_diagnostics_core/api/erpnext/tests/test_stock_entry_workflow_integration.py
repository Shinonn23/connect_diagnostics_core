# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.serial_batch_bundle import get_batch_nos
from frappe.client import save as client_save
from frappe.client import set_value as client_set_value
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

COMPANY = "_Test Company"
ITEM = "_Test Stock Transfer Approval Item"
BATCH_ITEM = "_Test Stock Transfer Approval Batch Item"
SOURCE = "Stores - _TC"
TARGET = "Finished Goods - _TC"
MAKER = "_test.stock.maker@example.com"
REVIEWER = "_test.stock.reviewer@example.com"
APPROVER = "_test.stock.approver@example.com"
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"


def _bin_qty(item_code: str, warehouse: str) -> float:
    return float(
        frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
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


def _ensure_item() -> None:
    if not frappe.db.exists("Item", ITEM):
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        if not item_group:
            raise AssertionError("Item Group test prerequisite is unavailable")
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": ITEM,
                "item_name": ITEM,
                "item_group": item_group,
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)


def _ensure_batch_item() -> None:
    if frappe.db.exists("Item", BATCH_ITEM):
        return
    item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
    if not item_group:
        raise AssertionError("Item Group test prerequisite is unavailable")
    frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": BATCH_ITEM,
            "item_name": BATCH_ITEM,
            "item_group": item_group,
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "batch_number_series": "_TEST-WF-BATCH-.#####",
        }
    ).insert(ignore_permissions=True)


def _draft_transfer(qty: float = 1, item_code: str = ITEM, batch_no: str | None = None) -> StockEntry:
    doc = cast(
        StockEntry,
        make_stock_entry(
            item_code=item_code,
            source=SOURCE,
            target=TARGET,
            qty=qty,
            batch_no=batch_no,
            do_not_save=True,
        ),
    )
    return doc.insert()


class TestStockEntryWorkflowIntegration(IntegrationTestCase):
    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_original_send_actor_survives_return_with_different_document_owner(self, _mail: object) -> None:
        from connect_diagnostics_core.api.erpnext import stock_entry_workflow

        frappe.set_user("Administrator")
        suffix = uuid4().hex
        owner = f"_test.stock.owner.{suffix}@example.com"
        maker = f"_test.stock.sender.{suffix}@example.com"
        checker = f"_test.stock.checker.{suffix}@example.com"
        approver = f"_test.stock.final.{suffix}@example.com"
        _ensure_item()
        _ensure_user(owner, ("Stock User",))
        _ensure_user(maker, ("Stock User", "Stock Manager", "C-Level Approver"))
        _ensure_user(checker, ("Stock User", "Stock Manager"))
        _ensure_user(approver, ("Stock User", "C-Level Approver"))
        make_stock_entry(item_code=ITEM, target=SOURCE, qty=5, basic_rate=100)
        source_before = _bin_qty(ITEM, SOURCE)
        target_before = _bin_qty(ITEM, TARGET)
        frappe.set_user(owner)
        transfer = _draft_transfer()
        self.assertEqual(transfer.owner, owner)
        frappe.set_user(maker)
        apply_workflow(transfer.reload(), "Send Stock Transfer for Review")
        self.assertEqual(transfer.reload().get("approval_maker_user"), maker)
        frappe.set_user(checker)
        apply_workflow(transfer, "Return Stock Transfer")

        frappe.set_user(owner)
        with (
            patch.object(
                stock_entry_workflow,
                "authorize_workflow_field_write",
                wraps=stock_entry_workflow.authorize_workflow_field_write,
            ) as grant,
            patch.object(
                stock_entry_workflow,
                "capture_maker_snapshot",
                wraps=stock_entry_workflow.capture_maker_snapshot,
            ) as capture,
        ):
            self._assert_denied(
                lambda: apply_workflow(transfer.reload(), "Resubmit Stock Transfer for Review")
            )
            capture.assert_called_once()
            grant.assert_not_called()
        self.assertEqual(transfer.reload().get("workflow_state"), "Stock Transfer Returned")
        self.assertEqual(transfer.get("approval_maker_user"), maker)
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), 0)

        frappe.set_user(maker)
        apply_workflow(transfer, "Resubmit Stock Transfer for Review")
        with patch.object(
            stock_entry_workflow,
            "authorize_approval_field_write",
            wraps=stock_entry_workflow.authorize_approval_field_write,
        ) as signed:
            self._assert_denied(lambda: apply_workflow(transfer.reload(), "Review Stock Transfer"))
            signed.assert_called_once()
        frappe.set_user(checker)
        apply_workflow(transfer.reload(), "Review Stock Transfer")
        frappe.set_user(maker)
        with patch.object(
            stock_entry_workflow,
            "authorize_approval_field_write",
            wraps=stock_entry_workflow.authorize_approval_field_write,
        ) as signed:
            self._assert_denied(lambda: apply_workflow(transfer.reload(), "Approve Stock Transfer"))
            signed.assert_called_once()
        frappe.set_user(approver)
        apply_workflow(transfer.reload(), "Approve Stock Transfer")
        frappe.set_user(checker)
        apply_workflow(transfer.reload(), "Submit Stock Transfer")
        self.assertEqual(transfer.reload().docstatus, 1)
        self.assertEqual(transfer.get("approval_maker_user"), maker)
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before - 1)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before + 1)
        apply_workflow(transfer, "Cancel Stock Transfer")
        self.assertEqual(transfer.reload().docstatus, 2)
        self.assertEqual(transfer.get("approval_maker_user"), maker)
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before)

    def _assert_denied(self, action: Callable[[], object]) -> None:
        savepoint = f"stock_state_denial_{uuid4().hex}"
        frappe.db.savepoint(savepoint)
        try:
            with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
                action()
        finally:
            frappe.db.rollback(save_point=savepoint)
            frappe.clear_cache(doctype="Stock Entry")

    def setUp(self) -> None:
        super().setUp()
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

    def test_native_new_doc_does_not_autofill_approval_evidence_from_employee_scope(self) -> None:
        from connect_diagnostics_core.api.erpnext import stock_entry_workflow

        old_user = frappe.session.user
        user = f"_test.stock.audit.{uuid4().hex}@example.com"
        try:
            frappe.set_user("Administrator")
            _ensure_user(user, ("Stock User",))
            employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
            self.assertIsNotNone(employee)
            permissions = frappe.get_all(
                "User Permission", filters={"user": user, "allow": "Employee"}, pluck="for_value"
            )
            self.assertEqual(permissions, [employee])
            frappe.set_user(user)
            draft = cast(StockEntry, frappe.new_doc("Stock Entry"))
            self.assertFalse(draft.get("checked_by"))
            self.assertFalse(draft.get("authorized_by"))
            self.assertFalse(draft.get("submit_by"))
            draft.purpose = "Material Transfer"
            stock_entry_workflow.validate_workflow(draft)
            draft.set("checked_by", employee)
            with self.assertRaises(frappe.ValidationError):
                stock_entry_workflow.validate_workflow(draft)
        finally:
            frappe.set_user(old_user)
            frappe.clear_cache(user=user)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_distinct_actor_workflow_posts_once_and_native_cancel_reverses(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))
        make_stock_entry(item_code=ITEM, target=SOURCE, qty=5, basic_rate=100)
        source_before = _bin_qty(ITEM, SOURCE)
        target_before = _bin_qty(ITEM, TARGET)

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        with self.assertRaises(frappe.ValidationError):
            transfer.submit()
        transfer.reload()
        apply_workflow(transfer, "Send Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("approval_reviewer_user"), REVIEWER)
        self.assertEqual(transfer.get("checked_signature"), SIGNATURE)
        transfer.items[0].qty = 2
        with self.assertRaises(frappe.ValidationError):
            transfer.save()

        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("approval_authorized_user"), APPROVER)
        self.assertEqual(transfer.get("authorized_signature"), SIGNATURE)

        frappe.set_user(REVIEWER)
        transfer.reload()

        def forge_submitted(*, api: bool) -> object:
            candidate = frappe.get_doc("Stock Entry", transfer.name)
            candidate.set("workflow_state", "Stock Transfer Submitted")
            if api:
                return client_save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        self._assert_denied(lambda: forge_submitted(api=False))
        self._assert_denied(lambda: forge_submitted(api=True))
        self._assert_denied(
            lambda: client_set_value(
                "Stock Entry", transfer.name, "workflow_state", "Stock Transfer Submitted"
            )
        )
        self.assertEqual(
            frappe.db.get_value("Stock Entry", transfer.name, "workflow_state"), "Stock Transfer Approved"
        )
        self.assertEqual(frappe.db.get_value("Stock Entry", transfer.name, "docstatus"), 0)
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before)
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), 0)
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 1)
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Submitted")
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before - 1)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before + 1)
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name, "is_cancelled": 0}),
            2,
        )

        def forge_cancelled(*, api: bool) -> object:
            candidate = frappe.get_doc("Stock Entry", transfer.name)
            candidate.set("workflow_state", "Stock Transfer Cancelled")
            if api:
                return client_save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        self._assert_denied(lambda: forge_cancelled(api=False))
        self._assert_denied(lambda: forge_cancelled(api=True))
        self._assert_denied(
            lambda: client_set_value(
                "Stock Entry", transfer.name, "workflow_state", "Stock Transfer Cancelled"
            )
        )
        self.assertEqual(
            frappe.db.get_value("Stock Entry", transfer.name, "workflow_state"), "Stock Transfer Submitted"
        )
        self.assertEqual(frappe.db.get_value("Stock Entry", transfer.name, "docstatus"), 1)
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before - 1)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before + 1)
        self.assertEqual(
            frappe.db.count(
                "Stock Ledger Entry",
                {
                    "voucher_no": transfer.name,
                    "is_cancelled": 0,
                },
            ),
            2,
        )

        # Exercise a historical generic submitted state in an isolated fixture transaction.
        historical = f"stock_history_{uuid4().hex}"
        frappe.db.savepoint(historical)
        try:
            frappe.db.set_value(
                "Stock Entry", transfer.name, "workflow_state", "Stock Entry Submitted", update_modified=False
            )
            legacy = frappe.get_doc("Stock Entry", transfer.name)
            legacy.save()
            self.assertEqual(legacy.get("workflow_state"), "Stock Entry Submitted")
        finally:
            frappe.db.rollback(save_point=historical)
            frappe.clear_cache(doctype="Stock Entry")
        transfer.reload()

        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Submit Stock Transfer")
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name, "is_cancelled": 0}),
            2,
        )

        apply_workflow(transfer, "Cancel Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.docstatus, 2)
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Cancelled")
        self.assertEqual(_bin_qty(ITEM, SOURCE), source_before)
        self.assertEqual(_bin_qty(ITEM, TARGET), target_before)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_return_resubmit_and_reject_never_post_stock(self, _send_workflow_action_email: object) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        apply_workflow(transfer, "Send Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Return Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Returned")
        self.assertFalse(transfer.get("approval_critical_digest"))
        self.assertFalse(transfer.get("checked_signature"))

        frappe.set_user(MAKER)
        transfer.reload()
        apply_workflow(transfer, "Resubmit Stock Transfer for Review")

        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")

        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Reject Stock Transfer")
        transfer.reload()
        self.assertEqual(transfer.get("workflow_state"), "Stock Transfer Rejected")
        self.assertEqual(transfer.docstatus, 0)
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), 0)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_maker_and_unauthorized_user_cannot_review(self, _send_workflow_action_email: object) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()
        _ensure_user(MAKER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))

        frappe.set_user(MAKER)
        transfer = _draft_transfer()
        apply_workflow(transfer, "Send Stock Transfer for Review")
        transfer.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Review Stock Transfer")

        frappe.set_user(APPROVER)
        transfer.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(transfer, "Review Stock Transfer")
        self.assertFalse(transfer.get("approval_reviewer_user"))
        self.assertFalse(transfer.get("checked_signature"))

    def test_non_material_transfer_keeps_native_submit_path(self) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_item()

        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=ITEM, target=SOURCE, qty=1, basic_rate=100),
        )
        receipt.reload()
        self.assertEqual(receipt.purpose, "Material Receipt")
        self.assertEqual(receipt.get("workflow_state"), "Stock Entry Submitted")
        self.assertEqual(receipt.docstatus, 1)
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": receipt.name, "is_cancelled": 0}),
            1,
        )

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_batch_bundle_moves_and_reverses_through_native_posting(
        self, _send_workflow_action_email: object
    ) -> None:
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_batch_item()
        serial_batch_enabled = frappe.db.get_single_value(
            "Stock Settings", "enable_serial_and_batch_no_for_item"
        )
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            serial_batch_enabled,
        )
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))
        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=BATCH_ITEM, target=SOURCE, qty=1, basic_rate=100),
        )
        batch_no = next(iter(get_batch_nos(receipt.items[0].serial_and_batch_bundle)))

        frappe.set_user(MAKER)
        transfer = _draft_transfer(item_code=BATCH_ITEM, batch_no=batch_no)
        apply_workflow(transfer, "Send Stock Transfer for Review")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Submit Stock Transfer")
        transfer.reload()

        self.assertTrue(transfer.items[0].serial_and_batch_bundle)
        self.assertEqual(set(get_batch_nos(transfer.items[0].serial_and_batch_bundle)), {batch_no})
        self.assertEqual(get_batch_qty(batch_no, SOURCE, BATCH_ITEM), 0)
        self.assertEqual(get_batch_qty(batch_no, TARGET, BATCH_ITEM), 1)

        apply_workflow(transfer, "Cancel Stock Transfer")
        self.assertEqual(get_batch_qty(batch_no, SOURCE, BATCH_ITEM), 1)
        self.assertEqual(get_batch_qty(batch_no, TARGET, BATCH_ITEM), 0)


class TestStockEntryPostSubmitRollbackIntegration(IntegrationTestCase):
    """Prove the native posting transaction rolls back on post-submit identity failure."""

    @classmethod
    def setUpClass(cls) -> None:
        frappe.reload_doc("connect_diagnostics_stock", "doctype", "storage_location", force=True)
        super().setUpClass()
        from connect_diagnostics_core.setup.storage_location import ensure_configuration

        ensure_configuration()

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_posted_tracked_identity_mismatch_rolls_back_native_submit(
        self, _send_workflow_action_email: object
    ) -> None:
        from connect_diagnostics_core.api.erpnext import stock_entry_workflow

        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        _ensure_batch_item()
        old_setting = frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item")
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        self.addCleanup(
            frappe.db.set_single_value,
            "Stock Settings",
            "enable_serial_and_batch_no_for_item",
            old_setting,
        )
        _ensure_user(MAKER, ("Stock User",))
        _ensure_user(REVIEWER, ("Stock User", "Stock Manager"))
        _ensure_user(APPROVER, ("Stock User", "C-Level Approver"))

        suffix = uuid4().hex
        source_location = f"_Test Rollback Source {suffix}"
        target_location = f"_Test Rollback Target {suffix}"
        for location in (source_location, target_location):
            frappe.get_doc(
                {"doctype": "Storage Location", "location_code": location, "warehouse": SOURCE}
            ).insert(ignore_permissions=True)

        receipt = cast(
            StockEntry,
            make_stock_entry(item_code=BATCH_ITEM, target=SOURCE, qty=1, basic_rate=100, do_not_save=True),
        )
        receipt.items[0].set("to_storage_location", source_location)
        receipt.insert().submit()
        batch_no = next(iter(get_batch_nos(receipt.items[0].serial_and_batch_bundle)))

        frappe.set_user(MAKER)
        transfer = cast(
            StockEntry,
            make_stock_entry(
                item_code=BATCH_ITEM,
                source=SOURCE,
                target=SOURCE,
                qty=1,
                batch_no=batch_no,
                do_not_save=True,
            ),
        )
        transfer.items[0].set("storage_location", source_location)
        transfer.items[0].set("to_storage_location", target_location)
        transfer.insert()
        apply_workflow(transfer, "Send Stock Transfer for Review")
        frappe.set_user(REVIEWER)
        transfer.reload()
        apply_workflow(transfer, "Review Stock Transfer")
        frappe.set_user(APPROVER)
        transfer.reload()
        apply_workflow(transfer, "Approve Stock Transfer")

        before_sle = frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name})
        before_gl = frappe.db.count("GL Entry", {"voucher_no": transfer.name})
        before_bin_source = _bin_qty(BATCH_ITEM, SOURCE)

        def location_qty(location: str) -> float:
            return float(
                frappe.db.sql(
                    """SELECT COALESCE(SUM(actual_qty), 0) FROM `tabStock Ledger Entry`
                       WHERE item_code = %s AND warehouse = %s AND storage_location = %s
                         AND is_cancelled = 0""",
                    (BATCH_ITEM, SOURCE, location),
                )[0][0]
            )

        before_source_location_qty = location_qty(source_location)
        before_target_location_qty = location_qty(target_location)
        savepoint = f"stock_transfer_post_rollback_{suffix}"
        frappe.db.savepoint(savepoint)
        original_verifier = stock_entry_workflow.validate_after_submit
        observed: dict[str, int] = {}
        source_bundle_entry_name = ""

        def corrupt_posted_bundle(doc: frappe.model.document.Document, method: str | None = None) -> None:
            nonlocal source_bundle_entry_name
            ledger = frappe.get_all(
                "Stock Ledger Entry",
                filters={"voucher_no": doc.name, "actual_qty": ["<", 0], "is_cancelled": 0},
                fields=["serial_and_batch_bundle"],
                limit=1,
            )
            self.assertTrue(ledger)
            bundle_name = str(ledger[0].serial_and_batch_bundle)
            entry = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": bundle_name, "parenttype": "Serial and Batch Bundle"},
                fields=["name", "batch_no"],
                limit=1,
            )
            self.assertEqual(entry[0].batch_no, batch_no)
            source_bundle_entry_name = str(entry[0].name)
            observed["sle"] = frappe.db.count("Stock Ledger Entry", {"voucher_no": doc.name})
            observed["gl"] = frappe.db.count("GL Entry", {"voucher_no": doc.name})
            frappe.db.set_value("Serial and Batch Entry", entry[0].name, "batch_no", f"unapproved-{suffix}")
            original_verifier(doc, method)

        try:
            frappe.set_user(REVIEWER)
            with patch.object(
                stock_entry_workflow, "validate_after_submit", side_effect=corrupt_posted_bundle
            ):
                with self.assertRaisesRegex(frappe.ValidationError, "identities differ"):
                    apply_workflow(transfer, "Submit Stock Transfer")
        finally:
            # A direct integration invocation runs inside the test transaction rather than
            # Frappe's request wrapper, so roll back the failing request's savepoint explicitly.
            frappe.db.rollback(save_point=savepoint)

        self.assertEqual(observed["sle"], before_sle + 2)
        self.assertGreaterEqual(observed["gl"], before_gl)
        self.assertEqual(frappe.db.get_value("Stock Entry", transfer.name, "docstatus"), 0)
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": transfer.name}), before_sle)
        self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": transfer.name}), before_gl)
        self.assertEqual(_bin_qty(BATCH_ITEM, SOURCE), before_bin_source)
        self.assertEqual(location_qty(source_location), before_source_location_qty)
        self.assertEqual(location_qty(target_location), before_target_location_qty)
        self.assertEqual(
            frappe.db.get_value("Serial and Batch Entry", source_bundle_entry_name, "batch_no"), batch_no
        )
