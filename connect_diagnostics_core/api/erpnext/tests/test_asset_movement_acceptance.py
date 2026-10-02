# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import asset_movement_acceptance as acceptance


class TestAssetMovementAcceptance(UnitTestCase):
    def _lookup(self, doctype: str, name: str, *args: object, **kwargs: object) -> frappe._dict:
        del name, args, kwargs
        if doctype == "Employee":
            return frappe._dict(status="Active", user_id="receiver@example.com")
        return frappe._dict(enabled=1, user_type="System User")

    def test_employee_resolves_receiver_and_location_requires_explicit_user(self) -> None:
        row = frappe._dict(to_employee="EMP", receiver_user=None)
        with patch.object(acceptance.frappe.db, "get_value", side_effect=self._lookup):
            self.assertEqual(acceptance._receiver(row), "receiver@example.com")
            row.receiver_user = "other@example.com"
            with self.assertRaises(frappe.ValidationError):
                acceptance._receiver(row)
            row.to_employee = None
            row.receiver_user = "receiver@example.com"
            self.assertEqual(acceptance._receiver(row), "receiver@example.com")
            row.receiver_user = None
            with self.assertRaises(frappe.ValidationError):
                acceptance._receiver(row)

    def test_disabled_external_or_inactive_mapping_is_denied(self) -> None:
        for identity in (
            frappe._dict(enabled=0, user_type="System User"),
            frappe._dict(enabled=1, user_type="Website User"),
            frappe._dict(status="Left", user_id="receiver@example.com"),
            frappe._dict(status="Active", user_id=None),
        ):
            with (
                self.subTest(identity=identity),
                patch.object(acceptance.frappe.db, "get_value", return_value=identity),
                self.assertRaises(frappe.ValidationError),
            ):
                acceptance._receiver(frappe._dict(to_employee="EMP", receiver_user="receiver@example.com"))

    def test_confirmation_identity_recheck_locks_employee_and_user(self) -> None:
        with patch.object(acceptance.frappe.db, "get_value", side_effect=self._lookup) as lookup:
            self.assertEqual(
                acceptance._receiver(
                    frappe._dict(to_employee="EMP", receiver_user="receiver@example.com"), lock_identity=True
                ),
                "receiver@example.com",
            )
        self.assertEqual([call.args[0] for call in lookup.call_args_list], ["Employee", "User"])
        self.assertTrue(all(call.kwargs["for_update"] for call in lookup.call_args_list))

    def test_receiver_validation_requires_rows_and_resolves_before_snapshot(self) -> None:
        doc = Document({"doctype": "Asset Movement", "assets": []})
        with self.assertRaises(frappe.ValidationError):
            acceptance.validate_receivers(doc)
        doc.append("assets", {"asset": "AST", "to_employee": "EMP"})
        with patch.object(acceptance.frappe.db, "get_value", side_effect=self._lookup):
            acceptance.validate_receivers(doc)
        self.assertEqual(doc.get("assets")[0].receiver_user, "receiver@example.com")

    def test_parent_evidence_spoof_and_submitted_recipient_mutation_denied(self) -> None:
        previous = Document(
            {
                "doctype": "Asset Movement",
                "docstatus": 1,
                "assets": [{"name": "ROW", "asset": "AST", "receiver_user": "receiver@example.com"}],
            }
        )
        for change in (
            {"accepted_by": "receiver@example.com"},
            {"receiver_user": "other@example.com"},
            {"asset": "OTHER"},
            {"installation_customer": "Customer"},
        ):
            doc = deepcopy(previous)
            doc.get("assets")[0].update(change)
            with (
                patch.object(doc, "get_doc_before_save", return_value=previous),
                self.assertRaises(frappe.ValidationError),
            ):
                acceptance.validate_receipt_evidence(doc)
        doc = deepcopy(previous)
        with patch.object(doc, "get_doc_before_save", return_value=previous):
            acceptance.validate_receipt_evidence(doc)
        doc.set("assets", [])
        with (
            patch.object(doc, "get_doc_before_save", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            acceptance.validate_receipt_evidence(doc)

    def test_standalone_child_lifecycle_always_denied(self) -> None:
        for method in ("before_insert", "validate", "before_update_after_submit", "on_trash"):
            with self.subTest(method=method), self.assertRaises(frappe.ValidationError):
                acceptance.deny_standalone_row_mutation(Document({"doctype": "Asset Movement Item"}), method)

    def test_confirmation_requires_interactive_permission_before_data(self) -> None:
        user = frappe.session.user
        request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = None
            with (
                patch.object(acceptance, "_", side_effect=lambda message: message),
                patch.object(acceptance.frappe.db, "get_value", wraps=frappe.db.get_value) as lookup,
                self.assertRaises(frappe.ValidationError),
            ):
                acceptance.confirm_receipt("AM", "ROW")
            self.assertFalse(
                any(
                    call.args
                    and call.args[0] in {"Asset Movement", "Asset Movement Item", "Employee", "User"}
                    for call in lookup.call_args_list
                )
            )
            frappe.set_user("receiver@example.com")
            frappe.local.request = frappe._dict(method="POST")
            with (
                patch.object(acceptance.frappe, "has_permission", return_value=False),
                patch.object(acceptance, "_", side_effect=lambda message: message),
                patch.object(acceptance.frappe.db, "get_value", wraps=frappe.db.get_value) as lookup,
                self.assertRaises(frappe.PermissionError),
            ):
                acceptance.confirm_receipt("AM", "ROW")
            self.assertFalse(
                any(
                    call.args
                    and call.args[0] in {"Asset Movement", "Asset Movement Item", "Employee", "User"}
                    for call in lookup.call_args_list
                )
            )
        finally:
            frappe.set_user(user)
            frappe.local.request = request
