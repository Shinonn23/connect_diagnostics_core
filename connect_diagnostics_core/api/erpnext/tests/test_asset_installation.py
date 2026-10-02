# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import asset_installation as installation


class TestAssetInstallation(UnitTestCase):
    def test_customer_history_uses_first_accepted_baseline(self) -> None:
        first = {
            "installation_previous_customer": "Original",
            "installation_customer": "A",
            "docstatus": 1,
        }
        second = {
            "installation_previous_customer": "A",
            "installation_customer": "B",
            "docstatus": 1,
        }
        self.assertEqual(installation._current_responsibility([first, second]), "B")
        first["docstatus"] = 2
        self.assertEqual(installation._current_responsibility([first, second]), "B")
        second["docstatus"] = 2
        self.assertEqual(installation._current_responsibility([first, second]), "Original")

    def test_submitted_customer_change_requires_exact_one_use_capability(self) -> None:
        asset = Document({"doctype": "Asset", "name": "AST", "docstatus": 1, "customer": "New"})
        before = Document({"doctype": "Asset", "name": "AST", "docstatus": 1, "customer": "Old"})
        with (
            patch.object(asset, "get_doc_before_save", return_value=before),
            patch.object(
                installation.frappe.db,
                "get_value",
                side_effect=[
                    frappe._dict(docstatus=1, workflow_state="Asset Movement Submitted"),
                    frappe._dict(installation_customer="New", accepted_by=None, accepted_at=None),
                ],
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                installation.validate_customer_update(asset, "before_update_after_submit")
            with installation._customer_save_capability(asset, "MOV", "ROW", "Old", "New", "receipt"):
                installation.validate_customer_update(asset, "before_update_after_submit")
                with self.assertRaises(frappe.ValidationError):
                    installation.validate_customer_update(asset, "before_update_after_submit")

    def test_customer_capability_rejects_other_asset_and_other_field(self) -> None:
        asset = Document(
            {"doctype": "Asset", "name": "AST", "docstatus": 1, "customer": "New", "location": "Other"}
        )
        before = Document(
            {"doctype": "Asset", "name": "AST", "docstatus": 1, "customer": "Old", "location": "Original"}
        )
        with (
            patch.object(asset, "get_doc_before_save", return_value=before),
            self.assertRaises(frappe.ValidationError),
        ):
            with installation._customer_save_capability(asset, "MOV", "ROW", "Old", "New", "receipt"):
                installation.validate_customer_update(asset, "before_update_after_submit")

    def test_prior_customer_evidence_and_history_deletion_are_protected(self) -> None:
        doc = Document(
            {
                "doctype": "Asset Movement",
                "name": "MOV",
                "workflow_state": "Asset Movement Draft",
                "assets": [
                    {
                        "asset": "AST",
                        "installation_customer": "Customer",
                        "installation_previous_customer": "Forged",
                    }
                ],
            }
        )
        with (
            patch.object(doc, "get_doc_before_save", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            installation.validate_draft_evidence(doc, "validate")
        with (
            patch.object(installation.frappe.db, "exists", return_value="ROW"),
            self.assertRaises(frappe.ValidationError),
        ):
            installation.prevent_history_deletion(doc, "on_trash")

    def test_maker_capture_allows_only_server_captured_nonblank_previous_customer(self) -> None:
        previous = Document(
            {
                "doctype": "Asset Movement",
                "workflow_state": "Asset Movement Draft",
                "assets": [{"name": "ROW", "asset": "AST", "installation_customer": "New"}],
            }
        )
        doc = Document(
            {
                "doctype": "Asset Movement",
                "workflow_state": "Asset Movement Pending Review",
                "assets": [{"name": "ROW", "asset": "AST", "installation_customer": "New"}],
            }
        )
        with patch.object(doc, "get_doc_before_save", return_value=previous):
            doc.get("assets")[0].installation_previous_customer = "Old"
            with self.assertRaises(frappe.ValidationError):
                installation.validate_draft_evidence(doc, "validate")
            doc.get("assets")[0].installation_previous_customer = None
            with patch.object(
                installation,
                "validate_current_installation",
                side_effect=lambda target, capture: target.get("assets")[0].set(
                    "installation_previous_customer", "Old"
                ),
            ):
                installation.capture_maker_customer(doc)
            installation.validate_draft_evidence(doc, "validate")
            doc.get("assets")[0].installation_previous_customer = "Forged"
            with self.assertRaises(frappe.ValidationError):
                installation.validate_draft_evidence(doc, "validate")

    def test_cancel_restores_first_baseline_through_customer_save(self) -> None:
        doc = Document(
            {
                "doctype": "Asset Movement",
                "name": "MOV",
                "assets": [
                    {
                        "asset": "AST",
                        "name": "ROW",
                        "installation_customer": "A",
                        "accepted_at": "2026-10-02 10:00:00",
                    }
                ],
            }
        )
        asset = Document({"doctype": "Asset", "name": "AST"})
        with (
            patch.object(installation.frappe.db, "get_value", return_value="AST"),
            patch.object(installation.frappe, "get_doc", return_value=asset),
            patch.object(
                installation,
                "_history",
                return_value=[
                    {
                        "installation_previous_customer": "Original",
                        "installation_customer": "A",
                        "docstatus": 2,
                    }
                ],
            ),
            patch.object(installation, "_save_customer") as save,
        ):
            installation.restore_after_cancel(doc, "on_cancel")
        save.assert_called_once()
        self.assertEqual(save.call_args.args[3:], ("Original", "cancel"))

    def test_confirm_rejects_equal_timestamp_before_asset_write(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "MOV"})
        row = frappe._dict(asset="AST", name="ROW", installation_customer="A")
        with (
            patch.object(installation, "_history", return_value=[{"accepted_at": "2026-10-02 10:00:00"}]),
            patch.object(installation, "_save_customer") as save,
            self.assertRaises(frappe.ValidationError),
        ):
            installation.confirm_customer(
                doc, row, Document({"doctype": "Asset", "name": "AST"}), "2026-10-02 10:00:00"
            )
        save.assert_not_called()

    def test_installation_shape_checks_issue_location_and_transfer_custodian(self) -> None:
        asset = frappe._dict(company="C", location="L1", custodian="E1", customer="Prior", docstatus=1)

        def lookup(doctype: str, *args: object, **kwargs: object) -> object:
            del args, kwargs
            if doctype == "Asset":
                return asset
            if doctype == "Customer":
                return 0
            if doctype == "User":
                return frappe._dict(enabled=1, user_type="System User")
            return frappe._dict(company="C", status="Active", user_id="receiver@example.com")

        row = frappe._dict(
            asset="AST",
            target_location="L2",
            from_employee="E1",
            to_employee="E2",
            receiver_user="receiver@example.com",
            installation_customer="Customer",
        )
        with (
            patch.object(installation.frappe.db, "get_value", side_effect=lookup),
            patch.object(installation.frappe.db, "exists", return_value=True),
        ):
            issue = Document(
                {"doctype": "Asset Movement", "company": "C", "purpose": "Issue", "assets": [row]}
            )
            with self.assertRaises(frappe.ValidationError):
                installation.validate_current_installation(issue, capture=True)
            issue.get("assets")[0].target_location = "L1"
            installation.validate_current_installation(issue, capture=True)
            self.assertEqual(issue.get("assets")[0].installation_previous_customer, "Prior")
            transfer = Document(
                {"doctype": "Asset Movement", "company": "C", "purpose": "Transfer", "assets": [row]}
            )
            transfer.get("assets")[0].from_employee = "Wrong"
            with self.assertRaises(frappe.ValidationError):
                installation.validate_current_installation(transfer, capture=True)
