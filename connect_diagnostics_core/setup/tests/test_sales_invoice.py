# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import sales_invoice


class TestSalesInvoiceCustomFields(UnitTestCase):
    def _field(self, fieldname: str) -> dict[str, str | int]:
        return next(
            field for field in sales_invoice.CUSTOM_FIELDS["Sales Invoice"] if field["fieldname"] == fieldname
        )

    def test_credit_note_reason_is_select_with_expected_options(self) -> None:
        field = self._field("credit_note_reason")
        self.assertEqual(field["fieldtype"], "Select")
        self.assertEqual(field["options"], "\n".join(sales_invoice.CREDIT_NOTE_REASONS))

    def test_credit_note_reason_only_shows_and_is_required_for_returns(self) -> None:
        field = self._field("credit_note_reason")
        self.assertEqual(field["depends_on"], "eval:doc.is_return")
        self.assertEqual(field["mandatory_depends_on"], "eval:doc.is_return")

    def test_credit_note_reason_follows_return_against(self) -> None:
        field = self._field("credit_note_reason")
        self.assertEqual(field["insert_after"], "return_against")

    def test_fieldnames_are_unique(self) -> None:
        fieldnames = [field["fieldname"] for field in sales_invoice.CUSTOM_FIELDS["Sales Invoice"]]
        self.assertEqual(len(fieldnames), len(set(fieldnames)))

    def test_demo_sale_provenance_fields_are_immutable_and_auditable(self) -> None:
        for fieldname in (
            "demo_fulfillment_allocation",
            "demo_outbound_dispatch",
            "demo_sale_attempt",
            "demo_sale_operation_id",
        ):
            field = self._field(fieldname)
            self.assertEqual(field["read_only"], 1)
            self.assertEqual(field["no_copy"], 1)
        self.assertEqual(self._field("demo_sale_operation_id")["unique"], 1)

    def test_auto_invoice_provenance_is_server_owned_and_locked_after_submit(self) -> None:
        expected = {
            "connect_invoice_generation_run": ("Link", "Sales Invoice Generation"),
            "connect_invoice_source_doctype": ("Data", None),
            "connect_invoice_source_name": ("Data", None),
            "connect_billing_authority_digest": ("Data", None),
            "connect_source_group_digest": ("Data", None),
            "connect_generated_by_actor": ("Link", "User"),
            "connect_generated_at": ("Datetime", None),
            "connect_generation_payload_digest": ("Data", None),
        }
        actual = {
            str(field["fieldname"])
            for field in sales_invoice.CUSTOM_FIELDS["Sales Invoice"]
            if str(field["fieldname"]).startswith("connect_")
        }
        self.assertEqual(actual, set(expected))
        for name, (fieldtype, options) in expected.items():
            field = self._field(name)
            self.assertEqual(field["fieldtype"], fieldtype)
            self.assertEqual(field.get("options"), options)
            for key in ("hidden", "read_only", "no_copy"):
                self.assertEqual(field[key], 1)
            self.assertFalse(field.get("allow_on_submit"))
            self.assertFalse(field.get("default"))
            self.assertFalse(field.get("reqd"))
