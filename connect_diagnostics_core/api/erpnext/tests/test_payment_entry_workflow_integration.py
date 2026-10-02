# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Live configuration checks for the native Payment Entry approval route."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from hashlib import sha256
from typing import TypeVar, cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry, get_payment_entry
from erpnext.accounts.doctype.payment_reconciliation.payment_reconciliation import PaymentReconciliation
from frappe.client import save as client_save
from frappe.client import set_value as client_set_value
from frappe.model.document import clear_document_cache
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate
from frappe.utils.nestedset import get_root_of

from connect_diagnostics_core.api.erpnext import payment_entry_workflow, payment_reconciliation
from connect_diagnostics_core.api.erpnext.payment_entry import validate_reference_dimensions
from connect_diagnostics_core.api.frappe.approval_routes import get_route
from connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5 import preflight

APPROVAL_FIELDS = (
    "approval_digest",
    "approval_maker_user",
    "approval_maker_at",
    "approval_checker_user",
    "approval_checker_at",
    "approval_approver_user",
    "approval_approver_at",
    "approval_submit_actor",
    "approval_cancel_actor",
    "checked_by",
    "checked_at",
    "checked_signature",
    "authorized_by",
    "authorized_at",
    "authorized_signature",
)
T = TypeVar("T")


def field_fingerprints(doc: PaymentEntry) -> dict[str, tuple[str, str]]:
    """Keep field paths, value types, and opaque digests for mutation comparison."""
    fields: dict[str, tuple[str, str]] = {}
    for fieldname, value in doc.as_dict().items():
        if not isinstance(value, list):
            fields[fieldname] = (type(value).__name__, sha256(repr(value).encode()).hexdigest())
            continue
        for index, child in enumerate(value, start=1):
            if not isinstance(child, dict):
                fields[f"{fieldname}[{index}]"] = (
                    type(child).__name__,
                    sha256(repr(child).encode()).hexdigest(),
                )
                continue
            for child_fieldname, child_value in child.items():
                path = f"{fieldname}[{index}].{child_fieldname}"
                fields[path] = (
                    type(child_value).__name__,
                    sha256(repr(child_value).encode()).hexdigest(),
                )
    return fields


