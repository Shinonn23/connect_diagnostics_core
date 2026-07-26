# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import retire_dksh_sales_settings as patch_module


class TestRetireDKSHSalesSettings(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module.frappe.db, "delete")
    @patch.object(patch_module.frappe, "delete_doc")
    @patch.object(patch_module.frappe.db, "exists", return_value=True)
    def test_removes_metadata_and_single_values_idempotently(
        self,
        mocked_exists: MagicMock,
        mocked_delete_doc: MagicMock,
        mocked_delete: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_exists, "exists")
        manager.attach_mock(mocked_delete_doc, "delete_doc")
        manager.attach_mock(mocked_delete, "delete")
        manager.attach_mock(mocked_clear_cache, "clear_cache")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.exists("DocType", patch_module.DKSH_SALES_SETTINGS_DOCTYPE),
                call.delete_doc(
                    "DocType",
                    patch_module.DKSH_SALES_SETTINGS_DOCTYPE,
                    force=True,
                    ignore_missing=True,
                ),
                call.delete("Singles", {"doctype": patch_module.DKSH_SALES_SETTINGS_DOCTYPE}),
                call.clear_cache(),
            ],
        )

    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module.frappe.db, "delete")
    @patch.object(patch_module.frappe, "delete_doc")
    @patch.object(patch_module.frappe.db, "exists", return_value=False)
    def test_removes_orphan_single_values_when_metadata_is_already_gone(
        self,
        _mocked_exists: MagicMock,
        mocked_delete_doc: MagicMock,
        mocked_delete: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        patch_module.execute()

        mocked_delete_doc.assert_not_called()
        mocked_delete.assert_called_once_with(
            "Singles", {"doctype": patch_module.DKSH_SALES_SETTINGS_DOCTYPE}
        )
