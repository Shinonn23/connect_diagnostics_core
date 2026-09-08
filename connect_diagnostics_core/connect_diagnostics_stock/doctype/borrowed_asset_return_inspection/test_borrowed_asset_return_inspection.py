# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.borrowed_asset_return_inspection.borrowed_asset_return_inspection import (
    BorrowedAssetReturnInspection,
)


class TestBorrowedAssetReturnInspection(UnitTestCase):
    def test_accepted_result_rejects_failed_check(self) -> None:
        doc = MagicMock()
        doc.get.side_effect = {
            "checks": [frappe._dict(result="Fail")],
            "inspection_result": "Accepted",
        }.get

        with self.assertRaises(frappe.ValidationError):
            BorrowedAssetReturnInspection._validate_result(doc)

    def test_rejected_result_requires_damage_note(self) -> None:
        doc = MagicMock()
        doc.get.side_effect = {
            "checks": [frappe._dict(result="Fail")],
            "inspection_result": "Rejected",
            "damage_note": None,
        }.get

        with self.assertRaises(frappe.ValidationError):
            BorrowedAssetReturnInspection._validate_result(doc)

    def test_accepted_result_allows_all_passed_checks(self) -> None:
        doc = MagicMock()
        doc.get.side_effect = {
            "checks": [frappe._dict(result="Pass")],
            "inspection_result": "Accepted",
        }.get

        BorrowedAssetReturnInspection._validate_result(doc)