class TestPaymentEntryWorkflowIntegration(IntegrationTestCase):
    def test_native_pay_reconciliation_preserves_approved_funds(self) -> None:
        self._native_matching_handoff("Pay")

    def test_native_receive_reconciliation_preserves_approved_funds(self) -> None:
        self._native_matching_handoff("Receive")

    def _posted_unallocated_payment(
        self, payment_type: str, *, dimension_values: dict[str, str] | None = None
    ) -> tuple[PaymentEntry, str, str]:
        preflight()
        template = self._template(payment_type)
        reference = template.references[0]
        invoice_type, invoice = str(reference.reference_doctype), str(reference.reference_name)
        maker = self._actor("match_maker", ("Accounts User",))
        checker = self._actor("match_checker", ("Accounts User", "Accounts Manager"))
        final = self._actor("match_final", ("Accounts User", "C-Level Approver"))
        frappe.set_user(maker)
        payment = self._clone(template)
        payment.set("references", [])
        payment.update(dimension_values or {})
        payment.set_amounts()
        payment.insert()
        name = str(payment.name)
        route = get_route("payment_entry")
        for user, action in (
            (maker, route.send_action),
            (checker, route.review_action),
            (final, route.approve_action),
            (checker, route.execute_action),
        ):
            frappe.set_user(user)
            payment = cast(PaymentEntry, apply_workflow(frappe.get_doc("Payment Entry", name), action))
        payment.reload()
        self.assertEqual(payment.docstatus, 1)
        self.assertFalse(payment.references)
        self.assertAlmostEqual(payment.unallocated_amount, 100)
        return payment, invoice_type, invoice

    def _matching_tool(
        self, payment: PaymentEntry, invoice_type: str, invoice: str, amount: float
    ) -> PaymentReconciliation:
        tool = cast(PaymentReconciliation, frappe.get_doc("Payment Reconciliation"))
        tool.company = payment.company
        self.assertTrue(payment.party_type)
        self.assertTrue(payment.party)
        tool.party_type = str(payment.party_type)
        tool.party = str(payment.party)
        tool.receivable_payable_account = (
            payment.paid_to if payment.payment_type == "Pay" else payment.paid_from
        )
        tool.payment_name = payment.name
        tool.invoice_name = invoice
        tool.set("department", self._fixture_department)
        tool.get_unreconciled_entries()
        invoices = [
            row.as_dict()
            for row in tool.invoices
            if row.invoice_number == invoice and row.invoice_type == invoice_type
        ]
        payments = [
            row.as_dict()
            for row in tool.payments
            if row.reference_type == "Payment Entry" and row.reference_name == payment.name
        ]
        self.assertEqual(len(invoices), 1)
        self.assertEqual(len(payments), 1)
        tool.allocate_entries(frappe._dict(invoices=invoices, payments=payments))
        self.assertEqual(len(tool.allocation), 1)
        tool.allocation[0].allocated_amount = amount
        return tool

    def _payment_gl(self, name: str) -> list[dict[str, object]]:
        return frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Payment Entry", "voucher_no": name},
            fields=[
                "name",
                "account",
                "party_type",
                "party",
                "debit",
                "credit",
                "debit_in_account_currency",
                "credit_in_account_currency",
                "department",
                "is_cancelled",
            ],
            order_by="name",
        )

    def _native_matching_handoff(self, payment_type: str) -> None:
        payment, invoice_type, invoice = self._posted_unallocated_payment(payment_type)
        evidence = {field: payment.get(field) for field in APPROVAL_FIELDS}
        ledger = self._payment_gl(str(payment.name))
        self.assertTrue(ledger)
        original_balance = float(frappe.db.get_value(invoice_type, invoice, "outstanding_amount"))
        total = 0
        for amount in (30, 40):
            tool = self._matching_tool(payment, invoice_type, invoice, amount)
            tool.reconcile()
            payment.reload()
            total += amount
            self.assertEqual({field: payment.get(field) for field in APPROVAL_FIELDS}, evidence)
            self.assertEqual(self._payment_gl(str(payment.name)), ledger)
            self.assertEqual(payment.docstatus, 1)
            self.assertEqual(payment.get("workflow_state"), get_route("payment_entry").submitted_state)
            self.assertAlmostEqual(payment.total_allocated_amount, total)
            self.assertAlmostEqual(payment.unallocated_amount, 100 - total)
            self.assertAlmostEqual(
                float(frappe.db.get_value(invoice_type, invoice, "outstanding_amount")),
                original_balance - total,
            )
            self.assertAlmostEqual(sum(float(row.allocated_amount) for row in payment.references), total)
            self.assertTrue(
                frappe.db.exists(
                    "Payment Ledger Entry",
                    {
                        "voucher_type": "Payment Entry",
                        "voucher_no": payment.name,
                        "against_voucher_type": invoice_type,
                        "against_voucher_no": invoice,
                        "delinked": 0,
                    },
                )
            )
            retained_names = [row.name for row in payment.references]

            def rename_reference() -> object:
                candidate = frappe.get_doc("Payment Entry", payment.name)
                candidate.references[0].name = f"_Test PE Forged Row {self._suffix}"
                candidate.flags.ignore_validate_update_after_submit = True
                return candidate.save()

            self._assert_denied(rename_reference)
            payment.reload()
            self.assertEqual([row.name for row in payment.references], retained_names)
        self.assertNotEqual(payment_entry_workflow.get_approval_digest(payment), evidence["approval_digest"])
        self.assertGreaterEqual(
            frappe.db.count(
                "Comment",
                {
                    "reference_doctype": "Payment Entry",
                    "reference_name": payment.name,
                    "comment_type": "Info",
                },
            ),
            2,
        )
        cancelled = cast(PaymentEntry, apply_workflow(payment, "Cancel Payment Entry"))
        self.assertEqual(cancelled.docstatus, 2)
        self.assertAlmostEqual(
            float(frappe.db.get_value(invoice_type, invoice, "outstanding_amount")), original_balance
        )
        self.assertFalse(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment.name, "is_cancelled": 0}
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Ledger Entry",
                {"voucher_type": "Payment Entry", "voucher_no": payment.name, "delinked": 0},
            )
        )

    def test_native_matching_rejects_raw_references_and_invalid_allocations(self) -> None:
        payment, invoice_type, invoice = self._posted_unallocated_payment("Receive")
        name = str(payment.name)
        before = self._payment_gl(name)
        outstanding = frappe.db.get_value(invoice_type, invoice, "outstanding_amount")
        ledger = frappe.get_all(
            "Payment Ledger Entry",
            filters={"voucher_type": "Payment Entry", "voucher_no": name},
            fields=["name", "amount", "against_voucher_type", "against_voucher_no", "delinked"],
            order_by="name",
        )

        def raw_reference(*, api: bool) -> object:
            candidate = cast(PaymentEntry, frappe.get_doc("Payment Entry", name))
            candidate.append(
                "references",
                {"reference_doctype": invoice_type, "reference_name": invoice, "allocated_amount": 10},
            )
            candidate.flags.ignore_validate_update_after_submit = True
            candidate.flags.ignore_reposting_on_reconciliation = True
            if api:
                return client_save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        for api in (False, True):
            self._assert_denied(lambda api=api: raw_reference(api=api))
        for amount in (101, -1):
            tool = self._matching_tool(payment, invoice_type, invoice, amount)
            self._assert_denied(tool.reconcile_allocations)
        for reference_type in ("Journal Entry", "Sales Invoice"):
            tool = self._matching_tool(payment, invoice_type, invoice, 10)
            mixed = tool.allocation[0].as_dict()
            mixed.pop("name", None)
            mixed.update(reference_type=reference_type, reference_name=invoice)
            tool.append("allocation", mixed)
            self._assert_denied(tool.reconcile_allocations)
        tool = self._matching_tool(payment, invoice_type, invoice, 10)
        tool.party = "_Test Customer USD"
        self._assert_denied(tool.reconcile_allocations)
        tool = self._matching_tool(payment, invoice_type, invoice, 10)
        self._assert_denied(lambda: tool.reconcile_allocations(skip_ref_details_update_for_pe=True))
        tool = self._matching_tool(payment, invoice_type, invoice, 10)
        native_reconcile = PaymentReconciliation.reconcile_allocations

        def fail_after_native(
            source: PaymentReconciliation, skip_ref_details_update_for_pe: bool = False
        ) -> None:
            native_reconcile(source, skip_ref_details_update_for_pe)
            raise RuntimeError("Test failure after native payment matching effects")

        with patch.object(PaymentReconciliation, "reconcile_allocations", fail_after_native):
            self._assert_denied(tool.reconcile_allocations, error=RuntimeError)
        self.assertIsNone(payment_reconciliation._context())
        tool = self._matching_tool(payment, invoice_type, invoice, 10)
        actor = frappe.session.user
        frappe.set_user("Administrator")
        other_department = frappe.get_doc(
            {
                "doctype": "Department",
                "department_name": f"_Test PE Matching Scope {self._suffix}",
                "company": "_Test Company",
                "parent_department": get_root_of("Department"),
            }
        ).insert()
        restriction = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": actor,
                "allow": "Department",
                "for_value": other_department.name,
                "apply_to_all_doctypes": 1,
            }
        ).insert()
        frappe.clear_cache(user=actor)
        frappe.set_user(actor)
        try:
            self._assert_denied(tool.reconcile_allocations, error=frappe.PermissionError)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("User Permission", restriction.name)
            frappe.clear_cache(user=actor)
            frappe.set_user(actor)
        self.assertEqual(self._payment_gl(name), before)
        self.assertEqual(frappe.db.get_value(invoice_type, invoice, "outstanding_amount"), outstanding)
        self.assertEqual(
            frappe.get_all(
                "Payment Ledger Entry",
                filters={"voucher_type": "Payment Entry", "voucher_no": name},
                fields=["name", "amount", "against_voucher_type", "against_voucher_no", "delinked"],
                order_by="name",
            ),
            ledger,
        )
        payment.reload()
        self.assertFalse(payment.references)
        self.assertAlmostEqual(payment.unallocated_amount, 100)

    def test_native_matching_preserves_cost_center_and_project(self) -> None:
        projects = [
            frappe.get_doc(
                {
                    "doctype": "Project",
                    "project_name": f"_Test PE Project {index} {self._suffix}",
                    "company": "_Test Company",
                }
            )
            .insert()
            .name
            for index in (1, 2)
        ]
        payment, invoice_type, _invoice = self._posted_unallocated_payment(
            "Receive",
            dimension_values={"project": projects[0], "cost_center": "_Test Cost Center - _TC"},
        )
        self.assertEqual(payment.cost_center, "_Test Cost Center - _TC")
        actor = frappe.session.user
        frappe.set_user("Administrator")
        other_cost_center = (
            frappe.get_doc(
                {
                    "doctype": "Cost Center",
                    "cost_center_name": f"_Test PE Other Cost Center {self._suffix}",
                    "company": "_Test Company",
                    "parent_cost_center": frappe.db.get_value(
                        "Cost Center", {"company": "_Test Company", "is_group": 1}, "name"
                    ),
                }
            )
            .insert()
            .name
        )
        invoice_names = [
            self._receive_invoice(dimension_values=values)
            for values in (
                {"project": projects[1], "cost_center": str(payment.cost_center)},
                {"project": projects[0], "cost_center": other_cost_center},
                {"project": projects[0], "cost_center": str(payment.cost_center)},
            )
        ]
        frappe.set_user(actor)
        evidence = {field: payment.get(field) for field in APPROVAL_FIELDS}
        before_gl = self._payment_gl(str(payment.name))
        for invoice in invoice_names[:2]:
            outstanding = frappe.db.get_value(invoice_type, invoice, "outstanding_amount")
            tool = self._matching_tool(payment, invoice_type, invoice, 10)
            self._assert_denied(tool.reconcile_allocations)
            self.assertEqual(frappe.db.get_value(invoice_type, invoice, "outstanding_amount"), outstanding)
            self.assertEqual(self._payment_gl(str(payment.name)), before_gl)
            payment.reload()
            self.assertFalse(payment.references)
        matching_invoice = invoice_names[2]
        tool = self._matching_tool(payment, invoice_type, matching_invoice, 10)
        tool.reconcile()
        payment.reload()
        self.assertEqual(payment.project, projects[0])
        self.assertEqual({field: payment.get(field) for field in APPROVAL_FIELDS}, evidence)
        self.assertEqual(self._payment_gl(str(payment.name)), before_gl)
        self.assertAlmostEqual(payment.total_allocated_amount, 10)
        self.assertAlmostEqual(
            float(frappe.db.get_value(invoice_type, matching_invoice, "outstanding_amount")), 90
        )
        self.assertEqual(apply_workflow(payment, "Cancel Payment Entry").docstatus, 2)
        self.assertAlmostEqual(
            float(frappe.db.get_value(invoice_type, matching_invoice, "outstanding_amount")), 100
        )

    def test_canonical_pay_handoff_posts_and_reverses_native_ledgers(self) -> None:
        self._canonical_handoff("Pay")

    def test_canonical_receive_handoff_posts_and_reverses_native_ledgers(self) -> None:
        self._canonical_handoff("Receive")

    def test_legacy_submitted_digest_can_cancel_without_reapproval(self) -> None:
        self._canonical_handoff("Receive", legacy=True)

    def test_legacy_approved_digest_requires_return_and_fresh_review(self) -> None:
        preflight()
        template = self._template("Receive")
        maker = self._actor("legacy_maker", ("Accounts User",))
        checker = self._actor("legacy_checker", ("Accounts User", "Accounts Manager"))
        approver = self._actor("legacy_final", ("Accounts User", "C-Level Approver"))
        route = get_route("payment_entry")
        frappe.set_user(maker)
        doc = self._clone(template).insert()
        name = str(doc.name)

        def action(user: str, command: str) -> PaymentEntry:
            frappe.set_user(user)
            return cast(PaymentEntry, apply_workflow(frappe.get_doc("Payment Entry", name), command))

        with patch.object(payment_entry_workflow, "DIGEST_VERSION", "payment-entry-approval-v1"):
            action(maker, route.send_action)
            action(checker, route.review_action)
            approved = action(approver, route.approve_action)
        self.assertTrue(str(approved.get("approval_digest")).startswith("payment-entry-approval-v1:"))
        self._assert_denied(lambda: action(checker, route.execute_action))
        self.assertEqual(frappe.db.get_value("Payment Entry", name, "docstatus"), 0)
        action(approver, route.return_action)
        action(maker, route.resubmit_action)
        action(checker, route.review_action)
        approved = action(approver, route.approve_action)
        self.assertTrue(str(approved.get("approval_digest")).startswith("payment-entry-approval-v2:"))
        posted = action(checker, route.execute_action)
        self.assertEqual(posted.docstatus, 1)
        self.assertTrue(frappe.db.exists("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": name}))
        self.assertEqual(action(checker, "Cancel Payment Entry").docstatus, 2)

    def _assert_denied(
        self, callback: Callable[[], object], *, error: type[Exception] = frappe.ValidationError
    ) -> None:
        savepoint = f"pe_denial_{uuid4().hex}"
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        old_grants = list(grants) if grants is not None else None
        frappe.db.savepoint(savepoint)
        try:
            with self.assertRaises(error):
                callback()
        finally:
            frappe.db.rollback(save_point=savepoint)
            if old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = old_grants
            clear_document_cache("Payment Entry")

    def test_canonical_review_protects_maker_signatures_and_posting_inputs(self) -> None:
        preflight()
        template = self._template("Pay")
        alternate_department = (
            frappe.get_doc(
                {
                    "doctype": "Department",
                    "department_name": f"_Test PE Changed Dimension {self._suffix}",
                    "company": "_Test Company",
                    "parent_department": get_root_of("Department"),
                }
            )
            .insert()
            .name
        )
        maker = self._actor("guard_maker", ("Accounts User", "Accounts Manager", "C-Level Approver"))
        checker = self._actor("guard_checker", ("Accounts User", "Accounts Manager", "C-Level Approver"))
        approver = self._actor("guard_final", ("Accounts User", "C-Level Approver"))
        replacement = self._actor("guard_replacement", ("Accounts User",))
        route = get_route("payment_entry")
        frappe.set_user(maker)
        doc = self._clone(template).insert()
        name = str(doc.name)

        def action(user: str, command: str) -> PaymentEntry:
            frappe.set_user(user)
            return cast(PaymentEntry, apply_workflow(frappe.get_doc("Payment Entry", name), command))

        self._assert_denied(lambda: action(replacement, route.send_action))
        action(maker, route.send_action)
        self._assert_denied(lambda: action(maker, route.review_action))
        self._assert_denied(lambda: action(approver, route.review_action))
        reviewed = action(checker, route.review_action)
        maker_at = reviewed.get("approval_maker_at")
        self._assert_denied(lambda: action(maker, route.approve_action))
        self._assert_denied(lambda: action(checker, route.approve_action))

        def mutate(field: str) -> object:
            frappe.set_user(checker)
            candidate = frappe.get_doc("Payment Entry", name)
            if field == "references":
                candidate.references[0].allocated_amount -= 1
            elif field == "paid_amount":
                candidate.set(field, candidate.get(field) + 1)
            elif field == "paid_to":
                candidate.set(field, "Cash - _TC")
            elif field == "department":
                candidate.set(field, alternate_department)
            elif field in {"approval_checker_user", "approval_maker_user"}:
                candidate.set(field, replacement)
            else:
                candidate.set(field, "forged")
            return candidate.save()

        for field in (
            "reference_no",
            "paid_amount",
            "paid_to",
            "references",
            "department",
            "checked_signature",
            "approval_checker_user",
            "approval_maker_user",
        ):
            with self.subTest(field=field):
                self._assert_denied(lambda: mutate(field))
        returned = action(approver, route.return_action)
        self.assertEqual(returned.get("approval_maker_user"), maker)
        self.assertEqual(returned.get("approval_maker_at"), maker_at)
        self.assertFalse(returned.get("checked_signature"))
        self._assert_denied(lambda: action(replacement, route.resubmit_action))
        resubmitted = action(maker, route.resubmit_action)
        self.assertEqual(resubmitted.get("approval_maker_at"), maker_at)
        self._assert_denied(lambda: action(maker, route.review_action))
        action(checker, route.review_action)
        rejected = action(approver, route.reject_action)
        self.assertEqual(rejected.get("approval_maker_user"), maker)
        self.assertEqual(rejected.get("approval_maker_at"), maker_at)
        self.assertFalse(rejected.get("checked_signature"))
        self.assertFalse(rejected.get("authorized_signature"))
        self.assertEqual(rejected.docstatus, 0)
        for ledger in ("GL Entry", "Payment Ledger Entry"):
            self.assertFalse(frappe.db.exists(ledger, {"voucher_type": "Payment Entry", "voucher_no": name}))

    def _canonical_handoff(self, payment_type: str, *, legacy: bool = False) -> None:
        preflight()
        template = self._template(payment_type)
        actors = {
            "maker": self._actor("pe_maker", ("Accounts User",)),
            "checker": self._actor("pe_checker", ("Accounts User", "Accounts Manager")),
            "approver": self._actor("pe_approver", ("Accounts User", "C-Level Approver")),
        }
        route = get_route("payment_entry")
        balances = {
            (row.reference_doctype, row.reference_name): float(
                frappe.db.get_value(row.reference_doctype, row.reference_name, "outstanding_amount")
            )
            for row in template.references
        }
        allocations = {
            (row.reference_doctype, row.reference_name): float(row.allocated_amount)
            for row in template.references
        }
        frappe.set_user(actors["maker"])
        doc = self._clone(template).insert()
        name = str(doc.name)
        self.assertEqual(doc.get("workflow_state"), route.draft_state)
        frappe.set_user(actors["checker"])
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc("Payment Entry", name).submit()
        generation = (
            patch.object(payment_entry_workflow, "DIGEST_VERSION", "payment-entry-approval-v1")
            if legacy
            else nullcontext()
        )
        with generation:
            for actor, action in (
                ("maker", route.send_action),
                ("checker", route.review_action),
                ("approver", route.approve_action),
                ("checker", route.execute_action),
            ):
                frappe.set_user(actors[actor])
                if action == route.execute_action:

                    def spoof_submitted_state(*, api: bool) -> object:
                        candidate = frappe.get_doc("Payment Entry", name)
                        candidate.set("workflow_state", route.submitted_state)
                        if api:
                            return client_save(frappe.as_json(candidate.as_dict()))
                        return candidate.save()

                    self._assert_denied(lambda: spoof_submitted_state(api=False))
                    self._assert_denied(lambda: spoof_submitted_state(api=True))
                    self._assert_denied(
                        lambda: client_set_value(
                            "Payment Entry", name, "workflow_state", route.submitted_state
                        )
                    )
                    self.assertEqual(
                        frappe.db.get_value("Payment Entry", name, "workflow_state"), route.approved_state
                    )
                    self.assertEqual(frappe.db.get_value("Payment Entry", name, "docstatus"), 0)
                    self.assertFalse(frappe.db.get_value("Payment Entry", name, "approval_submit_actor"))
                    for ledger in ("GL Entry", "Payment Ledger Entry"):
                        self.assertFalse(
                            frappe.db.exists(ledger, {"voucher_type": "Payment Entry", "voucher_no": name})
                        )
                doc = cast(PaymentEntry, apply_workflow(frappe.get_doc("Payment Entry", name), action))
                if action == route.review_action:
                    doc.reload()
                    self.assertEqual(
                        payment_entry_workflow.get_approval_digest(doc), doc.get("approval_digest")
                    )
        if legacy:
            self.assertTrue(str(doc.get("approval_digest")).startswith("payment-entry-approval-v1:"))
            self.assertNotEqual(payment_entry_workflow.get_approval_digest(doc), doc.get("approval_digest"))
        doc.reload()
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.get("workflow_state"), route.submitted_state)
        for field, actor in (
            ("approval_maker_user", "maker"),
            ("approval_checker_user", "checker"),
            ("approval_approver_user", "approver"),
            ("approval_submit_actor", "checker"),
        ):
            self.assertEqual(doc.get(field), actors[actor])
        for prefix, actor in (("checked", "checker"), ("authorized", "approver")):
            employee = frappe.db.get_value("Employee", {"user_id": actors[actor]}, "name")
            self.assertEqual(doc.get(f"{prefix}_by"), employee)
            self.assertTrue(doc.get(f"{prefix}_at"))
            self.assertEqual(doc.get(f"{prefix}_signature"), "data:image/png;base64,dGVzdA==")
        for ledger in ("GL Entry", "Payment Ledger Entry"):
            self.assertTrue(frappe.db.exists(ledger, {"voucher_type": "Payment Entry", "voucher_no": name}))
        for (doctype, invoice), balance in balances.items():
            self.assertAlmostEqual(
                float(frappe.db.get_value(doctype, invoice, "outstanding_amount")),
                balance - allocations[(doctype, invoice)],
            )
        frappe.set_user(actors["checker"])
        self._assert_denied(lambda: frappe.get_doc("Payment Entry", name).cancel())

        def tamper_submitted() -> object:
            candidate = frappe.get_doc("Payment Entry", name)
            candidate.set("checked_signature", "forged")
            return candidate.save()

        self._assert_denied(tamper_submitted)
        self.assertEqual(
            frappe.db.get_value("Payment Entry", name, "checked_signature"), "data:image/png;base64,dGVzdA=="
        )

        def spoof_state(*, api: bool) -> object:
            candidate = frappe.get_doc("Payment Entry", name)
            candidate.set("workflow_state", "Payment Entry Cancelled")
            if api:
                return client_save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        self._assert_denied(lambda: spoof_state(api=False))
        self._assert_denied(lambda: spoof_state(api=True))
        self._assert_denied(
            lambda: client_set_value("Payment Entry", name, "workflow_state", "Payment Entry Cancelled")
        )
        self.assertEqual(frappe.db.get_value("Payment Entry", name, "docstatus"), 1)
        self.assertEqual(frappe.db.get_value("Payment Entry", name, "workflow_state"), route.submitted_state)
        self.assertTrue(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Payment Entry", "voucher_no": name, "is_cancelled": 0}
            )
        )
        doc.reload()
        doc = cast(PaymentEntry, apply_workflow(doc, "Cancel Payment Entry"))
        self.assertEqual(doc.docstatus, 2)
        self.assertEqual(doc.get("workflow_state"), "Payment Entry Cancelled")
        self.assertFalse(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Payment Entry", "voucher_no": name, "is_cancelled": 0}
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "Payment Ledger Entry",
                {"voucher_type": "Payment Entry", "voucher_no": name, "delinked": 0},
            )
        )
        for (doctype, invoice), balance in balances.items():
            self.assertAlmostEqual(
                float(frappe.db.get_value(doctype, invoice, "outstanding_amount")), balance
            )

    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(frappe.local.site, "local.test")
        self._old_user = frappe.session.user
        self._old_request = getattr(frappe.local, "request", None)
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        self._old_grants = list(grants) if grants is not None else None
        self._old_execution = getattr(frappe.flags, "connect_payment_entry_execution", None)
        self._savepoint = f"pe_sources_{uuid4().hex}"
        frappe.db.savepoint(self._savepoint)
        self.addCleanup(self._restore_sources)
        self.enterContext(
            patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
        )
        self._suffix = uuid4().hex[:12]
        self._users: list[str] = []
        self._templates: dict[str, PaymentEntry] = {}
        self._fixture_department = ""
        self._source_actors: dict[str, str] = {}
        self._alternate_pay_invoice: str | None = None
        self._fx_bank_account: str | None = None
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user("Administrator")

    def _restore_sources(self) -> None:
        try:
            frappe.db.rollback(save_point=self._savepoint)
        finally:
            for doctype in (
                "Thai Tax Settings",
                "Company",
                "Account",
                "Department",
                "Purchase Order",
                "Purchase Receipt",
                "Purchase Invoice",
                "Sales Invoice",
                "Payment Entry",
                "Withholding Tax Type",
            ):
                clear_document_cache(doctype)
            frappe.set_user(self._old_user)
            frappe.local.request = self._old_request
            if self._old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = self._old_grants
            frappe.flags.connect_payment_entry_execution = self._old_execution
            for user in self._users:
                frappe.clear_cache(user=user)

    def _department(self) -> str:
        dimension = frappe.db.get_value(
            "Accounting Dimension",
            {"document_type": "Department"},
            ["fieldname", "disabled"],
            as_dict=True,
        )
        self.assertTrue(dimension, "App-managed Department Accounting Dimension is missing")
        self.assertEqual(dimension.fieldname, "department")
        self.assertEqual(dimension.disabled, 0)
        for doctype in ("Purchase Invoice", "Sales Invoice", "Payment Entry"):
            field = frappe.get_meta(doctype).get_field("department")
            self.assertIsNotNone(field, f"{doctype}.department dimension field is missing")
            self.assertEqual(field.options, "Department")
        root = get_root_of("Department")
        self.assertTrue(root, "Department root is missing")
        return (
            frappe.get_doc(
                {
                    "doctype": "Department",
                    "department_name": f"_Test PE {self._suffix}",
                    "company": "_Test Company",
                    "parent_department": root,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _actor(self, label: str, roles: tuple[str, ...]) -> str:
        user = f"_test_pe_{label}_{self._suffix}@example.invalid"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": f"Test PE {label}",
                "user_type": "System User",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)
        self._users.append(user)
        frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Test PE {label}",
                "company": "_Test Company",
                "department": self._fixture_department,
                "gender": "Other",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "employment_type": "Full-time",
                "status": "Active",
                "user_id": user,
                "create_user_permission": 0,
                "approval_signature": "data:image/png;base64,dGVzdA==",
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(user=user)
        return user

    def _ensure_thai_tax_settings(self) -> None:
        company = "_Test Company"
        parent = frappe.db.get_value(
            "Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name"
        )
        self.assertTrue(parent, "Company liability Account group is missing")
        currency = frappe.db.get_value("Company", company, "default_currency")
        self.assertTrue(currency, "Company default currency is missing")
        self._tax_account = (
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": f"_Test PE Tax {self._suffix}",
                    "company": company,
                    "parent_account": parent,
                    "account_type": "Tax",
                    "root_type": "Liability",
                    "is_group": 0,
                    "account_currency": currency,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        settings = frappe.get_single("Thai Tax Settings")
        if not any(row.company == company for row in settings.company_accounts):
            settings.append(
                "company_accounts",
                {
                    "company": company,
                    "sales_tax_account": self._tax_account,
                    "purchase_tax_account": self._tax_account,
                },
            )
            settings.save(ignore_permissions=True)

    def _actors(self) -> dict[str, str]:
        if self._source_actors:
            return self._source_actors
        self._fixture_department = self._department()
        self._ensure_thai_tax_settings()
        roles = {
            "po_maker": ("Purchase User",),
            "po_reviewer": ("Purchase User", "Purchase Manager"),
            "po_approver": ("Purchase User", "C-Level Approver"),
            "pi_maker": ("Accounts User",),
            "pi_reviewer": ("Accounts User", "Purchase Manager"),
            "pi_approver": ("Accounts User", "Accounts Manager"),
        }
        self._source_actors = {label: self._actor(label, assigned) for label, assigned in roles.items()}
        return self._source_actors

    def _as_user(self, user: str, callback: Callable[[], T]) -> T:
        previous = frappe.session.user
        frappe.set_user(user)
        try:
            return callback()
        finally:
            frappe.set_user(previous)

    def _pay_invoice(self, actors: dict[str, str]) -> str:
        company = "_Test Company"
        item = "_Test Item"
        warehouse = "_Test Warehouse - _TC"
        supplier = "_Test Supplier"
        for doctype, name in (
            ("Company", company),
            ("Item", item),
            ("Warehouse", warehouse),
            ("Supplier", supplier),
        ):
            self.assertTrue(frappe.db.exists(doctype, name), f"Missing native test master: {doctype} {name}")
        order = self._as_user(
            actors["po_maker"],
            lambda: frappe.get_doc(
                {
                    "doctype": "Purchase Order",
                    "company": company,
                    "supplier": supplier,
                    "department": self._fixture_department,
                    "schedule_date": add_days(nowdate(), 1),
                    "items": [
                        {
                            "item_code": item,
                            "qty": 1,
                            "rate": 100,
                            "warehouse": warehouse,
                            "schedule_date": add_days(nowdate(), 1),
                            "department": self._fixture_department,
                        }
                    ],
                }
            ).insert(),
        )
        order = self._as_user(
            actors["po_maker"], lambda: apply_workflow(order, "Submit Purchase Order for Review")
        )
        order = self._as_user(actors["po_reviewer"], lambda: apply_workflow(order, "Review Purchase Order"))
        order = self._as_user(actors["po_approver"], lambda: apply_workflow(order, "Approve Purchase Order"))
        order = self._as_user(actors["po_reviewer"], lambda: apply_workflow(order, "Post Purchase Order"))
        self.assertEqual(order.docstatus, 1)
        receipt = frappe.get_doc(
            {
                "doctype": "Purchase Receipt",
                "company": company,
                "supplier": supplier,
                "department": self._fixture_department,
                "items": [
                    {
                        "item_code": item,
                        "qty": 1,
                        "rate": 100,
                        "warehouse": warehouse,
                        "purchase_order": order.name,
                        "purchase_order_item": order.items[0].name,
                        "department": self._fixture_department,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        receipt.submit()
        invoice = self._as_user(
            actors["pi_maker"],
            lambda: frappe.get_doc(
                {
                    "doctype": "Purchase Invoice",
                    "company": company,
                    "supplier": supplier,
                    "bill_no": f"PE-{self._suffix}-{uuid4().hex[:6]}",
                    "department": self._fixture_department,
                    "items": [
                        {
                            "item_code": item,
                            "qty": 1,
                            "rate": 100,
                            "purchase_order": order.name,
                            "po_detail": order.items[0].name,
                            "purchase_receipt": receipt.name,
                            "pr_detail": receipt.items[0].name,
                            "department": self._fixture_department,
                        }
                    ],
                }
            ).insert(),
        )
        invoice = self._as_user(
            actors["pi_maker"], lambda: apply_workflow(invoice, "Submit Purchase Invoice for Review")
        )
        invoice = self._as_user(
            actors["pi_reviewer"], lambda: apply_workflow(invoice, "Verify Purchase Invoice Source")
        )
        invoice = self._as_user(
            actors["pi_approver"], lambda: apply_workflow(invoice, "Approve Purchase Invoice")
        )
        invoice = self._as_user(
            actors["pi_approver"], lambda: apply_workflow(invoice, "Post Purchase Invoice")
        )
        self.assertEqual(invoice.docstatus, 1)
        self.assertGreater(invoice.outstanding_amount, 0)
        return invoice.name

    def _receive_invoice(self, *, dimension_values: dict[str, str] | None = None) -> str:
        values: dict[str, object] = {
            "doctype": "Sales Invoice",
            "company": "_Test Company",
            "customer": "_Test Customer",
            "currency": "INR",
            "conversion_rate": 1,
            "debit_to": "Debtors - _TC",
            "department": self._fixture_department,
            "items": [
                {
                    "item_code": "_Test Item",
                    "qty": 1,
                    "rate": 100,
                    "income_account": "Sales - _TC",
                    "cost_center": "_Test Cost Center - _TC",
                    "department": self._fixture_department,
                }
            ],
        }
        values.update(dimension_values or {})
        for item in cast(list[dict[str, object]], values["items"]):
            item.update(dimension_values or {})
        invoice = frappe.get_doc(values).insert(ignore_permissions=True)
        invoice.submit()
        self.assertGreater(invoice.outstanding_amount, 0)
        return invoice.name

    def _ensure_withholding_type(self) -> str:
        if not hasattr(self, "_withholding_type"):
            self._withholding_type = (
                frappe.get_doc(
                    {
                        "doctype": "Withholding Tax Type",
                        "title": f"_Test PE WHT {self._suffix}",
                        "percent": 1,
                        "for_payment_type": "Pay",
                        "accounts": [{"company": "_Test Company", "account": self._tax_account}],
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )
        return self._withholding_type

    def _fx_receivable_account(self) -> str:
        existing = "_Test Receivable USD - _TC"
        if frappe.db.exists("Account", existing):
            account = frappe.get_doc("Account", existing)
            self.assertEqual(account.company, "_Test Company")
            self.assertEqual(account.account_currency, "USD")
            self.assertEqual(account.account_type, "Receivable")
            self.assertEqual(account.is_group, 0)
            return existing
        parent = frappe.db.get_value(
            "Account",
            {"company": "_Test Company", "root_type": "Asset", "is_group": 1},
            "name",
        )
        self.assertTrue(parent, "Company asset Account group is missing")
        return (
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": f"_Test PE USD Receivable {self._suffix}",
                    "company": "_Test Company",
                    "parent_account": parent,
                    "account_type": "Receivable",
                    "root_type": "Asset",
                    "is_group": 0,
                    "account_currency": "USD",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _fx_bank(self) -> str:
        if self._fx_bank_account:
            return self._fx_bank_account
        reference = frappe.get_doc("Account", "_Test Bank - _TC")
        self.assertEqual(reference.company, "_Test Company")
        self.assertEqual(reference.account_currency, "INR")
        self.assertEqual(reference.account_type, "Bank")
        self.assertEqual(reference.is_group, 0)
        parent = frappe.get_doc("Account", reference.parent_account)
        self.assertEqual(parent.company, reference.company)
        self.assertEqual(parent.is_group, 1)
        self.assertEqual(parent.root_type, "Asset")
        self.assertEqual(parent.account_currency, reference.account_currency)
        self._fx_bank_account = (
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": f"_Test PE FX Bank {self._suffix}",
                    "company": reference.company,
                    "parent_account": parent.name,
                    "account_type": "Bank",
                    "root_type": "Asset",
                    "is_group": 0,
                    "account_currency": reference.account_currency,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        return self._fx_bank_account

    def _fx_invoice(self) -> str:
        self._actors()
        customer = "_Test Customer USD"
        self.assertTrue(frappe.db.exists("Customer", customer), "Native USD test Customer is missing")
        receivable = self._fx_receivable_account()
        invoice = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "company": "_Test Company",
                "customer": customer,
                "currency": "USD",
                "conversion_rate": 50,
                "debit_to": receivable,
                "department": self._fixture_department,
                "items": [
                    {
                        "item_code": "_Test Item",
                        "qty": 1,
                        "rate": 10,
                        "income_account": "Sales - _TC",
                        "cost_center": "_Test Cost Center - _TC",
                        "department": self._fixture_department,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        invoice.submit()
        self.assertGreater(invoice.outstanding_amount, 0)
        return invoice.name

    def _template(self, payment_type: str) -> PaymentEntry:
        if payment_type not in self._templates:
            actors = self._actors()
            if payment_type == "Pay":
                invoice = self._pay_invoice(actors)
                self._alternate_pay_invoice = self._pay_invoice(actors)
                source_doctype = "Purchase Invoice"
            else:
                invoice = self._receive_invoice()
                source_doctype = "Sales Invoice"
            template = cast(
                PaymentEntry, get_payment_entry(source_doctype, invoice, bank_account="_Test Bank - _TC")
            )
            template.set("reference_no", f"PE-{self._suffix}")
            template.set("reference_date", nowdate())
            self._templates[payment_type] = template
        return self._templates[payment_type]

    def _clone(self, source: PaymentEntry) -> PaymentEntry:
        doc = cast(PaymentEntry, frappe.copy_doc(source))
        doc.docstatus = 0
        doc.set("workflow_state", "Payment Entry Draft")
        for fieldname in APPROVAL_FIELDS:
            doc.set(fieldname, None)
        for child in doc.get_all_children():
            child.docstatus = 0
            for fieldname in APPROVAL_FIELDS:
                if child.meta.has_field(fieldname):
                    child.set(fieldname, None)
        return doc

    def _probe(
        self,
        payment_type: str,
        *,
        saved: bool,
        source: PaymentEntry | None = None,
        change: Callable[[PaymentEntry], None] | None = None,
        verify: Callable[[PaymentEntry], None] | None = None,
    ) -> dict[str, tuple[str | None, str | None]]:
        self.assertEqual(frappe.local.site, "local.test")
        source = source or self._template(payment_type)
        balances = {
            (row.reference_doctype, row.reference_name): frappe.db.get_value(
                row.reference_doctype, row.reference_name, "outstanding_amount"
            )
            for row in source.references
            if row.reference_doctype in ("Purchase Invoice", "Sales Invoice") and row.reference_name
        }
        savepoint = f"pe_payload_{uuid4().hex}"
        frappe.db.savepoint(savepoint)
        voucher_name: str | None = None
        try:
            doc = self._clone(source)
            if saved:
                doc.insert(ignore_permissions=True)
            voucher_name = doc.name
            if change:
                change(doc)
            for row in doc.references:
                if (
                    row.reference_doctype not in ("Purchase Invoice", "Sales Invoice")
                    or not row.reference_name
                ):
                    continue
                key = (row.reference_doctype, row.reference_name)
                if key not in balances:
                    balances[key] = frappe.db.get_value(
                        row.reference_doctype, row.reference_name, "outstanding_amount"
                    )
            doc._action = "submit"
            doc.docstatus = 1
            before = field_fingerprints(doc)
            try:
                doc.validate()
                validate_reference_dimensions(doc)
            except Exception as exc:
                self.fail(f"Native {payment_type} validation failed: {type(exc).__name__}")
            if verify:
                verify(doc)
            after = field_fingerprints(doc)
            changed = {
                fieldname: (
                    before.get(fieldname, (None, ""))[0],
                    after.get(fieldname, (None, ""))[0],
                )
                for fieldname in before.keys() | after.keys()
                if before.get(fieldname) != after.get(fieldname)
            }
            self.assertEqual(doc.docstatus, 1)
            self.assertEqual(doc._action, "submit")
            if saved:
                self.assertTrue(voucher_name)
                self.assertEqual(frappe.db.get_value("Payment Entry", voucher_name, "docstatus"), 0)
            else:
                self.assertIsNone(voucher_name)
            if voucher_name:
                for ledger in ("GL Entry", "Payment Ledger Entry"):
                    self.assertEqual(
                        frappe.db.count(
                            ledger, {"voucher_type": "Payment Entry", "voucher_no": voucher_name}
                        ),
                        0,
                    )
            for (doctype, name), amount in balances.items():
                self.assertEqual(frappe.db.get_value(doctype, name, "outstanding_amount"), amount)
            return changed
        finally:
            frappe.db.rollback(save_point=savepoint)
            if voucher_name:
                clear_document_cache("Payment Entry", voucher_name)
            if saved and voucher_name:
                self.assertFalse(frappe.db.exists("Payment Entry", voucher_name))
            for (doctype, name), amount in balances.items():
                self.assertEqual(frappe.db.get_value(doctype, name, "outstanding_amount"), amount)

    def test_native_submit_validation_of_pay_and_receive_templates(self) -> None:
        for payment_type in ("Pay", "Receive"):
            for saved in (False, True):
                with self.subTest(payment_type=payment_type, saved=saved):
                    self._probe(payment_type, saved=saved)

    def test_native_submit_validation_prunes_zero_allocation(self) -> None:
        def add_zero_reference(doc: PaymentEntry) -> None:
            existing = doc.references[0]
            self.assertTrue(self._alternate_pay_invoice)
            row = frappe.copy_doc(existing)
            row.set("reference_name", self._alternate_pay_invoice)
            row.set("allocated_amount", 0)
            doc.append("references", row.as_dict())

        for saved in (False, True):
            with self.subTest(saved=saved):
                changed = self._probe(
                    "Pay",
                    saved=saved,
                    change=add_zero_reference,
                    verify=lambda doc: self.assertEqual(len(doc.references), 1),
                )
                self.assertTrue(any(field.startswith("references[2].") for field in changed))

    def test_native_submit_validation_of_tax_and_deduction_inputs(self) -> None:
        def with_tax(doc: PaymentEntry, charge_type: str) -> None:
            account = self._tax_account
            doc.append(
                "taxes",
                {
                    "add_deduct_tax": "Add",
                    "charge_type": charge_type,
                    "account_head": account,
                    "description": "Test tax",
                    "tax_amount": 1 if charge_type == "Actual" else 0,
                    "rate": 1 if charge_type != "Actual" else 0,
                },
            )

        def with_deduction(doc: PaymentEntry) -> None:
            account = self._tax_account
            cost_center = doc.get("cost_center") or frappe.db.get_value(
                "Cost Center", {"company": doc.company, "is_group": 0}, "name"
            )
            self.assertTrue(cost_center, "No same-company Cost Center")
            row = {
                "account": account,
                "amount": 1,
                "description": "Test withholding",
                "cost_center": cost_center,
            }
            withholding_field = frappe.get_meta("Payment Entry Deduction").get_field("withholding_tax_type")
            self.assertTrue(withholding_field, "Thai withholding child field is missing")
            self.assertEqual(withholding_field.options, "Withholding Tax Type")
            row["withholding_tax_type"] = self._withholding_type
            row["withholding_tax_base"] = 100
            doc.append("deductions", row)

        for charge_type in ("Actual", "On Paid Amount"):
            with self.subTest(charge_type=charge_type):
                for saved in (False, True):
                    self._probe(
                        "Pay",
                        saved=saved,
                        change=lambda doc: with_tax(doc, charge_type),
                        verify=lambda doc: self.assertGreater(doc.taxes[0].tax_amount, 0),
                    )
        for saved in (False, True):
            with self.subTest(deduction=True, saved=saved):
                self._template("Pay")
                self._ensure_withholding_type()
                self._probe(
                    "Pay",
                    saved=saved,
                    change=with_deduction,
                    verify=lambda doc: self.assertEqual(len(doc.deductions), 1),
                )

    def test_native_submit_validation_propagates_active_dimension(self) -> None:
        from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
            get_accounting_dimensions,
        )

        self.assertIn("department", get_accounting_dimensions())

        def clear_reference_dimension(doc: PaymentEntry) -> None:
            reference = doc.references[0]
            self.assertEqual(
                frappe.db.get_value(reference.reference_doctype, reference.reference_name, "department"),
                self._fixture_department,
            )
            doc.set("department", None)

        for saved in (False, True):
            with self.subTest(saved=saved):
                changed = self._probe("Pay", saved=saved, change=clear_reference_dimension)
                self.assertTrue(changed)

    def test_native_fx_receive_validation_uses_explicit_invoice_rate(self) -> None:
        invoice = self._fx_invoice()
        balance = frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount")
        bank = self._fx_bank()
        doc = cast(
            PaymentEntry,
            get_payment_entry("Sales Invoice", invoice, bank_account=bank, bank_amount=500),
        )
        doc.set("reference_no", f"FX-{self._suffix}")
        doc.set("reference_date", nowdate())
        doc.set("source_exchange_rate", 50)
        doc.set_amounts()
        self.assertEqual(doc.payment_type, "Receive")
        self.assertEqual(doc.paid_from_account_currency, "USD")
        self.assertEqual(doc.paid_to_account_currency, "INR")
        self.assertEqual(doc.source_exchange_rate, 50)

        def verify_fx(validated: PaymentEntry) -> None:
            self.assertEqual(validated.payment_type, "Receive")
            self.assertEqual(validated.paid_from_account_currency, "USD")
            self.assertEqual(validated.paid_to_account_currency, "INR")
            self.assertEqual(validated.source_exchange_rate, 50)
            self.assertEqual(validated.paid_amount, balance)
            self.assertEqual(validated.received_amount, 500)
            self.assertEqual(len(validated.references), 1)
            self.assertEqual(validated.references[0].reference_name, invoice)
            self.assertEqual(validated.references[0].allocated_amount, balance)

        for saved in (False, True):
            with self.subTest(saved=saved):
                self._probe("Receive", saved=saved, source=doc, verify=verify_fx)
        self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount"), balance)

    def test_native_manual_pay_and_receive_without_invoice(self) -> None:
        for payment_type in ("Pay", "Receive"):
            with self.subTest(payment_type=payment_type):
                source = self._template(payment_type)
                balances = {
                    (row.reference_doctype, row.reference_name): frappe.db.get_value(
                        row.reference_doctype, row.reference_name, "outstanding_amount"
                    )
                    for row in source.references
                }
                doc = cast(PaymentEntry, frappe.new_doc("Payment Entry"))
                for fieldname in (
                    "company",
                    "party_type",
                    "party",
                    "paid_from",
                    "paid_to",
                    "paid_from_account_currency",
                    "paid_to_account_currency",
                    "cost_center",
                ):
                    doc.set(fieldname, source.get(fieldname))
                doc.payment_type = payment_type
                doc.paid_amount = 100
                doc.received_amount = 100
                doc.reference_no = f"MANUAL-{self._suffix}"
                doc.reference_date = nowdate()
                doc.setup_party_account_field()
                doc.set_missing_values()
                doc.set_exchange_rate()
                doc.set_amounts()
                self.assertFalse(doc.references)
                savepoint = f"pe_manual_{uuid4().hex}"
                frappe.db.savepoint(savepoint)
                try:
                    maker = self._actors()["pi_maker"]
                    self._as_user(maker, lambda: doc.insert())
                    self.assertEqual(
                        frappe.db.get_value("Payment Entry", doc.name, "workflow_state"),
                        "Payment Entry Draft",
                    )
                    with self.assertRaises(frappe.ValidationError):
                        self._as_user(maker, lambda: doc.submit())
                    self.assertEqual(frappe.db.get_value("Payment Entry", doc.name, "docstatus"), 0)
                    self.assertEqual(
                        frappe.db.get_value("Payment Entry", doc.name, "workflow_state"),
                        "Payment Entry Draft",
                    )
                    for ledger in ("GL Entry", "Payment Ledger Entry"):
                        self.assertEqual(
                            frappe.db.count(
                                ledger, {"voucher_type": "Payment Entry", "voucher_no": doc.name}
                            ),
                            0,
                        )
                    for (doctype, name), amount in balances.items():
                        self.assertEqual(frappe.db.get_value(doctype, name, "outstanding_amount"), amount)
                finally:
                    frappe.db.rollback(save_point=savepoint)
                    clear_document_cache("Payment Entry", doc.name)
                self.assertFalse(frappe.db.exists("Payment Entry", doc.name))

    def test_ordinary_user_cannot_enable_core_tds(self) -> None:
        from connect_diagnostics_core.setup.tds import get_disabled_message

        source = self._template("Pay")
        doc = self._clone(source)
        doc.set("apply_tds", 1)
        maker = self._actors()["pi_maker"]
        with self.assertRaises(frappe.ValidationError) as error:
            self._as_user(maker, lambda: doc.insert())
        self.assertEqual(str(error.exception), get_disabled_message())
        self.assertFalse(frappe.db.exists("Payment Entry", doc.name))

    def test_canonical_route_and_transition_tasks_are_live(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")
        workflow = frappe.get_doc("Workflow", "Connect Payment Entry Approval")
        self.assertEqual(workflow.document_type, "Payment Entry")
        self.assertEqual(workflow.is_active, 1)
        self.assertEqual(
            {row.state for row in workflow.states},
            {
                "Payment Entry Draft",
                "Payment Entry Pending Review",
                "Payment Entry Reviewed",
                "Payment Entry Approved",
                "Payment Entry Submitted",
                "Payment Entry Returned",
                "Payment Entry Rejected",
                "Payment Entry Cancelled",
            },
        )
        task_names = {row.transition_tasks for row in workflow.transitions if row.transition_tasks}
        self.assertEqual(
            task_names,
            {
                "Connect Payment Entry Capture Maker",
                "Connect Payment Entry Capture Checker",
                "Connect Payment Entry Capture Approver",
                "Connect Payment Entry Clear Approval",
                "Connect Payment Entry Submit Execution",
                "Connect Payment Entry Cancel Execution",
            },
        )
        for name in task_names:
            task_doc = frappe.get_doc("Workflow Transition Tasks", name)
            self.assertEqual(len(task_doc.tasks), 1)
            self.assertEqual(task_doc.tasks[0].task, name)
            self.assertEqual(task_doc.tasks[0].enabled, 1)
