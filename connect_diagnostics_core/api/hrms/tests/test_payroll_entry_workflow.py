# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import approval_controls
from connect_diagnostics_core.api.hrms import payroll_entry_workflow as workflow


class _NativePayrollOperations:
    def create_salary_slips(self, *args: object, **kwargs: object) -> tuple[str, tuple[object, ...], dict]:
        return ("create", args, kwargs)

    def submit_salary_slips(self, *args: object, **kwargs: object) -> tuple[str, tuple[object, ...], dict]:
        return ("submit", args, kwargs)

    def make_accrual_jv_entry(self, *args: object, **kwargs: object) -> tuple[str, tuple[object, ...], dict]:
        return ("accrual", args, kwargs)

    def make_bank_entry(self, *args: object, **kwargs: object) -> tuple[str, tuple[object, ...], dict]:
        return ("bank", args, kwargs)


class _GuardedPayroll(workflow.PayrollEntryApprovalMixin, _NativePayrollOperations):
    pass


class TestPayrollEntryWorkflow(UnitTestCase):
    def tearDown(self) -> None:
        if hasattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY):
            delattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY)
        super().tearDown()

    def _doc(self, **values: object) -> Document:
        return Document(
            {
                "doctype": "Payroll Entry",
                "name": "PE-1",
                "company": "ACME",
                "posting_date": "2026-09-26",
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "employees": [
                    {
                        "name": "ROW-1",
                        "employee": "EMP-1",
                        "department": "OPS",
                        "designation": "Technician",
                        "is_salary_withheld": 0,
                    }
                ],
                **values,
            }
        )

    def test_digest_is_deterministic_versioned_and_excludes_salary_values(self) -> None:
        doc = self._doc(department="OPS", gross_pay=999999)
        equivalent = self._doc(department="OPS", gross_pay=1)
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=["department"]),
            patch.object(workflow, "_payroll_source_revisions", return_value={"revision": "same"}),
        ):
            payload = workflow.approval_payload(doc)
            self.assertEqual(
                workflow.get_approval_digest(doc),
                workflow.get_approval_digest(equivalent),
            )
        self.assertEqual(payload["digest_version"], workflow.DIGEST_VERSION)
        self.assertEqual(payload["department"], "OPS")
        self.assertNotIn("gross_pay", payload)
        self.assertNotIn("base", payload["source_revisions"])

    def test_digest_changes_for_employee_and_dynamic_dimension(self) -> None:
        doc = self._doc(department="OPS")
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=["department"]),
            patch.object(workflow, "_payroll_source_revisions", return_value={"revision": "same"}),
        ):
            first = workflow.get_approval_digest(doc)
            doc.get("employees")[0].set("is_salary_withheld", 1)
            self.assertNotEqual(first, workflow.get_approval_digest(doc))
            second = workflow.get_approval_digest(doc)
            doc.set("department", "FINANCE")
            self.assertNotEqual(second, workflow.get_approval_digest(doc))

    def test_digest_changes_when_native_payroll_source_revision_changes(self) -> None:
        doc = self._doc()
        with (
            patch.object(workflow, "get_accounting_dimensions", return_value=[]),
            patch.object(
                workflow,
                "_payroll_source_revisions",
                side_effect=[
                    {"salary_structure_assignments": [{"name": "SSA-1", "modified": "first"}]},
                    {"salary_structure_assignments": [{"name": "SSA-1", "modified": "second"}]},
                ],
            ),
        ):
            self.assertNotEqual(workflow.get_approval_digest(doc), workflow.get_approval_digest(doc))

    def test_send_overwrites_maker_but_resubmit_preserves_it(self) -> None:
        send = self._doc()
        resubmit = self._doc(approval_maker_user="original@example.com")
        with patch.object(
            workflow,
            "authorize_workflow_field_write",
            return_value="current@example.com",
        ) as authorize:
            workflow.capture_maker_snapshot(send)
            self.assertEqual(send.get("approval_maker_user"), "current@example.com")
            authorize.assert_called_with(
                send,
                workflow.ROUTE.key,
                workflow.ROUTE.send_action,
                workflow.ROUTE.maker_roles,
            )

            workflow.capture_maker_snapshot(resubmit)
            self.assertEqual(resubmit.get("approval_maker_user"), "original@example.com")
            authorize.assert_called_with(
                resubmit,
                workflow.ROUTE.key,
                workflow.ROUTE.resubmit_action,
                workflow.ROUTE.maker_roles,
            )

    def test_approve_rejects_stale_digest_before_authorizing(self) -> None:
        doc = self._doc(
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_critical_digest="stale",
        )
        with (
            patch.object(workflow, "get_approval_digest", return_value="current"),
            patch.object(workflow, "authorize_approval_field_write") as authorize,
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.capture_authorization_snapshot(doc)
        authorize.assert_not_called()

    def test_unknown_transition_cannot_change_evidence(self) -> None:
        previous = self._doc(
            workflow_state=workflow.ROUTE.draft_state,
            approval_maker_user="maker@example.com",
        )
        doc = self._doc(
            workflow_state=workflow.ROUTE.draft_state,
            approval_maker_user="forged@example.com",
        )
        doc._doc_before_save = previous
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_workflow(doc)

    def test_review_consumes_exact_grant_and_blocks_authorizer_injection(self) -> None:
        previous = self._doc(
            workflow_state=workflow.ROUTE.pending_review_state,
            approval_maker_user="maker@example.com",
        )
        doc = self._doc(
            workflow_state=workflow.ROUTE.reviewed_state,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="signature",
        )
        doc._doc_before_save = previous
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.validate_workflow(doc)
        consume.assert_called_once_with(doc, workflow.ROUTE.key, workflow.ROUTE.review_action)

        doc.set("approval_authorized_user", "forged@example.com")
        with (
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "consume_approval_field_grant"),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_workflow(doc)

    def test_execute_validation_leaves_grant_for_before_submit(self) -> None:
        previous = self._doc(workflow_state=workflow.ROUTE.approved_state)
        doc = self._doc(workflow_state=workflow.ROUTE.submitted_state)
        doc._doc_before_save = previous
        with patch.object(workflow, "consume_approval_field_grant") as consume:
            workflow.validate_workflow(doc)
        consume.assert_not_called()

    def test_direct_submit_without_transition_grant_is_denied(self) -> None:
        doc = self._doc(workflow_state=workflow.ROUTE.submitted_state)
        with self.assertRaises(frappe.ValidationError):
            workflow.validate_before_submit(doc)

    def test_submit_rejects_actor_or_signed_snapshot_tampering(self) -> None:
        doc = self._doc(
            workflow_state=workflow.ROUTE.submitted_state,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="review-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-09-26 11:00:00",
            authorized_signature="approve-signature",
        )
        persisted = frappe._dict(doc.as_dict())
        persisted.workflow_state = workflow.ROUTE.approved_state
        persisted.checked_signature = "different-signature"
        with (
            patch.object(workflow, "consume_approval_field_grant"),
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "require_distinct_actors"),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

        persisted.checked_signature = doc.get("checked_signature")
        persisted.approval_reviewer_user = "other@example.com"
        with (
            patch.object(workflow, "consume_approval_field_grant"),
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(workflow, "require_distinct_actors"),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_same_user_actor_reuse_is_rechecked_at_submit(self) -> None:
        doc = self._doc(
            workflow_state=workflow.ROUTE.submitted_state,
            approval_maker_user="same@example.com",
            approval_reviewer_user="same@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="digest",
            checked_by="EMP-REVIEWER",
            checked_at="2026-09-26 10:00:00",
            checked_signature="review-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-09-26 11:00:00",
            authorized_signature="approve-signature",
        )
        persisted = frappe._dict(doc.as_dict())
        persisted.workflow_state = workflow.ROUTE.approved_state
        with (
            patch.object(workflow, "consume_approval_field_grant"),
            patch.object(workflow, "require_permission"),
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "get_approval_digest", return_value="digest"),
            patch.object(
                workflow,
                "require_distinct_actors",
                side_effect=frappe.ValidationError("same actor"),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_before_submit(doc)

    def test_return_and_reject_use_distinct_declared_actions(self) -> None:
        doc = self._doc(approval_maker_user="maker@example.com")
        with patch.object(workflow, "authorize_workflow_field_write") as authorize:
            workflow.clear_on_return(doc)
            authorize.assert_called_once_with(
                doc,
                workflow.ROUTE.key,
                workflow.ROUTE.return_action,
                workflow.ROUTE.reviewer_roles,
            )
            authorize.reset_mock()
            workflow.clear_on_reject(doc)
            authorize.assert_called_once_with(
                doc,
                workflow.ROUTE.key,
                workflow.ROUTE.reject_action,
                workflow.ROUTE.final_approver_roles,
            )

    def test_downstream_operations_require_submitted_approval_evidence(self) -> None:
        doc = self._doc(workflow_state=workflow.ROUTE.submitted_state)
        persisted = frappe._dict(
            {
                "docstatus": 1,
                "workflow_state": workflow.ROUTE.submitted_state,
                "approval_maker_user": "maker@example.com",
                "approval_reviewer_user": "reviewer@example.com",
                "approval_authorized_user": "approver@example.com",
                "approval_critical_digest": "digest",
                "checked_by": "EMP-REVIEWER",
                "checked_at": "2026-09-27 10:00:00",
                "checked_signature": "review-signature",
                "authorized_by": "EMP-APPROVER",
                "authorized_at": "2026-09-27 11:00:00",
                "authorized_signature": "approve-signature",
            }
        )
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "get_approval_digest", return_value="digest"),
        ):
            self.assertIs(workflow.validate_downstream_operation(doc), doc)

        persisted.workflow_state = workflow.ROUTE.approved_state
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_downstream_operation(doc)

    def test_native_operation_mixin_guards_then_delegates(self) -> None:
        payroll = _GuardedPayroll()
        with patch.object(workflow, "validate_downstream_operation") as validate:
            self.assertEqual(payroll.create_salary_slips(1), ("create", (1,), {}))
            self.assertEqual(payroll.submit_salary_slips(2), ("submit", (2,), {}))
            self.assertEqual(payroll.make_accrual_jv_entry(3), ("accrual", (3,), {}))
            self.assertEqual(payroll.make_bank_entry(4), ("bank", (4,), {}))
        self.assertEqual(validate.call_count, 4)
        self.assertEqual(validate.call_args_list[0].kwargs, {})
        self.assertEqual(validate.call_args_list[1].kwargs, {})
        self.assertEqual(validate.call_args_list[2].kwargs, {"require_current_digest": False})
        self.assertEqual(validate.call_args_list[3].kwargs, {"require_current_digest": False})
