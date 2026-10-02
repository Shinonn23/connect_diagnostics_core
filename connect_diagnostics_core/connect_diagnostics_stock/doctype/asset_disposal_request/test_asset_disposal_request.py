# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from connect_diagnostics_core.api.erpnext.tests.test_asset_movement_workflow import (
    TestAssetMovementWorkflowIntegration,
)


class TestAssetDisposalRequest(IntegrationTestCase):
    _location = TestAssetMovementWorkflowIntegration._location
    _asset = TestAssetMovementWorkflowIntegration._asset

    def setUp(self) -> None:
        super().setUp()
        old_user = frappe.session.user
        self.addCleanup(lambda: frappe.set_user(old_user))
        frappe.set_user("Administrator")
        location = self._location(f"Disposal {uuid4().hex[:8]}")
        self.asset = self._asset(location)
        self.asset.db_set("asset_quantity", 1)

    def _draft(self):
        return frappe.get_doc(
            {
                "doctype": "Asset Disposal Request",
                "purpose": "Scrap",
                "reason": "Equipment is beyond repair",
                "asset": self.asset.name,
                "request_date": today(),
                "disposal_date": today(),
            }
        ).insert()

    def test_draft_derives_company_and_whole_asset_quantity(self) -> None:
        request = self._draft()
        self.assertEqual(request.company, self.asset.company)
        self.assertEqual(request.asset_quantity, 1)
        self.assertEqual(request.docstatus, 0)

    def test_client_cannot_inject_execution_result_or_child_link(self) -> None:
        request = self._draft()
        request.disposal_status = "Closed"
        with self.assertRaises(frappe.ValidationError):
            request.save()
        fresh = frappe.get_doc("Asset Disposal Request", request.name)
        self.assertEqual(fresh.disposal_status, "Not Executed")
        fresh.append(
            "generated_journal_entries",
            {
                "journal_entry": "JE-FORGED",
                "operation_id": "FORGED",
                "kind": "depreciation",
                "stage": "pre_disposal_depreciation",
                "posting_date": today(),
                "source_proof": "FORGED",
            },
        )
        with self.assertRaises(frappe.ValidationError):
            fresh.save()

    def test_forged_closed_insert_cannot_release_an_asset_reservation(self) -> None:
        forged = frappe.get_doc(
            {
                "doctype": "Asset Disposal Request",
                "purpose": "Scrap",
                "reason": "Forged result",
                "asset": self.asset.name,
                "request_date": today(),
                "disposal_date": today(),
                "disposal_status": "Closed",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            forged.insert()
        self.assertFalse(
            frappe.db.exists(
                "Asset Disposal Request", {"asset": self.asset.name, "disposal_status": "Closed"}
            )
        )
