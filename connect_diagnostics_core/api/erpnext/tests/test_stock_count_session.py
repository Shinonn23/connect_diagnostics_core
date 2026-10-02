# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Focused unit checks for Count API input and evidence projection."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_count_session as api


class TestStockCountSessionAPI(UnitTestCase):
    def test_quantity_rejects_negative_nonfinite_and_boolean_values(self) -> None:
        for value in ("-1", "NaN", "Infinity", True, None):
            with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
                api._quantity(value)
        self.assertEqual(api._quantity("1.250"), Decimal("1.250"))

    def test_decision_reason_does_not_call_native_workflow(self) -> None:
        doc = cast(
            Any,
            frappe._dict(
                doctype="Stock Count Session",
                name="_Test Count Session",
                workflow_state="Pending Review",
                evidence_revision=1,
                snapshot_digest="sealed",
                scope=[frappe._dict(warehouse="_Test Warehouse")],
            ),
        )

        def set_doc_value(fieldname: str, value: object) -> None:
            doc[fieldname] = value

        def as_dict() -> dict[str, object]:
            return dict(doc)

        doc.set = set_doc_value
        doc.as_dict = as_dict
        doc.save = lambda: None
        with (
            patch.object(api, "_visible_session", return_value=doc),
            patch.object(api, "_current_session", return_value=doc),
            patch.object(api, "get_transitions", return_value=[{"action": "Return Count for Recount"}]),
            patch.object(api, "parent_write_grant") as grant,
            patch("frappe.model.workflow.apply_workflow") as native_apply,
            patch.object(api.frappe, "session", user="_test_checker@example.com"),
        ):
            grant.return_value.__enter__.return_value = None
            result = api.set_stock_count_decision_reason(
                "_Test Count Session", "Return Count for Recount", "Count again"
            )
        self.assertEqual(result["data"], {"action": "Return Count for Recount"})
        self.assertEqual(doc.pending_reason_text, "Count again")
        native_apply.assert_not_called()

    def test_unauthorized_decision_reason_never_saves_or_calls_native_workflow(self) -> None:
        with (
            patch.object(api, "_visible_session", side_effect=frappe.PermissionError),
            patch.object(api, "_current_session") as current_session,
            patch("frappe.model.workflow.apply_workflow") as native_apply,
        ):
            with self.assertRaises(frappe.PermissionError):
                api.set_stock_count_decision_reason(
                    "_Test Count Session", "Return Count for Recount", "Count again"
                )
        current_session.assert_not_called()
        native_apply.assert_not_called()

    def test_scope_read_requires_every_warehouse_and_company(self) -> None:
        doc = cast(
            Document,
            frappe._dict(
                company="COMP-A",
                scope=[frappe._dict(warehouse="WH-A"), frappe._dict(warehouse="WH-B")],
            ),
        )
        with patch.object(api, "_native_visible_scope", return_value=({"COMP-A"}, {"WH-A"})):
            self.assertFalse(api._scope_visible(doc, "count-user@example.com"))
        with patch.object(api, "_native_visible_scope", return_value=({"COMP-A"}, {"WH-A", "WH-B"})):
            self.assertTrue(api._scope_visible(doc, "count-user@example.com"))
        with patch.object(api, "_native_visible_scope", return_value=({"COMP-B"}, {"WH-A", "WH-B"})):
            self.assertFalse(api._scope_visible(doc, "count-user@example.com"))
