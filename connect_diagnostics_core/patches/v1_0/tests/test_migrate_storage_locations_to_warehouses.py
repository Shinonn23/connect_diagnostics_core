# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_storage_locations_to_warehouses as patch_module


class TestMigrateStorageLocationsToWarehouses(UnitTestCase):
    def test_no_op_when_storage_location_doctype_missing(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False) as mocked_exists,
            patch.object(patch_module.frappe, "get_all") as mocked_get_all,
        ):
            patch_module.execute()

        mocked_exists.assert_called_once_with("DocType", "Storage Location")
        mocked_get_all.assert_not_called()

    def test_skips_row_with_missing_parent_warehouse(self) -> None:
        location = frappe._dict(
            {
                "name": "LOC-001",
                "location_code": "LOC-001",
                "location_name": "Rack A",
                "warehouse": None,
            }
        )
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_all", return_value=[location]),
            patch.object(patch_module.frappe, "log_error") as mocked_log_error,
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_log_error.assert_called_once()
        mocked_get_doc.assert_not_called()

    def test_skips_row_when_parent_warehouse_has_no_company(self) -> None:
        location = frappe._dict(
            {
                "name": "LOC-002",
                "location_code": "LOC-002",
                "location_name": "Rack B",
                "warehouse": "Main Store - CD",
            }
        )

        def exists_side_effect(doctype, *args, **kwargs):
            if doctype == "DocType":
                return True
            if doctype == "Warehouse":
                return True
            return False

        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=exists_side_effect),
            patch.object(patch_module.frappe, "get_all", return_value=[location]),
            patch.object(patch_module.frappe.db, "get_value", return_value=None),
            patch.object(patch_module.frappe, "log_error") as mocked_log_error,
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_log_error.assert_called_once()
        mocked_get_doc.assert_not_called()

    def test_creates_warehouse_once_then_is_idempotent(self) -> None:
        location = frappe._dict(
            {
                "name": "LOC-003",
                "location_code": "LOC-003",
                "location_name": "Rack C",
                "warehouse": "Main Store - CD",
            }
        )

        def exists_side_effect(doctype, filters=None, *args, **kwargs):
            if doctype == "DocType":
                return True
            if doctype == "Warehouse" and isinstance(filters, str):
                return True
            if doctype == "Warehouse" and isinstance(filters, dict):
                return False  # the target leaf Warehouse does not exist yet
            return False

        mocked_new_warehouse = MagicMock()
        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=exists_side_effect),
            patch.object(patch_module.frappe, "get_all", return_value=[location]),
            patch.object(patch_module.frappe.db, "get_value", return_value="_Test Company"),
            patch.object(patch_module.frappe, "get_doc", return_value=mocked_new_warehouse) as mocked_get_doc,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_get_doc.assert_called_once_with(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Rack C",
                "parent_warehouse": "Main Store - CD",
                "company": "_Test Company",
                "is_group": 0,
            }
        )
        mocked_new_warehouse.insert.assert_called_once_with(ignore_permissions=True)

    def test_no_op_when_matching_warehouse_already_exists(self) -> None:
        location = frappe._dict(
            {
                "name": "LOC-004",
                "location_code": "LOC-004",
                "location_name": "Rack D",
                "warehouse": "Main Store - CD",
            }
        )
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_all", return_value=[location]),
            patch.object(patch_module.frappe.db, "get_value", return_value="_Test Company"),
            patch.object(patch_module.frappe, "get_doc") as mocked_get_doc,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "logger", return_value=MagicMock()),
        ):
            patch_module.execute()

        mocked_get_doc.assert_not_called()
