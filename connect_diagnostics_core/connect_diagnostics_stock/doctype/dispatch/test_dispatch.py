# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.dispatch.dispatch import Dispatch


class TestDispatch(UnitTestCase):
    def test_before_submit_starts_dispatched_state(self) -> None:
        values = {"delivery_status": "Draft", "dispatched_at": None}
        doc = MagicMock()
        doc.get.side_effect = values.get
        doc.set.side_effect = lambda key, value: values.__setitem__(key, value)

        Dispatch.before_submit(doc)

        doc._lock_and_revalidate_return_quantities.assert_called_once_with()
        doc._validate_asset_availability.assert_called_once_with()
        self.assertEqual(values["delivery_status"], "Dispatched")
        self.assertIsNotNone(values["dispatched_at"])

    def test_retry_must_reuse_original_movement_and_quantity(self) -> None:
        doc = MagicMock()
        doc.get.side_effect = {"original_dispatch": "DSP-OUT", "dispatch_type": "Retry"}.get
        row = frappe._dict(
            idx=1,
            material_request_item="MRI-1",
            item_code="ITEM-1",
            asset=None,
            reference_doctype="Stock Entry",
            reference_name="SE-2",
            qty=1,
            against_dispatch_transfer="ROW-1",
        )
        original = frappe._dict(
            parent="DSP-OUT",
            material_request_item="MRI-1",
            item_code="ITEM-1",
            asset=None,
            reference_doctype="Stock Entry",
            reference_name="SE-1",
            qty=1,
        )
        with patch.object(frappe.db, "get_value", return_value=original):
            with self.assertRaises(frappe.ValidationError):
                Dispatch._validate_against_outbound(doc, cast(Document, row))

    def test_asset_quantity_must_be_one(self) -> None:
        doc = MagicMock()
        doc.get.side_effect = {"material_request": "MR-1", "company": "_Test Company"}.get
        row = frappe._dict(
            idx=1,
            asset="AST-1",
            qty=2,
            reference_doctype="Asset Movement",
        )

        with self.assertRaises(frappe.ValidationError):
            Dispatch._validate_asset_transfer(doc, cast(Document, row), frappe._dict(allocated_asset="AST-1"))

    @patch.object(frappe, "get_all")
    def test_return_stock_entry_must_reverse_original_warehouses(self, get_all: MagicMock) -> None:
        get_all.side_effect = [
            [frappe._dict(s_warehouse="Stores - TC", t_warehouse="Demo - TC")],
            [frappe._dict(s_warehouse="Demo - TC", t_warehouse="Stores - TC")],
        ]
        doc = MagicMock()
        row = frappe._dict(
            idx=1,
            item_code="ITEM-1",
            material_request_item="MRI-1",
            reference_name="SE-RETURN",
        )
        original = frappe._dict(reference_name="SE-OUT")

        Dispatch._validate_reversed_stock_movement(doc, cast(Document, row), original)

    @patch.object(frappe, "get_all")
    def test_return_stock_entry_rejects_another_target_warehouse(self, get_all: MagicMock) -> None:
        get_all.side_effect = [
            [frappe._dict(s_warehouse="Stores - TC", t_warehouse=None)],
            [frappe._dict(s_warehouse=None, t_warehouse="Other - TC")],
        ]
        doc = MagicMock()
        row = frappe._dict(
            idx=1,
            item_code="ITEM-1",
            material_request_item="MRI-1",
            reference_name="SE-RETURN",
        )

        with self.assertRaises(frappe.ValidationError):
            Dispatch._validate_reversed_stock_movement(
                doc, cast(Document, row), frappe._dict(reference_name="SE-OUT")
            )

    def test_submitted_status_cannot_bypass_controlled_post_api(self) -> None:
        before = frappe._dict(delivery_status="Dispatched")
        doc = MagicMock()
        doc.docstatus = 1
        doc.flags = frappe._dict()
        doc.get_doc_before_save.return_value = before
        values = {
            "delivery_status": "Delivered",
            "received_at": "2026-09-07 10:00:00",
            "receiver_name": "Receiver",
            "receiver_contact": None,
            "receiver_signature": "signature",
            "delivery_note": None,
        }
        doc.get.side_effect = values.get

        with self.assertRaises(frappe.ValidationError):
            Dispatch._validate_post_submit_mutation(doc)
