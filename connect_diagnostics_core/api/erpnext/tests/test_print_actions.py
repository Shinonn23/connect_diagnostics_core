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
            {"user_id": print_actions.frappe.session.user, "status": "Active"},
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

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 26, 10, 30, 0))
    @patch.object(print_actions, "require_distinct_actors")
    @patch.object(print_actions, "require_permission")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-REVIEWER",
            "employee_name": "Purchase Reviewer",
            "approval_signature": "data:image/png;base64,reviewer",
        },
    )
    @patch("connect_diagnostics_core.api.erpnext.purchase_order_workflow.capture_review_snapshot")
    def test_purchase_order_review_is_protected_signed_and_bound_to_current_payload(
        self,
        capture_review_snapshot: MagicMock,
        _get_value: MagicMock,
        require_permission: MagicMock,
        require_distinct_actors: MagicMock,
        _now_datetime: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Purchase Order", "owner": "maker@example.com"})

        print_actions.capture_checked_action(cast(Document, doc))

        self.assertEqual(doc["checked_by"], "EMP-REVIEWER")
        self.assertEqual(doc["checked_signature"], "data:image/png;base64,reviewer")
        require_permission.assert_called_once_with(doc)
        require_distinct_actors.assert_called_once()
        capture_review_snapshot.assert_called_once_with(doc)

    @patch.object(print_actions, "require_distinct_actors")
    @patch.object(print_actions, "require_permission")
    @patch.object(print_actions.frappe.db, "get_value", return_value=None)
    def test_purchase_order_review_without_employee_fails_closed(
        self,
        _get_value: MagicMock,
        _require_permission: MagicMock,
        _require_distinct_actors: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Purchase Order", "owner": "maker@example.com"})

        with self.assertRaises(frappe.ValidationError):
            print_actions.capture_checked_action(cast(Document, doc))

    @patch.object(print_actions, "require_distinct_actors")
    @patch.object(print_actions, "require_permission")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={
            "name": "EMP-APPROVER",
            "employee_name": "Purchase Approver",
            "approval_signature": "",
        },
    )
    def test_purchase_order_approval_without_signature_fails_closed(
        self,
        _get_value: MagicMock,
        _require_permission: MagicMock,
        _require_distinct_actors: MagicMock,
    ) -> None:
        doc = FakeDocument({"doctype": "Purchase Order", "owner": "maker@example.com"})

        with self.assertRaises(frappe.ValidationError):
            print_actions.capture_authorized_action(cast(Document, doc))

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

    @patch.object(print_actions, "now_datetime", return_value=datetime(2026, 9, 5, 10, 30, 0))
    @patch.object(print_actions, "require_distinct_actors")
    @patch.object(print_actions, "require_permission")
    @patch.object(
        print_actions.frappe.db,
        "get_value",
        return_value={"name": "EMP-0001", "employee_name": "Approver", "approval_signature": "signed"},
    )
    def test_non_stock_approval_does_not_apply_stock_separation_of_duties(
        self,
        _get_value: MagicMock,
        require_permission: MagicMock,
        require_distinct_actors: MagicMock,
        _now_datetime: MagicMock,
    ) -> None:
        doc = FakeDocument(
            {
                "doctype": "Sales Order",
                "owner": print_actions.frappe.session.user,
                "authorized_by": "client",
                "authorized_signature": "fake",
            }
        )
        print_actions.capture_authorized_action(cast(Document, doc))
        require_permission.assert_called_once_with(doc)
        require_distinct_actors.assert_not_called()
        self.assertEqual(doc["authorized_by"], "EMP-0001")
        self.assertEqual(doc["authorized_signature"], "signed")

    @patch.object(print_actions, "require_permission")
    @patch.object(print_actions, "now_datetime")
    @patch.object(print_actions.frappe.db, "get_value")
    def test_reapproval_replaces_only_the_current_snapshot(
        self,
        get_value: MagicMock,
        now_datetime: MagicMock,
        _require_permission: MagicMock,
    ) -> None:
        get_value.side_effect = [
            {"name": "EMP-0001", "employee_name": "First", "approval_signature": "first"},
            {"name": "EMP-0002", "employee_name": "Second", "approval_signature": "second"},
        ]
        now_datetime.side_effect = [
            datetime(2026, 9, 5, 10, 30, 0),
            datetime(2026, 9, 6, 11, 45, 0),
        ]
        doc = FakeDocument({"doctype": "Sales Order"})

        print_actions.capture_authorized_action(cast(Document, doc))
        first_snapshot = (doc["authorized_by"], doc["authorized_at"], doc["authorized_signature"])
        print_actions.capture_authorized_action(cast(Document, doc))

        self.assertEqual(first_snapshot, ("EMP-0001", datetime(2026, 9, 5, 10, 30, 0), "first"))
        self.assertEqual(
            (doc["authorized_by"], doc["authorized_at"], doc["authorized_signature"]),
            ("EMP-0002", datetime(2026, 9, 6, 11, 45, 0), "second"),
        )
