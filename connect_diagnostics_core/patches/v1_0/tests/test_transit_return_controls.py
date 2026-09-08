# Copyright (c) 2026, Siwat Sroisuwan and contributors

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_transit_return_controls, rename_demo_return_inspection


class TestTransitReturnControls(UnitTestCase):
    def test_new_fields_cover_employee_company_native_movements(self) -> None:
        self.assertIn(
            "borrow_warehouse",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Employee"]},
        )
        self.assertIn(
            "borrow_in_transit_warehouse",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Company"]},
        )
        self.assertIn(
            "return_dispatch_transfer",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Quality Inspection"]},
        )

    def test_rename_is_deterministic(self) -> None:
        self.assertEqual(
            rename_demo_return_inspection.RENAMES[0][1:],
            ("Demo Return Inspection", "Borrowed Asset Return Inspection"),
        )

    @patch.object(rename_demo_return_inspection.frappe, "delete_doc")
    @patch.object(rename_demo_return_inspection.frappe.db, "sql_ddl")
    @patch.object(rename_demo_return_inspection.frappe.db, "count", return_value=0)
    @patch.object(rename_demo_return_inspection.frappe.db, "table_exists", return_value=True)
    def test_partial_model_sync_target_is_removed_only_when_empty(
        self,
        _table_exists: MagicMock,
        _count: MagicMock,
        sql_ddl: MagicMock,
        delete_doc: MagicMock,
    ) -> None:
        rename_demo_return_inspection._drop_empty_synced_target("Borrowed Asset Return Inspection")

        delete_doc.assert_called_once_with(
            "DocType", "Borrowed Asset Return Inspection", force=True, ignore_permissions=True
        )
        sql_ddl.assert_called_once()

    @patch.object(rename_demo_return_inspection.frappe, "delete_doc")
    @patch.object(rename_demo_return_inspection.frappe.db, "count", return_value=1)
    @patch.object(rename_demo_return_inspection.frappe.db, "table_exists", return_value=True)
    def test_non_empty_model_sync_target_aborts_migration(
        self, _table_exists: MagicMock, _count: MagicMock, delete_doc: MagicMock
    ) -> None:
        with self.assertRaises(frappe.ValidationError):
            rename_demo_return_inspection._drop_empty_synced_target("Borrowed Asset Return Inspection")

        delete_doc.assert_not_called()
