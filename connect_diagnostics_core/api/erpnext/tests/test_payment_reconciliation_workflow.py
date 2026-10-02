# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payment_reconciliation as matching
from connect_diagnostics_core.api.erpnext.payment_entry import DimensionField


def _tool(*rows: dict[str, object]) -> Document:
    return Document(
        {
            "doctype": "Payment Reconciliation",
            "company": "_Test Company",
            "party_type": "Customer",
            "party": "_Test Customer",
            "receivable_payable_account": "Debtors - _TC",
            "allocation": list(rows),
        }
    )


def _row(**values: object) -> dict[str, object]:
    return {
        "doctype": "Payment Reconciliation Allocation",
        "reference_type": "Payment Entry",
        "reference_name": "PE-1",
        "invoice_type": "Sales Invoice",
        "invoice_number": "SI-1",
        "allocated_amount": 30,
        "unreconciled_amount": 100,
        "amount": 100,
        "exchange_rate": 1,
        "difference_amount": 0,
        "currency": "INR",
        "cost_center": None,
        **values,
    }


class TestPaymentReconciliationWorkflow(UnitTestCase):
    def tearDown(self) -> None:
        if hasattr(frappe.local, matching._CONTEXT_KEY):
            delattr(frappe.local, matching._CONTEXT_KEY)
        super().tearDown()

    def test_no_payment_entry_keeps_native_non_payment_route(self) -> None:
        tool = _tool(_row(reference_type="Journal Entry"))
        with patch.object(matching, "require_interactive_user") as authorize:
            self.assertEqual(matching._prepare(tool, False), {})
            authorize.assert_not_called()

    def test_mixed_operation_is_rejected_before_lock_or_native_effect(self) -> None:
        for extra in (
            _row(reference_type="Journal Entry", reference_name="JE-1"),
            _row(invoice_type="Credit Note", invoice_number="CN-1"),
            _row(allocated_amount=0),
            _row(reference_row="ORDER-ROW"),
        ):
            with self.subTest(extra=extra):
                tool = _tool(_row(), extra)
                with (
                    patch.object(matching, "require_interactive_user", return_value="user@example.com"),
                    patch.object(matching, "_locked_document") as lock,
                ):
                    with self.assertRaises(frappe.ValidationError):
                        matching._prepare(tool, False)
                    lock.assert_not_called()

    def test_queued_payment_route_is_denied_before_authorization(self) -> None:
        with patch.object(matching, "require_interactive_user") as authorize:
            with self.assertRaises(frappe.ValidationError):
                matching._prepare(_tool(_row()), True)
            authorize.assert_not_called()

    def test_allocation_must_be_positive_and_finite(self) -> None:
        for value in (0, -1, "NaN", "Infinity", None, "invalid"):
            with self.subTest(value=value):
                with self.assertRaises(frappe.ValidationError):
                    matching._positive(value)

    def test_rates_and_gain_loss_require_exact_finite_values(self) -> None:
        self.assertTrue(matching._exact_number(1, 1))
        self.assertTrue(matching._exact_number(0.0, 0))
        for value in (1.001, "1.0001", "NaN", "Infinity", None):
            with self.subTest(value=value):
                self.assertFalse(matching._exact_number(value, 1))
        self.assertFalse(matching._exact_number(0.001, 0))

    def test_combined_fractional_allocations_use_currency_precision(self) -> None:
        payment = Document(
            {
                "doctype": "Payment Entry",
                "name": "PE-1",
                "unallocated_amount": 0.3,
                "cost_center": "Approved cost center",
            }
        )
        invoice = Document(
            {
                "doctype": "Sales Invoice",
                "name": "SI-1",
                "outstanding_amount": 0.3,
            }
        )
        tool = _tool(
            _row(allocated_amount=0.1, unreconciled_amount=0.3, amount=0.3),
            _row(allocated_amount=0.2, unreconciled_amount=0.3, amount=0.2),
        )

        def locked(doctype: str, name: str) -> Document:
            return payment if doctype == "Payment Entry" else invoice

        with (
            patch.object(matching, "require_interactive_user", return_value="user@example.com"),
            patch.object(matching, "_locked_document", side_effect=locked),
            patch.object(matching, "_company_currency", return_value="INR"),
            patch.object(matching.frappe, "get_precision", return_value=2),
            patch.object(matching, "_check_payment"),
            patch.object(matching, "_check_invoice"),
            patch.object(matching, "_expected_payload", return_value={"valid": True}),
            patch.object(matching, "get_approval_digest", return_value="before"),
            patch.object(matching, "critical_digest", return_value="expected"),
        ):
            capabilities = matching._prepare(tool, False)
            self.assertEqual(
                tuple(allocation.amount for allocation in capabilities["PE-1"].allocations),
                (0.1, 0.2),
            )
            tool.get("allocation")[0].set("cost_center", "Forged cost center")
            with self.assertRaises(frappe.ValidationError):
                matching._prepare(tool, False)

    def test_subprecision_allocation_is_denied(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            matching._currency_value(0.001, 2)

    def test_invoice_matching_preserves_dynamic_and_builtin_dimensions(self) -> None:
        source = _tool(_row())
        payment = Document({"doctype": "Payment Entry", "party_type": "Customer"})
        invoice = Document(
            {
                "doctype": "Sales Invoice",
                "docstatus": 1,
                "company": source.get("company"),
                "customer": source.get("party"),
                "debit_to": source.get("receivable_payable_account"),
                "currency": "INR",
                "conversion_rate": 1,
            }
        )
        for fieldname in ("cost_center", "project", "department", "new_active_dimension"):
            with self.subTest(fieldname=fieldname):
                source.set(fieldname, "Approved scope")
                payment.set(fieldname, "Approved scope")
                invoice.set(fieldname, "Approved scope")
                with (
                    patch.object(matching.frappe, "has_permission", return_value=True),
                    patch.object(
                        matching,
                        "get_payment_entry_dimension_fields",
                        return_value=[DimensionField(fieldname, fieldname)],
                    ),
                    patch.object(invoice.meta, "has_field", return_value=True),
                ):
                    matching._check_invoice(source, invoice, payment, "INR")
                    invoice.set(fieldname, "Different scope")
                    with self.assertRaises(frappe.ValidationError):
                        matching._check_invoice(source, invoice, payment, "INR")
                    invoice.set(fieldname, "Approved scope")
                    source.set(fieldname, "Different scope")
                    with self.assertRaises(frappe.ValidationError):
                        matching._check_invoice(source, invoice, payment, "INR")
                self.assertEqual(payment.get(fieldname), "Approved scope")

    def test_reference_identity_preserves_old_rows_and_exact_new_shape(self) -> None:
        previous = Document({"doctype": "Payment Entry", "name": "PE-1"})
        previous.append("references", {"name": "OLD-1", "reference_name": "SI-OLD"})
        payment = Document({"doctype": "Payment Entry", "name": "PE-1"})
        payment.append("references", {"name": "OLD-1", "reference_name": "SI-OLD"})
        new_row = payment.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": "SI-1",
                "allocated_amount": 30,
            },
        )
        new_row.docstatus = 1
        allocation = (matching._Allocation("Sales Invoice", "SI-1", 30),)
        self.assertTrue(matching._reference_identity_valid(payment, previous, allocation))
        payment.get("references")[0].name = "FORGED"
        self.assertFalse(matching._reference_identity_valid(payment, previous, allocation))
        payment.get("references")[0].name = "OLD-1"
        new_row.name = "OLD-1"
        self.assertFalse(matching._reference_identity_valid(payment, previous, allocation))
        new_row.name = None
        new_row.docstatus = 0
        self.assertFalse(matching._reference_identity_valid(payment, previous, allocation))

    def test_capability_rejects_wrong_object_actor_payment_and_payload(self) -> None:
        source = _tool(_row())
        payment = Document({"doctype": "Payment Entry", "name": "PE-1"})
        previous = Document({"doctype": "Payment Entry", "name": "PE-1"})
        appended = payment.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": "SI-1",
                "allocated_amount": 30,
            },
        )
        appended.docstatus = 1
        cap = matching._Capability(
            source=source,
            user="user@example.com",
            payment="PE-1",
            before_digest="before",
            expected_digest="expected",
            allocations=(matching._Allocation("Sales Invoice", "SI-1", 30),),
        )
        context = matching._Context(source, {"PE-1": cap})
        setattr(frappe.local, matching._CONTEXT_KEY, context)
        with (
            patch.object(matching, "get_approval_digest", return_value="before"),
            patch.object(matching, "approval_payload", return_value={"reference": "SI-1"}),
            patch.object(matching, "critical_digest", return_value="expected"),
            patch.object(matching.frappe, "session", user="other@example.com"),
        ):
            with self.assertRaises(frappe.ValidationError):
                matching.consume_matching_capability(payment, previous)
        self.assertIn("PE-1", context.capabilities)
        with (
            patch.object(matching, "get_approval_digest", return_value="before"),
            patch.object(matching, "approval_payload", return_value={"reference": "SI-1"}),
            patch.object(matching, "critical_digest", return_value="different"),
            patch.object(matching.frappe, "session", user="user@example.com"),
        ):
            with self.assertRaises(frappe.ValidationError):
                matching.consume_matching_capability(payment, previous)
        self.assertIn("PE-1", context.capabilities)
        with (
            patch.object(matching, "get_approval_digest", return_value="before"),
            patch.object(matching, "approval_payload", return_value={"reference": "SI-1"}),
            patch.object(matching, "critical_digest", return_value="expected"),
            patch.object(matching.frappe, "session", user="user@example.com"),
        ):
            wrong_payment = Document({"doctype": "Payment Entry", "name": "PE-2"})
            with self.assertRaises(frappe.ValidationError):
                matching.consume_matching_capability(wrong_payment, previous)
            context.source = _tool(_row())
            with self.assertRaises(frappe.ValidationError):
                matching.consume_matching_capability(payment, previous)
            context.source = source
            matching.consume_matching_capability(payment, previous)
            with self.assertRaises(frappe.ValidationError):
                matching.consume_matching_capability(payment, previous)

    def test_expected_payload_uses_only_pure_native_helpers(self) -> None:
        payment = Document({"doctype": "Payment Entry", "name": "PE-1"})
        expected = Document({"doctype": "Payment Entry", "name": "PE-1", "references": []})
        with (
            patch.object(matching.frappe, "get_doc", return_value=expected),
            patch.object(expected, "setup_party_account_field", create=True),
            patch.object(expected, "set_missing_values", create=True),
            patch.object(expected, "set_missing_ref_details", create=True),
            patch.object(expected, "set_amounts", create=True),
            patch.object(matching, "approval_payload", return_value={"references": ["SI-1"]}),
        ):
            self.assertEqual(
                matching._expected_payload(
                    payment, (matching._Allocation("Sales Invoice", "SI-1", 30),), "Debtors - _TC"
                ),
                {"references": ["SI-1"]},
            )
            self.assertEqual(len(expected.get("references")), 1)
