# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import approval_controls
from connect_diagnostics_core.api.hrms import payroll_entry_workflow as workflow
from connect_diagnostics_core.api.hrms import payroll_output_review as output


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
    name = "PE-1"


class _NativePayrollAccrual:
    def make_journal_entry(
        self, *args: object, **kwargs: object
    ) -> tuple[tuple[object, ...], dict[str, object]]:
        return args, kwargs


class _DraftAccrualPayroll(workflow.PayrollEntryWorkflowMixin, _NativePayrollAccrual):
    name = "PE-1"


class TestPayrollEntryWorkflow(UnitTestCase):
    def test_additional_salary_selector_matches_native_recurring_and_date_rules(self) -> None:
        base = {
            "docstatus": 1,
            "disabled": 0,
            "type": "Earning",
            "is_recurring": 1,
            "from_date": "2026-08-01",
            "to_date": "2026-10-31",
            "payroll_date": None,
        }
        self.assertTrue(workflow._eligible_additional_salary(base, "2026-09-01", "2026-09-30"))
        self.assertFalse(
            workflow._eligible_additional_salary(
                {**base, "from_date": "2026-10-01"}, "2026-09-01", "2026-09-30"
            )
        )
        self.assertTrue(
            workflow._eligible_additional_salary(
                {**base, "is_recurring": 0, "payroll_date": "2026-09-30"},
                "2026-09-01",
                "2026-09-30",
            )
        )
        for change in ({"docstatus": 0}, {"disabled": 1}, {"type": "Other"}):
            with self.subTest(change=change):
                self.assertFalse(
                    workflow._eligible_additional_salary({**base, **change}, "2026-09-01", "2026-09-30")
                )

    def test_additional_salary_writer_locks_old_and_new_employee_in_order(self) -> None:
        doc = Document({"doctype": "Additional Salary", "name": "AS-1", "employee": "EMP-A"})
        with (
            patch.object(workflow.frappe.db, "exists", return_value=True),
            patch.object(workflow.frappe.db, "get_value", side_effect=["EMP-Z", "EMP-Z"]),
            patch.object(workflow, "_lock_employee_scope") as lock_scope,
        ):
            doc.set("employee", "EMP-A")
            workflow.guard_additional_salary_employee_scope(doc, "before_update")
        lock_scope.assert_called_once_with(["EMP-A", "EMP-Z"])

    def test_locked_input_sources_hash_settings_and_native_eligible_additional_salary(self) -> None:
        doc = self._doc()
        additional = frappe._dict(
            name="AS-1",
            employee="EMP-1",
            salary_component="Allowance",
            type="Earning",
            amount=10,
            docstatus=1,
            disabled=0,
            is_recurring=0,
            payroll_date="2026-09-15",
            overwrite_salary_structure_amount=0,
            deduct_full_tax_on_selected_payroll_date=0,
            ref_doctype=None,
            ref_docname=None,
        )
        with (
            patch.object(
                workflow, "_lock_employee_scope", return_value=[frappe._dict(name="EMP-1")]
            ) as lock_employees,
            patch.object(workflow.frappe.db, "get_values", return_value=[additional]) as get_values,
            patch.object(
                workflow,
                "_locked_payroll_settings",
                return_value=[
                    frappe._dict(field="process_payroll_accounting_entry_based_on_employee", value="0")
                ],
            ),
        ):
            sources = workflow.lock_payroll_input_sources(doc)
        lock_employees.assert_called_once_with(["EMP-1"])
        self.assertEqual(sources["additional_salaries"], [dict(additional)])
        self.assertEqual(len(sources["payroll_settings_digest"]), 64)
        self.assertEqual(get_values.call_args.kwargs["for_update"], True)

    def test_native_additional_salary_reader_must_match_locked_projection(self) -> None:
        doc = self._doc()
        row = {
            "name": "AS-1",
            "employee": "EMP-1",
            "salary_component": "Allowance",
            "type": "Earning",
            "amount": 10,
            "is_recurring": 0,
            "overwrite_salary_structure_amount": 0,
            "deduct_full_tax_on_selected_payroll_date": 0,
            "ref_doctype": None,
        }
        source = {
            **row,
            "docstatus": 1,
            "disabled": 0,
            "payroll_date": "2026-09-15",
            "from_date": None,
            "to_date": None,
            "ref_docname": None,
        }
        native = {
            "name": "AS-1",
            "component": "Allowance",
            "type": "Earning",
            "amount": 10,
            "is_recurring": 0,
            "overwrite": 0,
            "deduct_full_tax_on_selected_payroll_date": 0,
            "ref_doctype": None,
        }
        with (
            patch.object(
                workflow,
                "lock_payroll_input_sources",
                return_value={"additional_salaries": [source], "payroll_settings_digest": "settings"},
            ),
            patch(
                "hrms.payroll.doctype.additional_salary.additional_salary.get_additional_salaries",
                side_effect=lambda _employee, _start, _end, component_type: [native]
                if component_type == "earnings"
                else [],
            ),
            patch.object(workflow, "_verify_native_payroll_settings") as verify_settings,
        ):
            workflow.verify_native_payroll_input_readers(doc)
        verify_settings.assert_called_once_with("settings")
        with (
            patch.object(
                workflow,
                "lock_payroll_input_sources",
                return_value={"additional_salaries": [source], "payroll_settings_digest": "settings"},
            ),
            patch(
                "hrms.payroll.doctype.additional_salary.additional_salary.get_additional_salaries",
                return_value=[],
            ),
            patch.object(workflow, "_verify_native_payroll_settings"),
            self.assertRaisesRegex(frappe.ValidationError, "Additional Salary inputs changed"),
        ):
            workflow.verify_native_payroll_input_readers(doc)

    def test_accrual_generation_is_kept_as_draft(self) -> None:
        with output.native_operation("PE-1", "bank_regular"):
            args, kwargs = _DraftAccrualPayroll().make_journal_entry(submit_journal_entry=True)
        self.assertEqual(args, ())
        self.assertFalse(kwargs["submit_journal_entry"])

        with output.native_operation("PE-1", "bank_regular"):
            args, kwargs = _DraftAccrualPayroll().make_journal_entry(1, 2, 3, 4, 5, 6, True)
        self.assertEqual(args, (1, 2, 3, 4, 5, 6, False))
        self.assertEqual(kwargs, {})

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
        cases = (
            (
                workflow.ROUTE.pending_review_state,
                workflow.ROUTE.returned_state,
                workflow.clear_on_return,
                workflow.ROUTE.return_action,
                workflow.ROUTE.reviewer_roles,
            ),
            (
                workflow.ROUTE.reviewed_state,
                workflow.ROUTE.returned_state,
                workflow.clear_on_return,
                workflow.ROUTE.return_action,
                workflow.ROUTE.final_approver_roles,
            ),
            (
                workflow.ROUTE.reviewed_state,
                "Payroll Entry Rejected",
                workflow.clear_on_reject,
                workflow.ROUTE.reject_action,
                workflow.ROUTE.final_approver_roles,
            ),
        )
        for source, target, callback, action, roles in cases:
            with self.subTest(source=source, target=target):
                doc = self._doc(workflow_state=target, approval_maker_user="maker@example.com")
                persisted = frappe._dict(docstatus=0, workflow_state=source)
                with (
                    patch.object(workflow.frappe.db, "get_value", return_value=persisted),
                    patch.object(workflow, "authorize_workflow_field_write") as authorize,
                ):
                    callback(doc)
                authorize.assert_called_once_with(doc, workflow.ROUTE.key, action, roles)
                self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")

    def test_return_and_reject_reject_invalid_locked_source_or_target(self) -> None:
        cases = (
            (workflow.clear_on_return, workflow.ROUTE.returned_state, workflow.ROUTE.draft_state),
            (workflow.clear_on_reject, "Payroll Entry Rejected", workflow.ROUTE.pending_review_state),
        )
        for callback, target, source in cases:
            with self.subTest(target=target, source=source):
                doc = self._doc(workflow_state=target)
                with (
                    patch.object(
                        workflow.frappe.db,
                        "get_value",
                        return_value=frappe._dict(docstatus=0, workflow_state=source),
                    ),
                    patch.object(workflow, "authorize_workflow_field_write") as authorize,
                    self.assertRaises(frappe.ValidationError),
                ):
                    callback(doc)
                authorize.assert_not_called()
        doc = self._doc(workflow_state=workflow.ROUTE.reviewed_state)
        with self.assertRaises(frappe.ValidationError):
            workflow.clear_on_return(doc)

    def test_return_and_reject_require_role_authorization(self) -> None:
        for callback, target, source in (
            (workflow.clear_on_return, workflow.ROUTE.returned_state, workflow.ROUTE.reviewed_state),
            (workflow.clear_on_reject, "Payroll Entry Rejected", workflow.ROUTE.reviewed_state),
        ):
            doc = self._doc(workflow_state=target)
            with (
                patch.object(
                    workflow.frappe.db,
                    "get_value",
                    return_value=frappe._dict(docstatus=0, workflow_state=source),
                ),
                patch.object(
                    workflow,
                    "authorize_workflow_field_write",
                    side_effect=frappe.PermissionError("wrong actor"),
                ),
                self.assertRaises(frappe.PermissionError),
            ):
                callback(doc)

    def test_return_reject_grants_are_one_use_and_evidence_is_cleared(self) -> None:
        for source, target, action in (
            (workflow.ROUTE.reviewed_state, workflow.ROUTE.returned_state, workflow.ROUTE.return_action),
            (workflow.ROUTE.reviewed_state, "Payroll Entry Rejected", workflow.ROUTE.reject_action),
        ):
            with self.subTest(target=target):
                previous = self._doc(
                    workflow_state=source,
                    approval_maker_user="maker@example.com",
                    approval_reviewer_user="reviewer@example.com",
                    approval_critical_digest="digest",
                    checked_by="EMP-REVIEWER",
                    checked_at="2026-09-26 10:00:00",
                    checked_signature="signature",
                )
                doc = deepcopy(previous)
                doc.set("workflow_state", target)
                doc._doc_before_save = previous
                with (
                    patch.object(
                        workflow.frappe.db,
                        "get_value",
                        return_value=frappe._dict(docstatus=0, workflow_state=source),
                    ),
                    patch.object(workflow, "authorize_workflow_field_write") as authorize,
                    patch.object(doc.meta, "has_field", return_value=True),
                ):
                    authorize.side_effect = lambda doc, route, action, roles: (
                        approval_controls._mint_approval_field_grant(doc, route, action)
                    )
                    workflow.clear_on_return(
                        doc
                    ) if action == workflow.ROUTE.return_action else workflow.clear_on_reject(doc)
                self.assertEqual(doc.get("approval_maker_user"), "maker@example.com")
                self.assertFalse(doc.get("approval_reviewer_user"))
                self.assertFalse(doc.get("checked_signature"))
                workflow.validate_workflow(doc)
                with self.assertRaises(frappe.ValidationError):
                    workflow.validate_workflow(doc)

    def test_direct_return_or_reject_without_callback_grant_is_denied(self) -> None:
        for target in (workflow.ROUTE.returned_state, "Payroll Entry Rejected"):
            with self.subTest(target=target):
                previous = self._doc(workflow_state=workflow.ROUTE.reviewed_state)
                doc = self._doc(workflow_state=target)
                doc._doc_before_save = previous
                with self.assertRaises(frappe.ValidationError):
                    workflow.validate_workflow(doc)

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
            patch.object(workflow, "resolve_user", side_effect=lambda value: value),
        ):
            self.assertIs(workflow.validate_downstream_operation(doc), doc)

        persisted.workflow_state = workflow.ROUTE.approved_state
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaises(frappe.ValidationError),
        ):
            workflow.validate_downstream_operation(doc)

    def test_native_operation_mixin_routes_through_reviewed_adapter(self) -> None:
        payroll = _GuardedPayroll()
        with (
            patch.object(output, "create_salary_slips", return_value="created") as create,
            patch.object(output, "submit_salary_slips", return_value="submitted") as submit,
        ):
            self.assertEqual(payroll.create_salary_slips(), "created")
            self.assertEqual(payroll.submit_salary_slips(), "submitted")
        create.assert_called_once_with(payroll)
        submit.assert_called_once_with(payroll)

        with self.assertRaises(frappe.PermissionError):
            _DraftAccrualPayroll().make_journal_entry(submit_journal_entry=True)

    def test_native_desk_methods_remain_whitelisted_after_override(self) -> None:
        for method in (
            workflow.PayrollEntryApprovalMixin.create_salary_slips,
            workflow.PayrollEntryApprovalMixin.submit_salary_slips,
            workflow.PayrollEntryApprovalMixin.make_bank_entry,
        ):
            frappe.is_whitelisted(method)

    def test_direct_submitted_output_state_change_requires_native_action_grant(self) -> None:
        previous = self._doc(workflow_state=output.SUBMITTED, docstatus=1)
        candidate = self._doc(workflow_state=output.REVIEWED, docstatus=1)
        candidate._doc_before_save = previous
        with self.assertRaisesRegex(frappe.ValidationError, "not authorized"):
            workflow.validate_before_update_after_submit(candidate)

    def test_direct_payroll_cancel_requires_native_action_grant(self) -> None:
        candidate = self._doc(workflow_state=output.CANCELLED, docstatus=2)
        with self.assertRaisesRegex(frappe.ValidationError, "not authorized"):
            workflow.validate_before_cancel(candidate)

    def test_output_reopen_clears_current_proof_and_increments_revision(self) -> None:
        pe = self._doc(
            output_reviewed_by="manager@example.com",
            output_reviewed_at="2026-10-02 10:00:00",
            output_review_signature="signature",
            output_review_digest="digest",
            output_review_version=output.VERSION,
            output_review_revision=3,
        )
        output.clear_output_review(pe)
        self.assertEqual(pe.get("output_review_revision"), 4)
        self.assertEqual(pe.get("output_review_version"), output.VERSION)
        for field in (field for field in output.OUTPUT_FIELDS[:-1] if field != "output_review_version"):
            self.assertFalse(pe.get(field), field)

    def test_output_review_dispatches_legacy_v1_and_unknown_versions(self) -> None:
        for version, expected_digest_check in ((None, False), ("", False), (output.VERSION, True)):
            with self.subTest(version=version):
                previous = self._doc(workflow_state=output.SUBMITTED, docstatus=1)
                previous.set("output_review_version", version)
                candidate = self._doc(workflow_state=output.REVIEWED, docstatus=1)
                candidate._doc_before_save = previous
                with (
                    patch.object(output, "locked_payroll_entry", return_value=previous),
                    patch.object(workflow, "validate_downstream_operation") as validate,
                    patch.object(
                        workflow,
                        "authorize_approval_field_write",
                        return_value=frappe._dict(user="hr@example.com"),
                    ),
                    patch.object(output, "current_roster", return_value=[]),
                    patch.object(output, "seal_output_review") as seal,
                ):
                    workflow.prepare_output_review(candidate)
                validate.assert_called_once_with(previous, require_current_digest=expected_digest_check)
                seal.assert_called_once_with(candidate, [], "hr@example.com")

        previous = self._doc(workflow_state=output.SUBMITTED, docstatus=1, output_review_version="future-v2")
        candidate = self._doc(workflow_state=output.REVIEWED, docstatus=1)
        with (
            patch.object(output, "locked_payroll_entry", return_value=previous),
            patch.object(workflow, "validate_downstream_operation") as validate,
            patch.object(workflow, "authorize_approval_field_write") as authorize,
            self.assertRaisesRegex(frappe.ValidationError, "version is unknown"),
        ):
            workflow.prepare_output_review(candidate)
        validate.assert_not_called()
        authorize.assert_not_called()

    def test_legacy_output_review_accepts_fully_submitted_roster(self) -> None:
        self._review_legacy_roster(("Submitted", "Submitted"))

    def test_legacy_output_review_accepts_complete_roster_with_withheld_slip(self) -> None:
        self._review_legacy_roster(("Submitted", "Withheld"))

    def test_legacy_output_review_accepts_complete_roster_with_submitted_and_draft_slips(self) -> None:
        self._review_legacy_roster(("Submitted", "Draft"), (1, 0))

    def _review_legacy_roster(self, statuses: tuple[str, ...], docstatuses: tuple[int, ...] = (1, 1)) -> None:
        pe = self._doc(
            docstatus=1,
            workflow_state=output.SUBMITTED,
            status="Submitted",
            salary_slips_created=1,
            payroll_frequency="Monthly",
            currency="THB",
            salary_slip_based_on_timesheet=0,
        )
        previous = deepcopy(pe)
        candidate = deepcopy(pe)
        candidate.set("workflow_state", output.REVIEWED)
        employees = [frappe._dict(idx=index, employee=f"EMP-{index}") for index in (1, 2)]
        rows = [
            frappe._dict(
                name=f"SS-{index}",
                employee=f"EMP-{index}",
                docstatus=docstatuses[index - 1],
                company="ACME",
                start_date="2026-09-01",
                end_date="2026-09-30",
                posting_date="2026-09-26",
                payroll_frequency="Monthly",
                currency="THB",
                salary_slip_based_on_timesheet=0,
            )
            for index in (1, 2)
        ]
        slips = [
            Document(
                {
                    "doctype": "Salary Slip",
                    "name": f"SS-{index}",
                    "employee": f"EMP-{index}",
                    "docstatus": docstatuses[index - 1],
                    "status": status,
                }
            )
            for index, status in enumerate(statuses, start=1)
        ]
        with (
            patch.object(output, "locked_payroll_entry", return_value=previous),
            patch.object(workflow, "validate_downstream_operation") as validate,
            patch.object(
                workflow,
                "authorize_approval_field_write",
                return_value=frappe._dict(user="hr@example.com"),
            ),
            patch.object(output, "_locked_rows", side_effect=[employees, rows, []]),
            patch.object(output, "_active_job", return_value=False),
            patch.object(output.frappe, "get_doc", side_effect=slips),
            patch.object(output, "seal_output_review") as seal,
        ):
            workflow.prepare_output_review(candidate)
        validate.assert_called_once_with(previous, require_current_digest=False)
        seal.assert_called_once_with(candidate, slips, "hr@example.com")

    def test_incomplete_legacy_roster_is_rejected_before_output_seal(self) -> None:
        pe = self._doc(
            docstatus=1,
            workflow_state=output.SUBMITTED,
            status="Submitted",
            salary_slips_created=1,
            payroll_frequency="Monthly",
            currency="THB",
            salary_slip_based_on_timesheet=0,
        )
        previous = deepcopy(pe)
        candidate = deepcopy(pe)
        candidate.set("workflow_state", output.REVIEWED)
        employees = [frappe._dict(idx=1, employee="EMP-1"), frappe._dict(idx=2, employee="EMP-2")]
        incomplete_rows = [
            frappe._dict(
                name="SS-1",
                employee="EMP-1",
                docstatus=1,
                company="ACME",
                start_date="2026-09-01",
                end_date="2026-09-30",
                posting_date="2026-09-26",
                payroll_frequency="Monthly",
                currency="THB",
                salary_slip_based_on_timesheet=0,
            )
        ]
        with (
            patch.object(output, "locked_payroll_entry", return_value=previous),
            patch.object(workflow, "validate_downstream_operation"),
            patch.object(
                workflow,
                "authorize_approval_field_write",
                return_value=frappe._dict(user="hr@example.com"),
            ),
            patch.object(output, "_locked_rows", side_effect=[employees, incomplete_rows]),
            patch.object(output, "_active_job", return_value=False),
            patch.object(output, "seal_output_review") as seal,
            self.assertRaisesRegex(frappe.PermissionError, "roster does not match"),
        ):
            workflow.prepare_output_review(candidate)
        seal.assert_not_called()

    def test_eligible_legacy_review_uses_persisted_approval_without_rewriting_it(self) -> None:
        doc = self._doc(workflow_state=output.SUBMITTED)
        persisted = frappe._dict(
            docstatus=1,
            workflow_state=output.SUBMITTED,
            approval_maker_user="maker@example.com",
            approval_reviewer_user="reviewer@example.com",
            approval_authorized_user="approver@example.com",
            approval_critical_digest="historical-sha256",
            checked_by="EMP-REVIEWER",
            checked_at="2026-01-01 10:00:00",
            checked_signature="original-check-signature",
            authorized_by="EMP-APPROVER",
            authorized_at="2026-01-01 11:00:00",
            authorized_signature="original-approval-signature",
        )
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            patch.object(workflow, "get_approval_digest", return_value="current-sha256"),
            patch.object(workflow, "resolve_user", side_effect=lambda user: user),
        ):
            workflow.validate_downstream_operation(doc, require_current_digest=False)
        self.assertEqual(persisted.approval_critical_digest, "historical-sha256")

        persisted.checked_signature = ""
        with (
            patch.object(workflow, "_persisted_approval", return_value=persisted),
            self.assertRaisesRegex(frappe.ValidationError, "complete review and approval evidence"),
        ):
            workflow.validate_downstream_operation(doc, require_current_digest=False)

    def test_output_reopen_clears_stale_seal_under_authorized_transition(self) -> None:
        previous = self._doc(
            workflow_state=output.REVIEWED,
            docstatus=1,
            output_review_version=output.VERSION,
            output_review_digest="stale-digest",
            output_review_signature="stale-signature",
            output_review_revision=8,
        )
        candidate = deepcopy(previous)
        candidate.set("workflow_state", output.SUBMITTED)
        candidate._doc_before_save = previous
        with (
            patch.object(output, "locked_payroll_entry", return_value=previous),
            patch.object(workflow, "validate_downstream_operation"),
            patch.object(workflow, "authorize_workflow_field_write") as authorize,
            patch.object(output, "require_output_review") as require_review,
            patch.object(workflow, "consume_approval_field_grant") as consume,
        ):
            workflow.prepare_output_reopen(candidate)
            workflow.validate_before_update_after_submit(candidate)
        authorize.assert_called_once_with(
            candidate, workflow.ROUTE.key, "Reopen Payroll Output", ("HR Manager",)
        )
        consume.assert_called_once_with(candidate, workflow.ROUTE.key, "Reopen Payroll Output")
        require_review.assert_not_called()
        self.assertEqual(candidate.get("output_review_revision"), 9)
        self.assertEqual(candidate.get("output_review_version"), output.VERSION)
        self.assertTrue(
            all(
                not candidate.get(field)
                for field in output.OUTPUT_FIELDS[:-1]
                if field != "output_review_version"
            )
        )

        reviewed = deepcopy(candidate)
        reviewed.set("workflow_state", output.REVIEWED)
        with (
            patch.object(output, "locked_payroll_entry", return_value=candidate),
            patch.object(workflow, "validate_downstream_operation") as validate,
            patch.object(
                workflow,
                "authorize_approval_field_write",
                return_value=frappe._dict(user="hr@example.com"),
            ),
            patch.object(output, "current_roster", return_value=[]),
            patch.object(output, "seal_output_review") as seal,
        ):
            workflow.prepare_output_review(reviewed)
        validate.assert_called_once_with(candidate, require_current_digest=True)
        seal.assert_called_once_with(reviewed, [], "hr@example.com")
