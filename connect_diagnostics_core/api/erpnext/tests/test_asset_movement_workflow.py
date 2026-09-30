# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import asset_movement_workflow as workflow


class TestAssetMovementWorkflow(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        if hasattr(frappe.local, workflow._CAPABILITY_STACK):
            delattr(frappe.local, workflow._CAPABILITY_STACK)

    def test_capability_is_request_local_and_exception_safe(self) -> None:
        with self.assertRaises(RuntimeError):
            with workflow.native_asset_movement_capability("AST-1", "submit"):
                capability = workflow._top_capability("submit")
                self.assertIsNotNone(capability)
                assert capability is not None
                self.assertEqual(capability.asset_name, "AST-1")
                raise RuntimeError("cleanup")
        self.assertIsNone(workflow._top_capability("submit"))

    def test_nested_capabilities_restore_outer_identity(self) -> None:
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            outer = workflow._top_capability("submit")
            with workflow.native_asset_movement_capability("AST-2", "submit"):
                self.assertNotEqual(workflow._top_capability("submit"), outer)
            self.assertIs(workflow._top_capability("submit"), outer)
        self.assertFalse(hasattr(frappe.local, workflow._CAPABILITY_STACK))

    def test_native_receipt_accepts_nullable_purchase_invoice_reference(self) -> None:
        asset = frappe._dict(name="AST-1", company="C", location="L", custodian=None)
        movement = frappe._dict(
            company="C",
            purpose="Receipt",
            reference_doctype="Purchase Invoice",
            reference_name=None,
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
        )
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            workflow.validate_native_asset_receipt(movement, asset)

    def test_native_receipt_rejects_wrong_shape_and_replay(self) -> None:
        asset = frappe._dict(
            name="AST-1", company="C", location="L", custodian="EMP-1", purchase_receipt="PR-1"
        )
        movement = frappe._dict(
            company="C",
            purpose="Receipt",
            reference_doctype="Purchase Receipt",
            reference_name="PR-1",
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee="EMP-1")],
        )
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            workflow.validate_native_asset_receipt(movement, asset)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_native_asset_receipt(movement, asset)

    def test_capability_is_not_exposed_and_cannot_be_replayed(self) -> None:
        asset = frappe._dict(name="AST-1", company="C", location="L", custodian=None)
        movement = frappe._dict(
            company="C",
            purpose="Receipt",
            reference_doctype="Purchase Invoice",
            reference_name=None,
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
        )
        with workflow.native_asset_movement_capability("AST-1", "submit") as exposed_capability:
            self.assertIsNone(exposed_capability)
            workflow.validate_native_asset_receipt(movement, asset)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_native_asset_receipt(movement, asset)

    def test_native_receipt_rejects_shape_mismatches(self) -> None:
        asset = frappe._dict(
            name="AST-1", company="C", location="L", custodian="EMP-1", purchase_receipt="PR-1"
        )
        base: Any = frappe._dict(
            company="C",
            purpose="Receipt",
            reference_doctype="Purchase Receipt",
            reference_name="PR-1",
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee="EMP-1")],
        )
        variants = (
            (
                "wrong row asset",
                {"assets": [frappe._dict(asset="AST-2", target_location="L", to_employee="EMP-1")]},
            ),
            ("multiple rows", {"assets": [base.assets[0], frappe._dict(asset="AST-1")]}),
            ("company", {"company": "OTHER"}),
            ("purpose", {"purpose": "Transfer"}),
            ("reference doctype", {"reference_doctype": "Purchase Invoice"}),
            ("reference name", {"reference_name": "PR-2"}),
            (
                "location",
                {"assets": [frappe._dict(asset="AST-1", target_location="OTHER", to_employee="EMP-1")]},
            ),
            (
                "custodian",
                {"assets": [frappe._dict(asset="AST-1", target_location="L", to_employee="EMP-2")]},
            ),
        )
        for label, changes in variants:
            with self.subTest(label=label):
                candidate = frappe._dict(base)
                candidate.update(changes)
                with workflow.native_asset_movement_capability("AST-1", "submit"):
                    with self.assertRaises(frappe.ValidationError):
                        workflow.validate_native_asset_receipt(candidate, asset)

    def test_receipt_reference_variants(self) -> None:
        for reference_doctype, reference_name, purchase_receipt, purchase_invoice in (
            ("Purchase Receipt", "PR-1", "PR-1", None),
            ("Purchase Invoice", "PI-1", None, "PI-1"),
            ("Purchase Invoice", None, None, None),
        ):
            with self.subTest(reference_doctype=reference_doctype, reference_name=reference_name):
                asset = frappe._dict(
                    name="AST-1",
                    company="C",
                    location="L",
                    custodian=None,
                    purchase_receipt=purchase_receipt,
                    purchase_invoice=purchase_invoice,
                )
                movement = frappe._dict(
                    company="C",
                    purpose="Receipt",
                    reference_doctype=reference_doctype,
                    reference_name=reference_name,
                    assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
                )
                with workflow.native_asset_movement_capability("AST-1", "submit"):
                    workflow.validate_native_asset_receipt(movement, asset)

    def test_cancel_requires_matching_asset(self) -> None:
        movement = frappe._dict(assets=[frappe._dict(asset="AST-1")])
        with workflow.native_asset_movement_capability("AST-1", "cancel"):
            workflow.validate_native_asset_cancel(movement, "AST-1")
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_native_asset_cancel(frappe._dict(assets=[]), "AST-1")

    def test_cancel_rejects_absent_or_wrong_capability_and_mixed_rows(self) -> None:
        movement = frappe._dict(assets=[frappe._dict(asset="AST-1"), frappe._dict(asset="AST-2")])
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_native_asset_cancel(movement, "AST-1")
        with workflow.native_asset_movement_capability("AST-2", "cancel"):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_native_asset_cancel(movement, "AST-1")

    def test_lock_asset_rows_is_sorted_and_duplicate_free(self) -> None:
        with patch.object(workflow.frappe.db, "get_value") as get_value:
            self.assertEqual(workflow.lock_asset_rows(["AST-2", "AST-1", "AST-2"]), ("AST-1", "AST-2"))
        self.assertEqual(
            get_value.call_args_list,
            [
                (("Asset", "AST-1", "name"), {"for_update": True}),
                (("Asset", "AST-2", "name"), {"for_update": True}),
            ],
        )

    def test_mixin_delegates_native_methods_inside_capability(self) -> None:
        class Parent:
            def make_asset_movement(self) -> str:
                self.submit_capability = workflow._top_capability("submit")
                return "submitted"

            def cancel_movement_entries(self) -> str:
                self.cancel_capability = workflow._top_capability("cancel")
                return "cancelled"

        class Asset(workflow.AssetMovementNativeMixin, Parent):
            def __init__(self) -> None:
                self.name = "AST-1"

            def get(self, fieldname: str) -> str:
                return getattr(self, fieldname)

        asset: Any = Asset()
        self.assertEqual(asset.make_asset_movement(), "submitted")
        self.assertEqual(asset.cancel_movement_entries(), "cancelled")
        self.assertIsNone(workflow._top_capability("submit"))
        self.assertIsNone(workflow._top_capability("cancel"))
        self.assertEqual(asset.submit_capability.asset_name, "AST-1")
        self.assertEqual(asset.cancel_capability.asset_name, "AST-1")

    def test_workflow_mixin_only_bypasses_core_validation_for_native_capability(self) -> None:
        class Parent:
            def validate_workflow(self) -> str:
                return "validated"

        class Movement(workflow.AssetMovementWorkflowMixin, Parent):
            def __init__(self, action: str | None = None) -> None:
                self._action = action
                self.workflow_state = workflow.STATE_DRAFT

            def set(self, fieldname: str, value: str) -> None:
                setattr(self, fieldname, value)

        ordinary: Any = Movement("submit")
        self.assertEqual(ordinary.validate_workflow(), "validated")
        self.assertEqual(ordinary.workflow_state, workflow.STATE_DRAFT)

        native_submit: Any = Movement("submit")
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            self.assertIsNone(native_submit.validate_workflow())
        self.assertEqual(native_submit.workflow_state, workflow.STATE_SUBMITTED)

        wrong_action: Any = Movement("save")
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            self.assertEqual(wrong_action.validate_workflow(), "validated")
        self.assertEqual(wrong_action.workflow_state, workflow.STATE_DRAFT)

    def test_critical_payload_preserves_server_values_and_row_order(self) -> None:
        doc: Any = frappe._dict(
            company="C",
            purpose="Transfer",
            transaction_date="2026-09-26",
            reference_doctype="Material Request",
            reference_name="MAT-1",
            material_request="MAT-1",
            workflow_state=workflow.STATE_PENDING_REVIEW,
            assets=[
                frappe._dict(asset="AST-2", company="C", source_location="L2", target_location="L3"),
                frappe._dict(asset="AST-1", company="C", source_location="L1", target_location="L2"),
            ],
        )
        payload = workflow.critical_payload(doc)
        self.assertEqual(payload["assets"][0][0], "AST-2")
        self.assertNotIn("workflow_state", payload)
        original_digest = workflow.critical_digest(doc)
        doc.assets[0].company = "OTHER"
        self.assertNotEqual(original_digest, workflow.critical_digest(doc))

    def test_workflow_states_match_approved_fixture_names(self) -> None:
        self.assertEqual(
            (
                workflow.STATE_DRAFT,
                workflow.STATE_PENDING_REVIEW,
                workflow.STATE_PENDING_APPROVAL,
                workflow.STATE_APPROVED,
                workflow.STATE_REJECTED,
                workflow.STATE_SUBMITTED,
                workflow.STATE_CANCELLED,
            ),
            (
                "Asset Movement Draft",
                "Asset Movement Pending Review",
                "Asset Movement Pending Approval",
                "Asset Movement Approved",
                "Asset Movement Rejected",
                "Asset Movement Submitted",
                "Asset Movement Cancelled",
            ),
        )

    def test_direct_submit_requires_approved_persisted_state(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement", name="AM-1", workflow_state=workflow.STATE_SUBMITTED
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(
                workflow,
                "_persisted_state",
                return_value={"workflow_state": workflow.STATE_PENDING_APPROVAL},
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)

    def test_submit_requires_and_consumes_workflow_object_marker(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            workflow_state=workflow.STATE_SUBMITTED,
            company="C",
            assets=[],
        )
        persisted = {
            "workflow_state": workflow.STATE_APPROVED,
            "approval_critical_digest": "digest",
            "approval_maker_user": "maker@example.com",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_approver_user": "approver@example.com",
        }
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(workflow, "_persisted_state", return_value=persisted),
            patch.object(workflow, "critical_digest", return_value="digest"),
            patch.object(workflow, "_require_snapshot"),
            patch.object(workflow.approval_controls, "require_distinct_actors"),
        ):
            workflow.authorize_submit_transition(doc)
            workflow.validate_before_submit(doc)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)

    def test_submit_rejects_stale_critical_digest(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            workflow_state=workflow.STATE_SUBMITTED,
            company="C",
            assets=[],
        )
        persisted = {
            "workflow_state": workflow.STATE_APPROVED,
            "approval_critical_digest": "old-digest",
            "approval_maker_user": "maker@example.com",
            "approval_reviewer_user": "reviewer@example.com",
            "approval_approver_user": "approver@example.com",
        }
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(workflow, "_persisted_state", return_value=persisted),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)

    def test_capture_review_requires_maker_and_uses_shared_signed_capture(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            approval_maker_user="maker@example.com",
            assets=[],
        )
        snapshot = workflow.approval_controls.SignedApprovalSnapshot(
            user="reviewer@example.com",
            employee="EMP-1",
            employee_name="Reviewer",
            acted_at=frappe.utils.now_datetime(),
            signature="sig",
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(
                workflow.approval_controls,
                "capture_signed_approval_actor",
                return_value=snapshot,
            ) as capture,
        ):
            workflow.capture_review(doc)
        capture.assert_called_once_with(doc, "maker@example.com")
        self.assertEqual(doc.approval_reviewer_user, "reviewer@example.com")
        self.assertEqual(doc.checked_by, "EMP-1")
        self.assertEqual(doc.checked_signature, "sig")

    def test_capture_review_without_maker_fails_closed(self) -> None:
        doc: Any = frappe._dict(doctype="Asset Movement", name="AM-1", assets=[])
        with patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}):
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_review(doc)

    def test_capture_approval_requires_distinct_prior_actor(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            assets=[],
        )
        snapshot = workflow.approval_controls.SignedApprovalSnapshot(
            user="approver@example.com",
            employee="EMP-2",
            employee_name="Approver",
            acted_at=frappe.utils.now_datetime(),
            signature="sig-2",
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.APPROVER_ROLE}),
            patch.object(
                workflow.approval_controls,
                "capture_signed_approval_actor",
                return_value=snapshot,
            ) as capture,
        ):
            workflow.capture_approval(doc)
        capture.assert_called_once_with(doc, "maker@example.com", ("reviewer@example.com",))
        self.assertEqual(doc.approval_approver_user, "approver@example.com")
        self.assertEqual(doc.authorized_by, "EMP-2")

    def test_validate_workflow_requires_evidence_and_rejects_critical_mutation(self) -> None:
        incomplete: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            workflow_state=workflow.STATE_PENDING_REVIEW,
            assets=[],
        )
        incomplete.get_doc_before_save = lambda: None
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_workflow(incomplete)

        previous: Any = frappe._dict(
            workflow_state=workflow.STATE_PENDING_REVIEW,
            company="C",
            assets=[frappe._dict(asset="AST-1", company="C")],
        )
        changed: Any = frappe._dict(
            workflow_state=workflow.STATE_PENDING_APPROVAL,
            approval_maker_user="maker@example.com",
            approval_critical_digest="digest",
            company="C",
            assets=[frappe._dict(asset="AST-2", company="C")],
        )
        changed.get_doc_before_save = lambda: previous
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_workflow(changed)

    def test_capability_helper_is_not_whitelisted(self) -> None:
        self.assertFalse(hasattr(workflow.native_asset_movement_capability, "is_whitelisted"))

    def test_native_before_submit_validates_and_consumes_exact_receipt(self) -> None:
        asset = frappe._dict(name="AST-1", company="C", location="L", custodian=None)
        movement: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            workflow_state=workflow.STATE_DRAFT,
            company="C",
            purpose="Receipt",
            reference_doctype="Purchase Invoice",
            reference_name=None,
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
        )
        with patch.object(workflow.frappe, "get_doc", return_value=asset):
            with workflow.native_asset_movement_capability("AST-1", "submit"):
                workflow.validate_before_submit(movement)
                self.assertEqual(movement.workflow_state, workflow.STATE_SUBMITTED)
                with self.assertRaises(frappe.ValidationError):
                    workflow.validate_before_submit(movement)

    def test_native_before_submit_rejects_wrong_receipt_shape(self) -> None:
        asset = frappe._dict(name="AST-1", company="C", location="L", custodian=None)
        movement: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            company="OTHER",
            purpose="Receipt",
            reference_doctype="Purchase Invoice",
            reference_name=None,
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
        )
        with patch.object(workflow.frappe, "get_doc", return_value=asset):
            with workflow.native_asset_movement_capability("AST-1", "submit"):
                with self.assertRaises(frappe.ValidationError):
                    workflow.validate_before_submit(movement)

    def test_direct_cancel_requires_submitted_state(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement", name="AM-1", workflow_state=workflow.STATE_SUBMITTED
        )
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_before_cancel(doc)

    def test_workflow_cancel_requires_cancelled_state_and_persisted_submission(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement", name="AM-1", workflow_state=workflow.STATE_CANCELLED
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(
                workflow, "_persisted_state", return_value={"workflow_state": workflow.STATE_SUBMITTED}
            ),
        ):
            workflow.authorize_cancel_transition(doc)
            workflow.validate_before_cancel(doc)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_cancel(doc)

    def test_direct_cancel_without_object_marker_is_denied(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement", name="AM-1", workflow_state=workflow.STATE_CANCELLED
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(
                workflow, "_persisted_state", return_value={"workflow_state": workflow.STATE_SUBMITTED}
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_cancel(doc)

    def test_reset_approval_clears_all_protected_evidence(self) -> None:
        doc: Any = frappe._dict(
            **{
                field: "value"
                for field in (
                    "approval_maker_user",
                    "approval_reviewer_user",
                    "approval_approver_user",
                    "approval_critical_digest",
                    "checked_by",
                    "checked_at",
                    "checked_signature",
                    "authorized_by",
                    "authorized_at",
                    "authorized_signature",
                )
            }
        )
        workflow.reset_approval(doc)
        self.assertTrue(all(doc.get(field) is None for field in doc))

    def test_capture_maker_resets_previous_approval_cycle(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            company="C",
            workflow_state=workflow.STATE_REJECTED,
            approval_reviewer_user="reviewer@example.com",
            approval_approver_user="approver@example.com",
            checked_signature="old-check",
            authorized_signature="old-approval",
            assets=[],
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.MAKER_ROLE}),
            patch.object(workflow.approval_controls, "resolve_user", return_value="maker@example.com"),
        ):
            workflow.capture_maker(doc)
        self.assertEqual(doc.approval_maker_user, "maker@example.com")
        self.assertIsNone(doc.approval_reviewer_user)
        self.assertIsNone(doc.approval_approver_user)
        self.assertIsNone(doc.checked_signature)
        self.assertIsNone(doc.authorized_signature)

    def test_linked_material_request_is_approval_critical_and_cannot_be_rewritten(self) -> None:
        doc: Any = frappe._dict(
            company="C",
            purpose="Transfer",
            transaction_date="2026-09-26",
            reference_doctype="Material Request",
            reference_name="MAT-1",
            material_request="MAT-1",
            assets=[frappe._dict(asset="AST-1", company="C", source_location="L1", target_location="L2")],
        )
        digest = workflow.critical_digest(doc)
        doc.material_request = "MAT-2"
        self.assertNotEqual(digest, workflow.critical_digest(doc))

    def test_return_and_reject_are_not_receipt_capability_paths(self) -> None:
        for purpose in ("Return", "Reject"):
            with self.subTest(purpose=purpose):
                movement = frappe._dict(
                    company="C",
                    purpose=purpose,
                    reference_doctype="Material Request",
                    reference_name="MAT-1",
                    assets=[frappe._dict(asset="AST-1", target_location="L2", to_employee=None)],
                )
                asset = frappe._dict(name="AST-1", company="C", location="L1", custodian=None)
                with workflow.native_asset_movement_capability("AST-1", "submit"):
                    with self.assertRaises(frappe.ValidationError):
                        workflow.validate_native_asset_receipt(movement, asset)

    def test_wrong_role_and_self_approval_fail_closed(self) -> None:
        doc: Any = frappe._dict(doctype="Asset Movement", name="AM-1", assets=[])
        with patch.object(workflow, "_roles", return_value={workflow.MAKER_ROLE}):
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_review(doc)
        with (
            patch.object(workflow, "_roles", return_value={workflow.APPROVER_ROLE}),
            patch.object(workflow.approval_controls, "capture_signed_approval_actor") as capture,
        ):
            capture.side_effect = frappe.ValidationError("same actor")
            doc.update(approval_maker_user="maker@example.com", approval_reviewer_user="reviewer@example.com")
            with self.assertRaises(frappe.ValidationError):
                workflow.capture_approval(doc)

    def test_multi_asset_lock_and_history_digest_are_deterministic(self) -> None:
        rows = [
            frappe._dict(asset="AST-2", company="C"),
            frappe._dict(asset="AST-1", company="C"),
        ]
        with patch.object(workflow.frappe.db, "get_value") as get_value:
            self.assertEqual(workflow.lock_asset_rows([str(row.asset) for row in rows]), ("AST-1", "AST-2"))
        self.assertEqual(get_value.call_count, 2)
        doc: Any = frappe._dict(company="C", purpose="Transfer", assets=rows)
        first = workflow.critical_digest(doc)
        doc.assets.reverse()
        self.assertNotEqual(first, workflow.critical_digest(doc))

    def test_failed_submit_does_not_leave_transition_marker_consumed(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement",
            name="AM-1",
            workflow_state=workflow.STATE_SUBMITTED,
            company="C",
            assets=[],
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(workflow, "_persisted_state", return_value=None),
        ):
            workflow.authorize_submit_transition(doc)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_submit(doc)
            self.assertIsNone(getattr(doc, workflow._SUBMIT_MARKER_FIELD, None))

    def test_retry_after_successful_transition_is_rejected(self) -> None:
        doc: Any = frappe._dict(
            doctype="Asset Movement", name="AM-1", workflow_state=workflow.STATE_CANCELLED
        )
        with (
            patch.object(workflow, "_roles", return_value={workflow.REVIEWER_ROLE}),
            patch.object(workflow.approval_controls, "require_permission"),
            patch.object(
                workflow, "_persisted_state", return_value={"workflow_state": workflow.STATE_SUBMITTED}
            ),
        ):
            workflow.authorize_cancel_transition(doc)
            workflow.validate_before_cancel(doc)
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_before_cancel(doc)

    def test_non_receipt_native_asset_movement_is_not_bypassed(self) -> None:
        asset = frappe._dict(name="AST-1", company="C", location="L", custodian=None)
        movement = frappe._dict(
            company="C",
            purpose="Transfer",
            reference_doctype="Asset Movement",
            reference_name="AM-1",
            assets=[frappe._dict(asset="AST-1", target_location="L", to_employee=None)],
        )
        with workflow.native_asset_movement_capability("AST-1", "submit"):
            with self.assertRaises(frappe.ValidationError):
                workflow.validate_native_asset_receipt(movement, asset)


class TestAssetMovementWorkflowIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        print_patcher = patch("frappe.attach_print", return_value={})
        print_patcher.start()
        self.addCleanup(print_patcher.stop)

    def _actor(self, email: str, role: str, *, signature: str | None = None) -> tuple[str, str]:
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email,
                    "send_welcome_email": 0,
                    "roles": [{"role": role}],
                }
            ).insert(ignore_permissions=True)
        user = frappe.get_doc("User", email)
        user.add_roles(role)
        employee = f"_TEST-{role.upper().replace(' ', '-')}-{frappe.generate_hash(length=6)}"
        employee_doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "name": employee,
                "employee": employee,
                "employee_name": email,
                "first_name": email,
                "company": "_Test Company",
                "user_id": email,
                "status": "Active",
                "approval_signature": signature,
            }
        )
        employee_doc.db_insert()
        frappe.clear_cache(user=email)
        return email, employee

    def _location(self, label: str) -> str:
        name = f"_Test Asset Movement {label} {frappe.generate_hash(length=6)}"
        location = frappe.get_doc({"doctype": "Location", "name": name, "location_name": name, "is_group": 0})
        location.db_insert()
        return name

    def _asset(self, source_location: str) -> Any:
        name = f"_TEST-ASSET-{frappe.generate_hash(length=8)}"
        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "name": name,
                "asset_name": name,
                "company": "_Test Company",
                "purchase_date": "2026-09-26",
                "location": source_location,
                "status": "Submitted",
                "docstatus": 1,
            }
        )
        asset.db_insert()
        return frappe.get_doc("Asset", name)

    def _material_request(self, allocated_asset: str | None) -> str:
        name = f"_TEST-MR-ASSET-{frappe.generate_hash(length=8)}"
        request = frappe.get_doc(
            {
                "doctype": "Material Request",
                "name": name,
                "company": "_Test Company",
                "material_request_type": "Material Transfer",
                "transaction_date": "2026-09-26",
                "schedule_date": "2026-09-26",
                "docstatus": 1,
            }
        )
        request.db_insert()
        item = frappe.get_doc(
            {
                "doctype": "Material Request Item",
                "name": f"_TEST-MRI-{frappe.generate_hash(length=8)}",
                "parent": name,
                "parenttype": "Material Request",
                "parentfield": "items",
                "idx": 1,
                "item_code": "_Test Item",
                "qty": 1,
                "schedule_date": "2026-09-26",
                "fulfillment_route": "Existing Asset",
                "allocated_asset": allocated_asset,
            }
        )
        item.db_insert()
        return name

    def test_linked_material_request_uses_real_validation_hook(self) -> None:
        maker, _ = self._actor("_test.asset.mr.maker@example.com", workflow.MAKER_ROLE)
        original_user = frappe.session.user
        try:
            frappe.set_user("Administrator")
            source_location = self._location("MR Source")
            target_location = self._location("MR Target")
            asset = self._asset(source_location)
            valid_request = self._material_request(asset.name)
            invalid_request = self._material_request(None)

            frappe.set_user(maker)
            movement_values = {
                "doctype": "Asset Movement",
                "company": asset.company,
                "purpose": "Transfer",
                "transaction_date": frappe.utils.now(),
                "assets": [
                    {
                        "asset": asset.name,
                        "company": asset.company,
                        "source_location": source_location,
                        "target_location": target_location,
                    }
                ],
            }
            valid = frappe.get_doc({**movement_values, "material_request": valid_request}).insert()
            self.assertEqual(valid.material_request, valid_request)

            with self.assertRaises(frappe.ValidationError):
                frappe.get_doc({**movement_values, "material_request": invalid_request}).insert()
        finally:
            frappe.set_user(original_user)

    def test_native_receipt_and_generic_workflow_submit_cancel(self) -> None:
        maker, _ = self._actor("_test.asset.maker@example.com", workflow.MAKER_ROLE)
        reviewer, reviewer_employee = self._actor(
            "_test.asset.reviewer@example.com",
            workflow.REVIEWER_ROLE,
            signature="<svg>reviewer</svg>",
        )
        approver, approver_employee = self._actor(
            "_test.asset.approver@example.com",
            workflow.APPROVER_ROLE,
            signature="<svg>approver</svg>",
        )
        original_user = frappe.session.user
        try:
            frappe.set_user("Administrator")
            source_location = self._location("Source")
            target_location = self._location("Target")
            asset = self._asset(source_location)
            second_asset = self._asset(source_location)
            asset.make_asset_movement()
            second_asset.make_asset_movement()

            native_receipt = frappe.db.get_value(
                "Asset Movement",
                [["Asset Movement Item", "asset", "=", asset.name], ["purpose", "=", "Receipt"]],
                ["name", "docstatus", "workflow_state"],
                as_dict=True,
                order_by="creation desc",
            )
            second_native_receipt = frappe.db.get_value(
                "Asset Movement",
                [
                    ["Asset Movement Item", "asset", "=", second_asset.name],
                    ["purpose", "=", "Receipt"],
                ],
                ["name", "docstatus", "workflow_state"],
                as_dict=True,
                order_by="creation desc",
            )
            self.assertEqual(native_receipt.docstatus, 1)
            self.assertEqual(native_receipt.workflow_state, workflow.STATE_SUBMITTED)
            self.assertEqual(second_native_receipt.docstatus, 1)
            self.assertEqual(second_native_receipt.workflow_state, workflow.STATE_SUBMITTED)

            frappe.set_user(maker)
            movement = frappe.get_doc(
                {
                    "doctype": "Asset Movement",
                    "company": asset.company,
                    "purpose": "Transfer",
                    "transaction_date": frappe.utils.now(),
                    "assets": [
                        {
                            "asset": asset.name,
                            "company": asset.company,
                            "source_location": source_location,
                            "target_location": target_location,
                        },
                        {
                            "asset": second_asset.name,
                            "company": second_asset.company,
                            "source_location": source_location,
                            "target_location": target_location,
                        },
                    ],
                }
            ).insert()
            self.assertIn(workflow.MAKER_ROLE, frappe.get_roles())
            self.assertEqual(movement.workflow_state, workflow.STATE_DRAFT)
            movement = apply_workflow(movement, "Send Asset Movement for Review")
            self.assertEqual(movement.workflow_state, workflow.STATE_PENDING_REVIEW)

            frappe.get_doc("User", maker).add_roles(workflow.REVIEWER_ROLE)
            frappe.clear_cache(user=maker)
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(movement, "Review Asset Movement")

            frappe.set_user(approver)
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(movement, "Review Asset Movement")

            frappe.set_user(reviewer)
            movement = apply_workflow(movement, "Return Asset Movement")
            self.assertEqual(movement.workflow_state, workflow.STATE_DRAFT)

            frappe.set_user(maker)
            movement = apply_workflow(movement, "Send Asset Movement for Review")
            frappe.set_user(reviewer)
            movement = apply_workflow(movement, "Review Asset Movement")
            self.assertEqual(movement.workflow_state, workflow.STATE_PENDING_APPROVAL)
            self.assertEqual(movement.checked_by, reviewer_employee)

            frappe.set_user(approver)
            movement = apply_workflow(movement, "Reject Asset Movement")
            self.assertEqual(movement.workflow_state, workflow.STATE_REJECTED)
            self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), source_location)
            self.assertEqual(frappe.db.get_value("Asset", second_asset.name, "location"), source_location)

            frappe.set_user(maker)
            movement = apply_workflow(movement, "Resubmit Asset Movement")
            frappe.set_user(reviewer)
            movement = apply_workflow(movement, "Review Asset Movement")
            frappe.set_user(approver)
            movement = apply_workflow(movement, "Approve Asset Movement")
            self.assertEqual(movement.workflow_state, workflow.STATE_APPROVED)
            self.assertEqual(movement.authorized_by, approver_employee)

            frappe.set_user(reviewer)
            with self.assertRaises(frappe.ValidationError):
                movement.submit()
            movement.reload()
            frappe.db.savepoint("asset_movement_submit_retry")
            with (
                patch.object(type(movement), "on_submit", side_effect=frappe.ValidationError("retry")),
                self.assertRaises(frappe.ValidationError),
            ):
                apply_workflow(movement, "Submit Asset Movement")
            frappe.db.rollback(save_point="asset_movement_submit_retry")
            movement = frappe.get_doc("Asset Movement", movement.name)
            self.assertEqual(movement.docstatus, 0)
            self.assertEqual(movement.workflow_state, workflow.STATE_APPROVED)

            movement = apply_workflow(movement, "Submit Asset Movement")
            self.assertEqual(movement.docstatus, 1)
            self.assertEqual(movement.workflow_state, workflow.STATE_SUBMITTED)
            self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), target_location)
            self.assertEqual(frappe.db.get_value("Asset", second_asset.name, "location"), target_location)
            self.assertTrue(frappe.db.exists("Asset Activity", {"asset": asset.name}))
            self.assertTrue(frappe.db.exists("Asset Activity", {"asset": second_asset.name}))

            with self.assertRaises(frappe.ValidationError):
                movement.cancel()
            movement.reload()
            movement = apply_workflow(movement, "Cancel Asset Movement")
            self.assertEqual(movement.docstatus, 2)
            self.assertEqual(movement.workflow_state, workflow.STATE_CANCELLED)
            self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), source_location)
            self.assertEqual(frappe.db.get_value("Asset", second_asset.name, "location"), source_location)

            frappe.set_user("Administrator")
            asset.reload()
            asset.cancel_movement_entries()
            second_asset.reload()
            second_asset.cancel_movement_entries()
            self.assertEqual(
                frappe.db.get_value("Asset Movement", native_receipt.name, "workflow_state"),
                workflow.STATE_CANCELLED,
            )
            self.assertEqual(
                frappe.db.get_value("Asset Movement", second_native_receipt.name, "workflow_state"),
                workflow.STATE_CANCELLED,
            )
        finally:
            frappe.set_user(original_user)
