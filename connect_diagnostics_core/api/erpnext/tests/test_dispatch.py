# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
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

    @patch.object(dispatch.frappe.db, "get_value", return_value=("DSP-1", "Other", 1, "Dispatched"))
    @patch.object(dispatch.frappe, "has_permission", return_value=True)
    def test_company_mismatch_is_rejected(self, _permission: MagicMock, _get_value: MagicMock) -> None:
        with self.assertRaises(frappe.PermissionError):
            dispatch._locked_dispatch("DSP-1", "_Test Company")
