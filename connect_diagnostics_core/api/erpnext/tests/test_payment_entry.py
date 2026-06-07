# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ..payment_entry import DimensionField, validate_reference_dimensions


class PaymentEntryStub:
    doctype = "Payment Entry"

    def __init__(self, *, references: list[frappe._dict], **values: Any) -> None:
        self.references = references
        self.values = values

    def get(self, key: str, default: Any = None) -> Any:
        if key == "references":
            return self.references
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


def make_reference(name: str, *, allocated_amount: float = 100) -> frappe._dict:
    return frappe._dict(
        reference_doctype="Purchase Invoice",
        reference_name=name,
        allocated_amount=allocated_amount,
    )


class TestPaymentEntryReferenceDimensions(FrappeTestCase):
    def setUp(self) -> None:
        self.dimensions = [DimensionField("department", "Department")]
        self.dimension_patch = patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_payment_entry_dimension_fields",
            return_value=self.dimensions,
        )
        self.dimension_patch.start()
        self.addCleanup(self.dimension_patch.stop)

    def test_payment_entry_dimension_must_match_reference(self) -> None:
        doc = PaymentEntryStub(references=[make_reference("PINV-001")], department="Dept B")

        with patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_reference_dimensions",
            return_value={"department": "Dept A"},
        ):
            with self.assertRaises(frappe.ValidationError) as context:
                validate_reference_dimensions(doc)

        self.assertIn("Department", str(context.exception))
        self.assertIn("PINV-001", str(context.exception))

    def test_missing_payment_entry_dimension_is_synced_from_reference(self) -> None:
        doc = PaymentEntryStub(references=[make_reference("PINV-001")])

        with patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_reference_dimensions",
            return_value={"department": "Dept A"},
        ):
            validate_reference_dimensions(doc)

        self.assertEqual(doc.get("department"), "Dept A")

    def test_multiple_references_with_same_dimensions_are_allowed(self) -> None:
        doc = PaymentEntryStub(
            references=[make_reference("PINV-001"), make_reference("PINV-002")],
            department="Dept A",
        )

        with patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_reference_dimensions",
            return_value={"department": "Dept A"},
        ):
            validate_reference_dimensions(doc)

    def test_multiple_references_with_different_dimensions_are_blocked(self) -> None:
        doc = PaymentEntryStub(
            references=[make_reference("PINV-001"), make_reference("PINV-002")],
            department="Dept A",
        )

        with patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_reference_dimensions",
            side_effect=[{"department": "Dept A"}, {"department": "Dept B"}],
        ):
            with self.assertRaises(frappe.ValidationError) as context:
                validate_reference_dimensions(doc)

        self.assertIn("different accounting dimensions", str(context.exception))

    def test_unallocated_invoice_references_are_ignored(self) -> None:
        doc = PaymentEntryStub(
            references=[make_reference("PINV-001", allocated_amount=0)], department="Dept B"
        )

        with patch(
            "connect_diagnostics_core.api.erpnext.payment_entry.get_reference_dimensions"
        ) as get_reference_dimensions:
            validate_reference_dimensions(doc)

        get_reference_dimensions.assert_not_called()
