# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import print_actions


class FakeDocument(frappe._dict):
    def set(self, fieldname: str, value: Any) -> None:
        self[fieldname] = value


class TestPrintActionWorkflowTasks(UnitTestCase):
    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-0001",
            "employee_name": "Submitter",
            "approval_signature": "data:image/png;base64,signature",
        },
    )
    def test_captures_employee_time_and_signature_snapshot(
        self,
        get_value: MagicMock,
        msgprint: MagicMock,
        _now_datetime: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice"})

        print_actions.capture_submit_action(cast(Document, doc))

        self.assertEqual(doc["submit_by"], "EMP-0001")
        self.assertEqual(doc["submit_at"], datetime(2026, 9, 5, 10, 30, 0))
        self.assertEqual(doc["submit_signature"], "data:image/png;base64,signature")
        msgprint.assert_not_called()
        get_value.assert_called_once_with(
            "Employee",
            {"user_id": print_actions.frappe.session.user},
            ["name", "employee_name", "approval_signature"],
            as_dict=True,
        )

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={"name": "EMP-0001", "employee_name": "No Signature", "approval_signature": ""},
    )
    def test_missing_signature_warns_but_still_captures_employee_and_time(
        self,
        _get_value: MagicMock,
        msgprint: MagicMock,
        _now_datetime: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice"})

        print_actions.capture_submit_action(cast(Document, doc))

        self.assertEqual(doc["submit_by"], "EMP-0001")
        self.assertEqual(doc["submit_at"], datetime(2026, 9, 5, 10, 30, 0))
        self.assertEqual(doc["submit_signature"], "")
        msgprint.assert_called_once()
        self.assertEqual(msgprint.call_args.kwargs["indicator"], "orange")

    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(print_actions.frappe.db, "get_value", return_value=None)
    def test_missing_employee_warns_without_blocking_the_workflow_task(
        self, _get_value: MagicMock, msgprint: MagicMock
    ) -> None:
        doc = FakeDocument({"doctype": "Sales Invoice"})

        print_actions.capture_submit_action(cast(Document, doc))

        self.assertNotIn("submit_by", doc)
        self.assertNotIn("submit_at", doc)
        self.assertNotIn("submit_signature", doc)
        msgprint.assert_called_once()

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-0001",
            "employee_name": "Quotation Signatory",
            "approval_signature": "data:image/png;base64,signature",
        },
    )
    def test_signatory_and_signed_tasks_use_the_same_snapshot_writer(
        self,
        get_value: MagicMock,
        _msgprint: MagicMock,
        _now_datetime: MagicMock,
    ) -> None:
        quotation_doc = FakeDocument({"doctype": "Quotation"})
        wht_doc = FakeDocument({"doctype": "Withholding Tax Cert"})

        print_actions.capture_signatory_action(cast(Document, quotation_doc))
        print_actions.capture_signed_action(cast(Document, wht_doc))

        self.assertEqual(quotation_doc["signatory_by"], "EMP-0001")
        self.assertEqual(quotation_doc["signatory_signature"], "data:image/png;base64,signature")
        self.assertEqual(wht_doc["signed_by"], "EMP-0001")
        self.assertEqual(wht_doc["signed_signature"], "data:image/png;base64,signature")
        self.assertEqual(get_value.call_count, 2)

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-0001",
            "employee_name": "Warehouse Employee",
            "approval_signature": "data:image/png;base64,signature",
        },
    )
    def test_stock_entry_uses_submit_snapshot_writer(
        self, _get_value: MagicMock, _msgprint: MagicMock, _now_datetime: MagicMock
    ) -> None:
        doc = FakeDocument({"doctype": "Stock Entry"})

        print_actions.capture_submit_action(cast(Document, doc))

        self.assertEqual(doc["submit_by"], "EMP-0001")
        self.assertEqual(doc["submit_at"], datetime(2026, 9, 5, 10, 30, 0))
        self.assertEqual(doc["submit_signature"], "data:image/png;base64,signature")

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions.frappe, "msgprint")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-0001",
            "employee_name": "C-Level Approver",
            "approval_signature": "data:image/png;base64,signature",
        },
    )
    def test_material_request_and_capitalization_use_authorized_snapshot_writer(
        self, _get_value: MagicMock, _msgprint: MagicMock, _now_datetime: MagicMock
    ) -> None:
        for doctype in ("Material Request", "Asset Capitalization"):
            doc = FakeDocument({"doctype": doctype})

            print_actions.capture_authorized_action(cast(Document, doc))

            with self.subTest(doctype=doctype):
                self.assertEqual(doc["authorized_by"], "EMP-0001")
                self.assertEqual(doc["authorized_at"], datetime(2026, 9, 5, 10, 30, 0))
                self.assertEqual(doc["authorized_signature"], "data:image/png;base64,signature")
                self.assertNotIn("submit_by", doc)
