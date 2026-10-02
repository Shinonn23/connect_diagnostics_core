# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.rename_doc import rename_doc
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    require_location_warehouse,
)

TEST_NAME = "_Test Exact Storage Location"
RENAMED_NAME = "_Test Renamed Storage Location"
MERGE_NAME = "_Test Merge Target Storage Location"


class TestStorageLocation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        frappe.reload_doc("connect_diagnostics_stock", "doctype", "storage_location", force=True)
        # This suite uses the existing test-site Warehouse and creates its own Locations.
        # Frappe's automatic Warehouse dependency generator is unrelated to this master.
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()

    def tearDown(self) -> None:
        for name in (TEST_NAME, RENAMED_NAME, MERGE_NAME):
            if frappe.db.exists("Storage Location", name):
                frappe.delete_doc("Storage Location", name, force=True)
        super().tearDown()

    def _warehouse(self) -> str:
        warehouse = frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name")
        assert warehouse
        return str(warehouse)

    def _other_warehouse(self, source: str) -> str:
        warehouse = frappe.db.get_value(
            "Warehouse", {"is_group": 0, "disabled": 0, "name": ["!=", source]}, "name"
        )
        assert warehouse
        return str(warehouse)

    def test_names_document_by_code_and_requires_warehouse(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": self._warehouse()}
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.name, TEST_NAME)
        self.assertEqual(doc.warehouse, self._warehouse())

        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Storage Location", "location_code": "_Test Missing Warehouse"}
            ).insert(ignore_permissions=True)

    def test_rejects_missing_or_group_warehouse(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": "_Missing"}
            ).insert(ignore_permissions=True)
        group = frappe.db.get_value("Warehouse", {"is_group": 1}, "name")
        assert group
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": group}
            ).insert(ignore_permissions=True)

    def test_requires_current_warehouse_read_scope(self) -> None:
        with (
            patch.object(frappe, "has_permission", return_value=False),
            self.assertRaises(frappe.PermissionError),
        ):
            frappe.get_doc(
                {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": self._warehouse()}
            ).insert(ignore_permissions=True)

    def test_stock_user_has_read_only_master_permission(self) -> None:
        permissions = {row.role: row for row in frappe.get_meta("Storage Location").permissions}
        self.assertEqual(permissions["Stock User"].read, 1)
        self.assertFalse(permissions["Stock User"].write)
        self.assertEqual(permissions["Stock Manager"].write, 1)

    def test_transfer_rechecks_location_read_scope_and_owner(self) -> None:
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": self._warehouse()}
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            require_location_warehouse(TEST_NAME, "_Other Warehouse")
        with (
            patch.object(frappe, "has_permission", return_value=False),
            self.assertRaises(frappe.PermissionError),
        ):
            require_location_warehouse(TEST_NAME, self._warehouse())

    def test_ledger_history_blocks_warehouse_reassignment_including_cancelled_entries(self) -> None:
        source = self._warehouse()
        doc = frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": source}
        ).insert(ignore_permissions=True)
        doc.warehouse = self._other_warehouse(source)
        original_get_value = frappe.db.get_value

        def get_value(doctype: str, filters: object, *args: object, **kwargs: object) -> object:
            if doctype == "Stock Ledger Entry":
                return "SLE-CANCELLED"
            return original_get_value(doctype, filters, *args, **kwargs)

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value) as current_read,
            self.assertRaises(frappe.ValidationError),
        ):
            doc.validate()
        current_read.assert_any_call(
            "Stock Ledger Entry",
            {"storage_location": TEST_NAME},
            "name",
            for_update=True,
            wait=False,
        )
        self.assertEqual(frappe.db.get_value("Storage Location", TEST_NAME, "warehouse"), source)

    def test_unused_location_can_change_warehouse(self) -> None:
        source = self._warehouse()
        target = self._other_warehouse(source)
        doc = frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": source}
        ).insert(ignore_permissions=True)
        doc.warehouse = target
        doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Storage Location", TEST_NAME, "warehouse"), target)

    def test_ledger_history_blocks_native_rename_including_cancelled_entries(self) -> None:
        warehouse = self._warehouse()
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": warehouse}
        ).insert(ignore_permissions=True)
        original_get_value = frappe.db.get_value

        def get_value(doctype: str, filters: object, *args: object, **kwargs: object) -> object:
            if doctype == "Stock Ledger Entry":
                return "SLE-CANCELLED"
            return original_get_value(doctype, filters, *args, **kwargs)

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value) as current_read,
            self.assertRaises(frappe.ValidationError),
        ):
            rename_doc("Storage Location", TEST_NAME, RENAMED_NAME, ignore_permissions=True)
        current_read.assert_any_call(
            "Stock Ledger Entry",
            {"storage_location": TEST_NAME},
            "name",
            for_update=True,
            wait=False,
        )
        self.assertTrue(frappe.db.exists("Storage Location", TEST_NAME))
        self.assertFalse(frappe.db.exists("Storage Location", RENAMED_NAME))

    def test_native_merge_is_rejected_for_same_and_different_warehouse(self) -> None:
        source = self._warehouse()
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": source}
        ).insert(ignore_permissions=True)
        for target_warehouse in (source, self._other_warehouse(source)):
            frappe.get_doc(
                {
                    "doctype": "Storage Location",
                    "location_code": MERGE_NAME,
                    "warehouse": target_warehouse,
                }
            ).insert(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError):
                rename_doc("Storage Location", TEST_NAME, MERGE_NAME, merge=True, ignore_permissions=True)
            self.assertTrue(frappe.db.exists("Storage Location", TEST_NAME))
            self.assertTrue(frappe.db.exists("Storage Location", MERGE_NAME))
            frappe.delete_doc("Storage Location", MERGE_NAME, force=True)

    def test_unused_location_can_use_native_rename(self) -> None:
        warehouse = self._warehouse()
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": warehouse}
        ).insert(ignore_permissions=True)
        rename_doc("Storage Location", TEST_NAME, RENAMED_NAME, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("Storage Location", TEST_NAME))
        self.assertEqual(frappe.db.get_value("Storage Location", RENAMED_NAME, "location_code"), RENAMED_NAME)

    def test_ledger_history_blocks_force_delete(self) -> None:
        frappe.get_doc(
            {"doctype": "Storage Location", "location_code": TEST_NAME, "warehouse": self._warehouse()}
        ).insert(ignore_permissions=True)
        original_get_value = frappe.db.get_value

        def get_value(doctype: str, filters: object, *args: object, **kwargs: object) -> object:
            if doctype == "Stock Ledger Entry":
                return "SLE-CANCELLED"
            return original_get_value(doctype, filters, *args, **kwargs)

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            self.assertRaises(frappe.ValidationError),
        ):
            frappe.delete_doc("Storage Location", TEST_NAME, force=True, ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Storage Location", TEST_NAME))
