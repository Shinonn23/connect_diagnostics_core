# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import clear_legacy_tds_values as patch_module


class TestClearLegacyTDSValues(UnitTestCase):
    def test_submitted_documents_are_force_cleared_and_committed(self) -> None:
        submitted = {"doctype": "Purchase Invoice", "name": "PI-0001", "docstatus": 1}

        with (
            patch.object(patch_module, "_find_candidates", return_value=[submitted]),
            patch.object(patch_module, "_clear_candidate") as mocked_clear,
            patch.object(patch_module.frappe.db, "commit") as mocked_commit,
        ):
            patch_module.execute()

        mocked_clear.assert_called_once_with(submitted)
        mocked_commit.assert_called_once_with()

    def test_draft_documents_are_cleared_and_committed(self) -> None:
        candidates = [
            {"doctype": "Supplier", "name": "SUP-0001", "docstatus": 0},
            {"doctype": "Purchase Invoice", "name": "PI-0001", "docstatus": 0},
        ]

        with (
            patch.object(patch_module, "_find_candidates", return_value=candidates),
            patch.object(patch_module, "_clear_candidate") as mocked_clear,
            patch.object(patch_module.frappe.db, "commit") as mocked_commit,
        ):
            patch_module.execute()

        self.assertEqual(
            [call.args for call in mocked_clear.call_args_list], [(candidates[0],), (candidates[1],)]
        )
        mocked_commit.assert_called_once_with()
