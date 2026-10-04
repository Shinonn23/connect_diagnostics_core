# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    add_material_request_stock_entry_print_signature_snapshots,
    rollback_add_material_request_stock_entry_print_signature_snapshots,
)


class TestStockEntryPrintSignatureSnapshots(UnitTestCase):
    @patch.object(add_material_request_stock_entry_print_signature_snapshots, "create_custom_fields")
    def test_forward_patch_creates_stock_entry_field_set(
        self, mocked_create_custom_fields: MagicMock
    ) -> None:
        add_material_request_stock_entry_print_signature_snapshots.execute()

        mocked_create_custom_fields.assert_called_once_with(
            add_material_request_stock_entry_print_signature_snapshots.NEW_PRINT_SIGNATURE_FIELDS,
            update=True,
            ignore_validate=True,
        )

    @patch.object(
        rollback_add_material_request_stock_entry_print_signature_snapshots.frappe.db,
        "has_column",
        return_value=False,
    )
    @patch.object(
        rollback_add_material_request_stock_entry_print_signature_snapshots.frappe.db,
        "exists",
        return_value=False,
    )
    @patch.object(rollback_add_material_request_stock_entry_print_signature_snapshots.frappe.db, "commit")
    def test_rollback_is_idempotent_when_fields_are_already_absent(
        self, mocked_commit: MagicMock, mocked_exists: MagicMock, mocked_has_column: MagicMock
    ) -> None:
        rollback_add_material_request_stock_entry_print_signature_snapshots.execute()

        self.assertEqual(mocked_exists.call_count, 18)
        self.assertEqual(mocked_has_column.call_count, 18)
        mocked_commit.assert_called_once_with()
