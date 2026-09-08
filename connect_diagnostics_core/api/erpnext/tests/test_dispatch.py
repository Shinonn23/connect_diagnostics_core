# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import dispatch


class TestDispatchApi(UnitTestCase):
    @patch.object(dispatch, "_locked_dispatch")
    def test_confirm_delivery_persists_pod(self, locked: MagicMock) -> None:
        doc = MagicMock()
        doc.as_dict.return_value = {"name": "DSP-1", "delivery_status": "Delivered"}
        locked.return_value = doc

        result = dispatch.confirm_dispatch_delivery(
            "DSP-1", "_Test Company", "Receiver", "data:image/png;base64,AA=="
        )

        doc.set.assert_any_call("delivery_status", "Delivered")
        doc.set.assert_any_call("receiver_name", "Receiver")
        doc.save.assert_called_once_with()
        self.assertEqual(result["data"]["delivery_status"], "Delivered")

    @patch.object(dispatch, "_locked_dispatch")
    def test_confirm_delivery_requires_signature(self, locked: MagicMock) -> None:
        locked.return_value = MagicMock()

        with self.assertRaises(frappe.ValidationError):
            dispatch.confirm_dispatch_delivery("DSP-1", "_Test Company", "Receiver", "")

    @patch.object(dispatch, "_locked_dispatch")
    def test_report_failure_requires_note(self, locked: MagicMock) -> None:
        locked.return_value = MagicMock()

        with self.assertRaises(frappe.ValidationError):
            dispatch.report_dispatch_failure("DSP-1", "_Test Company", "")

    @patch.object(dispatch, "_locked_dispatch")
    def test_report_failure_persists_failure_state(self, locked: MagicMock) -> None:
        doc = MagicMock()
        doc.as_dict.return_value = {"name": "DSP-1", "delivery_status": "Failed"}
        locked.return_value = doc

        result = dispatch.report_dispatch_failure("DSP-1", "_Test Company", "Recipient unavailable")

        doc.set.assert_any_call("delivery_status", "Failed")
        doc.set.assert_any_call("delivery_note", "Recipient unavailable")
        doc.save.assert_called_once_with()
        self.assertEqual(result["data"]["delivery_status"], "Failed")

    @patch.object(dispatch, "_create_return_to_origin")
    @patch.object(dispatch, "_locked_dispatch")
    def test_failed_return_can_be_recovered_without_stopping_material_request(
        self, locked: MagicMock, recover: MagicMock
    ) -> None:
        doc = MagicMock()
        values = {
            "dispatch_type": "Return",
            "delivery_status": "Failed",
            "material_request": "MR-1",
        }
        doc.get.side_effect = values.get
        doc.as_dict.return_value = {"delivery_status": "Returned to Origin"}
        locked.return_value = doc

        result = dispatch.return_dispatch_to_origin("DSP-RETURN", "_Test Company", "Carrier rejected parcel")

        recover.assert_called_once_with(doc)
        doc.set.assert_any_call("delivery_status", "Returned to Origin")
        self.assertEqual(result["data"]["delivery_status"], "Returned to Origin")

    @patch.object(dispatch, "_validate_asset_delivery_movements")
    @patch.object(dispatch, "_create_end_transit_stock_entry")
    def test_asset_delivery_reuses_submitted_asset_movement(
        self, end_transit: MagicMock, validate_asset: MagicMock
    ) -> None:
        doc = Document({"doctype": "Dispatch", "transfers": []})

        dispatch._create_delivery_movements(doc)

        end_transit.assert_called_once_with(doc)
        validate_asset.assert_called_once_with(doc)

    @patch.object(dispatch, "now_datetime", return_value="2026-09-08 10:00:00")
    @patch.object(dispatch.frappe, "new_doc")
    def test_asset_only_return_to_origin_creates_recovery_movement(
        self, new_doc: MagicMock, _now: MagicMock
    ) -> None:
        movement = MagicMock(name="AM-RECOVERY")
        movement.name = "AM-RECOVERY"
        new_doc.return_value = movement
        doc = Document(
            {
                "doctype": "Dispatch",
                "name": "DSP-OUT",
                "company": "_Test Company",
                "material_request": "MR-1",
                "dispatch_type": "Outbound",
            }
        )
        doc.set("transfers", [frappe._dict(asset="AST-1", original_source_location="LOC-1")])

        dispatch._create_recovery_asset_movement(doc)

        movement.append.assert_called_once_with("assets", {"asset": "AST-1", "target_location": "LOC-1"})
        movement.insert.assert_called_once_with()
        movement.submit.assert_called_once_with()
        self.assertEqual(doc.get("recovery_asset_movement"), "AM-RECOVERY")

    @patch.object(dispatch.frappe.db, "get_value", return_value=("DSP-1", "Other", 1, "Dispatched"))
    @patch.object(dispatch.frappe, "has_permission", return_value=True)
    def test_company_mismatch_is_rejected(self, _permission: MagicMock, _get_value: MagicMock) -> None:
        with self.assertRaises(frappe.PermissionError):
            dispatch._locked_dispatch("DSP-1", "_Test Company")
