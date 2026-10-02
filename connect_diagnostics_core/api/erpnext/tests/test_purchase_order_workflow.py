# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import purchase_order_workflow as workflow
from connect_diagnostics_core.api.frappe import approval_controls


class TestPurchaseOrderWorkflow(UnitTestCase):
    def _doc(self, **values: object) -> Document:
        return frappe.get_doc({"doctype": "Purchase Order", "name": "PO-TEST", **values})

    def test_direct_and_partial_quotation_require_distinct_evidence_rules(self) -> None:
        direct = self._doc(items=[{"item_code": "ITEM-1"}])
        with self.assertRaisesRegex(frappe.ValidationError, "Direct Purchase Orders"):
            workflow._validate_supplier_selection(direct)
        direct.set("supplier_selection_reason", "Urgent local supply")
        direct.set("supplier_selection_evidence", "/private/files/selection.pdf")
        workflow._validate_supplier_selection(direct)
        direct.get("items")[0].supplier_quotation = "SQ-1"
        with self.assertRaisesRegex(frappe.ValidationError, "both header and item"):
            workflow._validate_supplier_selection(direct)

    def test_quote_pair_must_be_submitted_and_match_exact_child_identity(self) -> None:
        doc = self._doc(
            supplier="SUP-1",
            company="COMP-1",
            currency="THB",
            items=[{"item_code": "ITEM-1", "supplier_quotation": "SQ-1", "supplier_quotation_item": "SQI-1"}],
        )
        header = frappe._dict(name="SQ-1", docstatus=1, supplier="SUP-1", company="COMP-1", currency="THB")
        child = frappe._dict(name="SQI-1", parent="SQ-1", item_code="ITEM-1")
        source = Document(
            {
                "doctype": "Supplier Quotation",
                "name": "SQ-1",
                "items": [{"name": "SQI-1", "parent": "SQ-1", "item_code": "ITEM-1"}],
            }
        )
        with (
            patch.object(workflow.frappe.db, "get_value", return_value=header) as locked_header,
            patch.object(workflow.frappe.db, "get_values", return_value=[child]) as locked_children,
            patch.object(workflow.frappe, "get_doc", return_value=source),
        ):
            workflow._validate_supplier_selection(doc)
            self.assertTrue(locked_header.call_args.kwargs["for_update"])
            self.assertFalse(locked_header.call_args.kwargs["wait"])
            self.assertTrue(locked_children.call_args.kwargs["for_update"])
            self.assertFalse(locked_children.call_args.kwargs["wait"])
            child.item_code = "OTHER"
            with self.assertRaisesRegex(frappe.ValidationError, "changed while"):
                workflow._validate_supplier_selection(doc)
            child.item_code = "ITEM-1"
            child.parent = "SQ-OTHER"
            source.get("items")[0].parent = "SQ-OTHER"
            with self.assertRaisesRegex(frappe.ValidationError, "selected quotation"):
                workflow._validate_supplier_selection(doc)
            child.parent = "SQ-1"
            source.get("items")[0].parent = "SQ-1"
            header.docstatus = 2
            with self.assertRaisesRegex(frappe.ValidationError, "submitted"):
                workflow._validate_supplier_selection(doc)

    def test_mixed_order_needs_direct_evidence_even_with_a_valid_quote(self) -> None:
        doc = self._doc(
            supplier="SUP-1",
            company="COMP-1",
            currency="THB",
            items=[
                {"item_code": "ITEM-1", "supplier_quotation": "SQ-1", "supplier_quotation_item": "SQI-1"},
                {"item_code": "ITEM-2"},
            ],
        )
        header = frappe._dict(name="SQ-1", docstatus=1, supplier="SUP-1", company="COMP-1", currency="THB")
        child = frappe._dict(name="SQI-1", parent="SQ-1", item_code="ITEM-1")
        source = Document(
            {
                "doctype": "Supplier Quotation",
                "name": "SQ-1",
                "items": [{"name": "SQI-1", "parent": "SQ-1", "item_code": "ITEM-1"}],
            }
        )
        with (
            patch.object(workflow.frappe.db, "get_value", return_value=header),
            patch.object(workflow.frappe.db, "get_values", return_value=[child]),
            patch.object(workflow.frappe, "get_doc", return_value=source),
            self.assertRaisesRegex(frappe.ValidationError, "Direct Purchase Orders"),
        ):
            workflow._validate_supplier_selection(doc)

    def test_legacy_blank_selection_projection_remains_exact_v1_shape(self) -> None:
        doc = self._doc(items=[], **dict.fromkeys(workflow.COMMITMENT_FIELDS["Purchase Order"]))
        baseline = workflow.build_commitment_payload(doc)
        self.assertNotIn("supplier_selection_reason", baseline)
        self.assertNotIn("supplier_selection_evidence", baseline)
        self.assertNotIn("supplier_selection_evidence_sha256", baseline)
        doc.set("supplier_selection_reason", "  ")
        self.assertEqual(workflow.build_commitment_payload(doc), baseline)
        # Frozen from the predecessor's build_commitment_payload + critical_digest
        # for a PO containing no table rows or populated commitment fields.
        self.assertEqual(
            workflow.get_commitment_digest(doc),
            "b17af54fc74a8de41bc1150253e858c80aea78359ffff4a5ad87aa9649049dd0",
        )

    def test_reviewed_return_compares_document_projection_without_reading_missing_file(self) -> None:
        previous = self._doc(
            workflow_state=workflow.APPROVAL_STATE,
            docstatus=0,
            supplier_selection_reason="Direct source",
            supplier_selection_evidence="/private/files/selection.pdf",
            items=[{"name": "ROW-1", "item_code": "ITEM-1", "qty": 1}],
        )
        current = self._doc(
            workflow_state="Purchase Order Draft",
            docstatus=0,
            supplier_selection_reason="Direct source",
            supplier_selection_evidence="/private/files/selection.pdf",
            items=[{"name": "ROW-1", "item_code": "ITEM-1", "qty": 1}],
        )
        with (
            patch.object(Document, "get_doc_before_save", return_value=previous),
            patch.object(
                workflow, "_selection_evidence_digest", side_effect=frappe.ValidationError("gone")
            ) as file_bytes,
        ):
            workflow._reject_critical_changes_after_review(current)
            file_bytes.assert_not_called()
            for field, value in (
                ("supplier_selection_reason", "Other source"),
                ("supplier_selection_evidence", "/private/files/other.pdf"),
            ):
                current.set(field, value)
                with self.assertRaisesRegex(frappe.ValidationError, "Commitment-critical"):
                    workflow._reject_critical_changes_after_review(current)
                current.set(field, previous.get(field))
            current.get("items")[0].set("qty", 2)
            with self.assertRaisesRegex(frappe.ValidationError, "Commitment-critical"):
                workflow._reject_critical_changes_after_review(current)
            current.get("items")[0].set("qty", 1)
            current.set("workflow_state", workflow.APPROVED_STATE)
            with self.assertRaisesRegex(frappe.ValidationError, "gone"):
                workflow._reject_critical_changes_after_review(current)

    def test_attached_private_file_bytes_and_binding_are_sealed(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "selection.pdf"
            path.write_bytes(b"first supplier rationale")
            values = {
                "file_url": "/private/files/selection.pdf",
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": "PO-TEST",
                "attached_to_field": "supplier_selection_evidence",
                "is_private": 1,
                "is_remote_file": 0,
                "is_folder": 0,
            }
            file = Mock()
            file.get.side_effect = values.get
            file.get_full_path.return_value = str(path)
            doc = self._doc(
                supplier_selection_reason="Direct source", supplier_selection_evidence=values["file_url"]
            )
            with (
                patch.object(workflow.frappe.db, "get_values", return_value=["FILE-1"]),
                patch.object(workflow.frappe, "get_doc", return_value=file),
                patch.object(workflow, "get_files_path", return_value=temporary),
                patch.object(workflow, "_normalize_native_temporals", side_effect=lambda payload: payload),
            ):
                first = workflow.get_commitment_digest(doc)
                path.write_bytes(b"replacement supplier rationale")
                self.assertNotEqual(first, workflow.get_commitment_digest(doc))
                values["attached_to_name"] = "OTHER-PO"
                with self.assertRaises(frappe.ValidationError):
                    workflow.get_commitment_digest(doc)

    def test_digest_is_stable_and_changes_for_commitment_value(self) -> None:
        doc = self._doc(
            owner="maker@example.com",
            supplier="SUP-1",
            company="Company",
            currency="THB",
            items=[],
        )
        first = workflow.get_commitment_digest(doc)
        self.assertEqual(first, workflow.get_commitment_digest(doc))
        doc.set("currency", "USD")
        self.assertNotEqual(first, workflow.get_commitment_digest(doc))
        doc.set("currency", "THB")
        doc.set("owner", "approver@example.com")
        self.assertNotEqual(first, workflow.get_commitment_digest(doc))

    @patch.object(workflow.frappe, "throw")
    def test_maker_change_after_review_is_rejected(self, throw: Mock) -> None:
        previous = self._doc(
            workflow_state=workflow.APPROVAL_STATE,
            owner="maker@example.com",
            supplier="SUP-1",
        )
        current = self._doc(
            workflow_state=workflow.APPROVAL_STATE,
            owner="approver@example.com",
            supplier="SUP-1",
        )
        with patch.object(Document, "get_doc_before_save", return_value=previous):
            workflow.validate_workflow(current)
        throw.assert_called_once()

    def test_child_row_order_is_commitment_critical(self) -> None:
        first = self._doc(items=[{"item_code": "A", "qty": 1}, {"item_code": "B", "qty": 1}])
        second = self._doc(items=[{"item_code": "B", "qty": 1}, {"item_code": "A", "qty": 1}])
        self.assertNotEqual(workflow.get_commitment_digest(first), workflow.get_commitment_digest(second))

    def test_native_integer_float_normalization_preserves_meaningful_delta(self) -> None:
        base = {"doctype": "Purchase Order", "items": [{"name": "ROW-1", "item_code": "A", "qty": 1}]}
        native = {"doctype": "Purchase Order", "items": [{"name": "ROW-1", "item_code": "A", "qty": 1.0}]}
        changed = {"doctype": "Purchase Order", "items": [{"name": "ROW-1", "item_code": "A", "qty": 1.25}]}
        self.assertEqual(workflow.get_commitment_digest(base), workflow.get_commitment_digest(native))
        self.assertNotEqual(workflow.get_commitment_digest(base), workflow.get_commitment_digest(changed))

    def test_native_temporal_v1_golden_and_json_equivalence(self) -> None:
        native = self._doc(
            transaction_date=date(2026, 10, 2),
            transaction_time=timedelta(hours=25, minutes=6, seconds=7, microseconds=120000),
            schedule_date=date(2026, 10, 4),
            items=[{"name": "ROW-1", "schedule_date": date(2026, 10, 4)}],
            payment_schedule=[{"name": "PAY-1", "due_date": date(2026, 10, 5)}],
        )
        digest = workflow.get_commitment_digest(native)
        self.assertEqual(digest, "77663aeedd9a12b42abaddc838cafb9140d1756d9969fa39b624bda5e7f0d824")
        serialized = self._doc(
            transaction_date="2026-10-02",
            transaction_time="25:06:07.120000",
            schedule_date="2026-10-04",
            items=[{"name": "ROW-1", "schedule_date": "2026-10-04"}],
            payment_schedule=[{"name": "PAY-1", "due_date": "2026-10-05"}],
        )
        self.assertEqual(workflow.get_commitment_digest(serialized), digest)
        serialized.get("items")[0].schedule_date = "2026-10-06"
        self.assertNotEqual(workflow.get_commitment_digest(serialized), digest)
        serialized.get("items")[0].schedule_date = "2026-10-04"
        serialized.set("transaction_time", "25:06:07.120001")
        self.assertNotEqual(workflow.get_commitment_digest(serialized), digest)

    def test_temporal_parser_rejects_invalid_sentinels_and_negative_time(self) -> None:
        native = self._doc(transaction_date=date(2026, 10, 2), transaction_time=timedelta(hours=-1))
        negative = self._doc(transaction_date="2026-10-02", transaction_time="-1:00:00")
        self.assertNotEqual(workflow.get_commitment_digest(native), workflow.get_commitment_digest(negative))
        for invalid in (
            "2026-10-02junk",
            "0000-00-00",
            "0001-01-01",
            "2026-02-30",
            "2026-10-02T00:00:00",
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(workflow._native_temporal(invalid, "Date"), invalid)
        for invalid in (
            "25:06:07junk",
            "-25:06:07",
            "25:60:07",
            "25:06:60",
            "838:60:00",
            "839:00:00",
            "999:00:00",
            "9999:06:07",
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(workflow._native_temporal(invalid, "Time"), invalid)
        self.assertEqual(workflow._native_temporal("0000-00-00 00:00:00", "Datetime"), "0000-00-00 00:00:00")
        self.assertEqual(workflow._native_temporal("0001-01-01 00:00:00", "Datetime"), "0001-01-01 00:00:00")
        self.assertEqual(workflow._native_temporal(date(1, 1, 1), "Date"), date(1, 1, 1))
        self.assertEqual(workflow._native_temporal(timedelta(hours=-1), "Time"), timedelta(hours=-1))
        self.assertEqual(
            workflow._native_temporal("838:59:59.999999", "Time"),
            timedelta(hours=838, minutes=59, seconds=59, microseconds=999999),
        )
        self.assertEqual(
            workflow._native_temporal("2026-10-02 09:10:11junk", "Datetime"), "2026-10-02 09:10:11junk"
        )

    def test_metadata_controls_optional_datetime_and_preserves_numeric_null(self) -> None:
        native = {"custom_delivery_by": datetime(2026, 10, 2, 9, 10, 11, 123456), "conversion_rate": None}
        serialized = {"custom_delivery_by": "2026-10-02 09:10:11.123456", "conversion_rate": None}
        zero = {"custom_delivery_by": "2026-10-02 09:10:11.123456", "conversion_rate": 0}
        actual_meta = frappe.get_meta("Purchase Order")
        actual_get_field = actual_meta.get_field
        actual_get_meta = frappe.get_meta

        def field(name: str) -> object:
            if name == "custom_delivery_by":
                return SimpleNamespace(fieldtype="Datetime")
            return actual_get_field(name)

        with (
            patch.object(actual_meta, "get_field", side_effect=field),
            patch.object(
                workflow.frappe,
                "get_meta",
                side_effect=lambda name: actual_meta if name == "Purchase Order" else actual_get_meta(name),
            ),
        ):
            self.assertEqual(
                workflow.get_commitment_digest(native), workflow.get_commitment_digest(serialized)
            )
            self.assertNotEqual(workflow.get_commitment_digest(native), workflow.get_commitment_digest(zero))
        self.assertNotEqual(
            workflow.get_commitment_digest(native), workflow.get_commitment_digest(serialized)
        )

    def test_maker_capture_requires_canonical_owner_and_write_permission(self) -> None:
        doc = self._doc(owner="EMP-MAKER")

        def canonical(identity: str) -> str:
            return "maker@example.com" if identity == "EMP-MAKER" else identity

        with (
            patch.object(workflow, "require_permission") as permission,
            patch.object(workflow, "resolve_user", side_effect=canonical),
            patch.object(workflow.frappe, "session", Mock(user="maker@example.com")),
        ):
            workflow.capture_maker_snapshot(doc)
        permission.assert_called_once_with(doc, "write")
        self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")

        doc.set("approval_maker_user", None)
        with (
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "resolve_user", side_effect=canonical),
            patch.object(workflow.frappe, "session", Mock(user="other@example.com")),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.capture_maker_snapshot(doc)
        self.assertFalse(doc.get("approval_maker_user"))

        with (
            patch.object(workflow, "require_permission", side_effect=frappe.PermissionError),
            patch.object(workflow, "resolve_user") as resolve,
            self.assertRaises(frappe.PermissionError),
        ):
            workflow.capture_maker_snapshot(doc)
        resolve.assert_not_called()

        doc.set("owner", "")
        with (
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "resolve_user", wraps=approval_controls.resolve_user),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.capture_maker_snapshot(doc)
        self.assertFalse(doc.get("approval_maker_user"))

    def test_downstream_generated_status_values_do_not_invalidate_approval(self) -> None:
        doc = self._doc(
            supplier="SUP-1",
            items=[{"item_code": "A", "qty": 1, "received_qty": 0, "returned_qty": 0}],
        )
        first = workflow.get_commitment_digest(doc)

        doc.set("status", "To Receive")
        doc.set("per_received", 50)
        doc.set("per_billed", 25)
        doc.set("advance_paid", 100)
        doc.get("items")[0].received_qty = 0.5
        doc.get("items")[0].returned_qty = 0.25

        self.assertEqual(first, workflow.get_commitment_digest(doc))

    @patch.object(workflow, "require_permission")
    @patch.object(workflow, "_employee_snapshot", return_value=("EMP-1", "sig"))
    @patch.object(workflow.frappe, "session", Mock(user="reviewer@example.com"))
    def test_review_snapshot_captures_revision_evidence(self, _employee: Mock, _permission: Mock) -> None:
        doc = self._doc(owner="maker@example.com", supplier="SUP-1")
        with (
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(
                workflow, "require_distinct_actors", wraps=workflow.require_distinct_actors
            ) as distinct,
        ):
            workflow.capture_review_snapshot(doc)
        distinct.assert_called_once_with("maker@example.com", "reviewer@example.com", ())
        self.assertEqual(doc.get("approval_digest_version"), workflow.DIGEST_VERSION)
        self.assertEqual(doc.get("approval_reviewer_user"), "reviewer@example.com")
        self.assertEqual(doc.get("checked_by"), "EMP-1")
        self.assertEqual(doc.get("checked_signature"), "sig")

    @patch.object(workflow, "require_permission")
    @patch.object(workflow, "_employee_snapshot", return_value=("EMP-2", "sig"))
    @patch.object(workflow.frappe, "session", Mock(user="approver@example.com"))
    def test_authorization_keeps_prior_reviewer_distinct(self, _employee: Mock, _permission: Mock) -> None:
        doc = self._doc(
            owner="maker@example.com", supplier="SUP-1", approval_reviewer_user="reviewer@example.com"
        )
        doc.set("approval_critical_digest", workflow.get_commitment_digest(doc))
        with (
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(
                workflow, "require_distinct_actors", wraps=workflow.require_distinct_actors
            ) as distinct,
        ):
            workflow.capture_authorization_snapshot(doc)
        distinct.assert_called_once_with(
            "maker@example.com", "approver@example.com", previous_identities=("reviewer@example.com",)
        )
        self.assertEqual(doc.get("approval_authorized_user"), "approver@example.com")

    @patch.object(workflow, "require_permission")
    @patch.object(workflow, "_employee_snapshot", return_value=("EMP-2", "sig"))
    @patch.object(workflow.frappe, "session", Mock(user="reviewer@example.com"))
    def test_reviewer_cannot_authorize_same_order(self, _employee: Mock, _permission: Mock) -> None:
        doc = self._doc(
            owner="maker@example.com", supplier="SUP-1", approval_reviewer_user="reviewer@example.com"
        )
        with (
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.capture_authorization_snapshot(doc)
        self.assertFalse(doc.get("approval_authorized_user"))

    def test_clear_snapshot_removes_all_approval_evidence(self) -> None:
        doc = self._doc(
            workflow_state="Purchase Order Draft",
            owner="maker@example.com",
            approval_maker_user="maker@example.com",
            approval_critical_digest="digest",
            approval_digest_version=workflow.DIGEST_VERSION,
            approval_reviewer_user="reviewer",
            approval_authorized_user="approver",
            checked_by="EMP-1",
            checked_signature="review",
            authorized_by="EMP-2",
            authorized_signature="approve",
        )
        persisted = frappe._dict(
            workflow_state=workflow.APPROVAL_STATE,
            docstatus=0,
            owner="maker@example.com",
            approval_maker_user="maker@example.com",
        )
        with (
            patch.object(workflow.frappe.db, "get_value", return_value=persisted),
            patch.object(workflow, "resolve_user", side_effect=lambda identity: identity),
            patch.object(
                workflow, "authorize_workflow_field_write", return_value="approver@example.com"
            ) as grant,
            patch.object(workflow, "require_distinct_actors") as distinct,
        ):
            workflow.clear_approval_snapshots(doc)
        grant.assert_called_once_with(
            doc, workflow._RETURN_ROUTE, workflow._RETURN_ACTION, ("C-Level Approver",)
        )
        distinct.assert_called_once_with("maker@example.com", "approver@example.com", ())
        for field in workflow.SNAPSHOT_FIELDS:
            self.assertFalse(doc.get(field))

    def test_return_action_rejects_duplicate_or_unexpected_roles(self) -> None:
        doc = self._doc()
        action = frappe._dict(name="WA-1", workflow_state=workflow.APPROVED_STATE)
        for actions, roles in (
            ([action, action], [frappe._dict(role="Purchase Manager")]),
            ([action], [frappe._dict(role="Purchase Manager"), frappe._dict(role="Purchase Manager")]),
            ([action], [frappe._dict(role="Purchase User")]),
        ):
            with (
                patch.object(workflow.frappe.db, "sql", side_effect=[actions, roles]),
                self.assertRaises(frappe.ValidationError),
            ):
                workflow._return_action(doc, workflow.APPROVED_STATE)

    def test_raw_return_cannot_mint_completion(self) -> None:
        previous = self._doc(workflow_state=workflow.APPROVED_STATE, owner="maker@example.com")
        doc = self._doc(workflow_state="Purchase Order Draft", owner="maker@example.com")
        with (
            patch.object(Document, "get_doc_before_save", return_value=previous),
            patch.object(workflow, "consume_approval_field_grant", side_effect=frappe.ValidationError),
            patch.object(workflow, "update_completed_workflow_actions_using_role") as complete,
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_workflow(doc)
        complete.assert_not_called()

    @patch.object(workflow.frappe, "throw")
    def test_mutation_after_review_is_rejected(self, throw: Mock) -> None:
        previous = self._doc(workflow_state=workflow.APPROVAL_STATE, supplier="SUP-1")
        current = self._doc(workflow_state=workflow.APPROVAL_STATE, supplier="SUP-2")
        with patch.object(Document, "get_doc_before_save", return_value=previous):
            workflow.validate_workflow(current)
        throw.assert_called_once()

    @patch.object(workflow.frappe, "throw")
    @patch.object(workflow, "require_permission")
    def test_submit_requires_persisted_approved_digest_and_signatures(
        self, _permission: Mock, throw: Mock
    ) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-1")
        digest = workflow.get_commitment_digest(doc)
        doc.set("approval_critical_digest", digest)
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": digest,
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "submit"),
        )
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(approval_controls, "resolve_user", side_effect=lambda identity: identity),
            patch.object(
                workflow, "require_distinct_actors", wraps=workflow.require_distinct_actors
            ) as distinct,
        ):
            workflow.validate_before_submit(doc)
        self.assertEqual(
            distinct.call_args_list,
            [
                call("maker@example.com", "reviewer@example.com", previous_identities=()),
                call(
                    "maker@example.com",
                    "approver@example.com",
                    previous_identities=("reviewer@example.com",),
                ),
            ],
        )
        throw.assert_not_called()

    @patch.object(workflow, "require_permission")
    def test_state_spoof_without_native_post_transition_is_rejected(self, _permission: Mock) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-1")
        digest = workflow.get_commitment_digest(doc)
        doc.set("approval_critical_digest", digest)
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": digest,
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    @patch.object(workflow, "require_permission")
    def test_submit_rejects_stale_commitment_digest(self, _permission: Mock) -> None:
        doc = self._doc(workflow_state=workflow.SUBMITTED_STATE, owner="maker@example.com", supplier="SUP-2")
        doc.set("approval_critical_digest", "old-digest")
        persisted = {
            "workflow_state": workflow.APPROVED_STATE,
            "owner": "maker@example.com",
            "approval_digest_version": workflow.DIGEST_VERSION,
            "approval_critical_digest": "old-digest",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_authorized_user": "approver@example.com",
            "checked_signature": "review",
            "authorized_signature": "approve",
        }
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "submit"),
        )

        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_persisted_approval_uses_row_lock(self) -> None:
        doc = self._doc()
        with patch.object(workflow.frappe.db, "get_value", return_value={"workflow_state": "Draft"}) as get:
            workflow._persisted_approval(doc)

        self.assertTrue(get.call_args.kwargs["for_update"])

    def test_cancel_accepts_only_native_submitted_to_cancelled_transition(self) -> None:
        doc = self._doc(docstatus=1, workflow_state=workflow.CANCELLED_STATE)
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "cancel"),
        )

        with patch.object(workflow.frappe.db, "get_value", return_value=workflow.SUBMITTED_STATE):
            workflow.validate_before_cancel(doc)

    @patch.object(workflow.frappe, "throw")
    def test_cancel_requires_persisted_submitted_state(self, throw: Mock) -> None:
        doc = self._doc(docstatus=1, workflow_state=workflow.CANCELLED_STATE)
        setattr(
            workflow.frappe.flags,
            workflow._EXECUTION_FLAG,
            workflow._execution_marker(doc, "cancel"),
        )

        with patch.object(workflow.frappe.db, "get_value", return_value=workflow.APPROVED_STATE):
            workflow.validate_before_cancel(doc)

        throw.assert_called_once()
