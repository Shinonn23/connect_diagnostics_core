# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import storage_location


class TestStorageLocationSetup(UnitTestCase):
    def _inventory_documents(self) -> list[tuple[str]]:
        return [
            ("Stock Entry Detail",),
            ("Purchase Receipt Item",),
            ("Delivery Note Item",),
            ("Serial and Batch Entry",),
        ]

    def _native_fields(self) -> list[frappe._dict]:
        with patch.object(
            storage_location, "get_inventory_documents", return_value=self._inventory_documents()
        ):
            expected = storage_location._expected_native_fields()
        return [
            frappe._dict(dt=doctype, fieldname=fieldname, fieldtype="Link", options="Storage Location")
            for doctype, fieldname in expected
        ]

    def test_creates_native_dimension_with_negative_stock_check(self) -> None:
        dimension = MagicMock()
        with (
            patch.object(storage_location.frappe, "get_all", return_value=[]),
            patch.object(storage_location.frappe.db, "get_value", return_value=None),
            patch.object(storage_location.frappe, "get_doc", return_value=dimension) as get_doc,
        ):
            storage_location._ensure_dimension()
        get_doc.assert_called_once_with(
            {
                "doctype": "Inventory Dimension",
                "dimension_name": "Storage Location",
                "reference_document": "Storage Location",
                "apply_to_all_doctypes": 1,
                "validate_negative_stock": 1,
            }
        )
        dimension.insert.assert_called_once_with(ignore_permissions=True)

    def test_matching_dimension_is_not_resaved(self) -> None:
        existing = frappe._dict(
            dimension_name="Storage Location",
            reference_document="Storage Location",
            source_fieldname="storage_location",
            target_fieldname="storage_location",
            apply_to_all_doctypes=1,
            validate_negative_stock=1,
        )
        with (
            patch.object(
                storage_location, "get_inventory_documents", return_value=self._inventory_documents()
            ),
            patch.object(storage_location.frappe, "get_all", side_effect=[[], self._native_fields()]),
            patch.object(storage_location.frappe.db, "get_value", return_value=existing),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_incompatible_dimension_stops_without_resaving(self) -> None:
        existing = frappe._dict(
            dimension_name="Storage Location",
            reference_document="Other",
            source_fieldname="storage_location",
            target_fieldname="storage_location",
            apply_to_all_doctypes=1,
            validate_negative_stock=1,
        )
        with (
            patch.object(storage_location.frappe, "get_all", return_value=[]),
            patch.object(storage_location.frappe.db, "get_value", return_value=existing),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_field_reference_collision_stops_creation(self) -> None:
        with (
            patch.object(
                storage_location.frappe,
                "get_all",
                side_effect=[[frappe._dict(fieldname="storage_location", fieldtype="Link", options="Other")]],
            ),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_same_reference_non_link_field_is_a_collision(self) -> None:
        with (
            patch.object(
                storage_location.frappe,
                "get_all",
                side_effect=[
                    [frappe._dict(fieldname="storage_location", fieldtype="Data", options="Storage Location")]
                ],
            ),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_partial_native_field_set_blocks_existing_dimension_rerun(self) -> None:
        existing = frappe._dict(
            dimension_name="Storage Location",
            reference_document="Storage Location",
            source_fieldname="storage_location",
            target_fieldname="storage_location",
            apply_to_all_doctypes=1,
            validate_negative_stock=1,
        )
        with (
            patch.object(
                storage_location, "get_inventory_documents", return_value=self._inventory_documents()
            ),
            patch.object(storage_location.frappe, "get_all", side_effect=[[], self._native_fields()[:1]]),
            patch.object(storage_location.frappe.db, "get_value", return_value=existing),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_orphan_native_field_blocks_new_dimension_creation(self) -> None:
        with (
            patch.object(storage_location.frappe, "get_all", side_effect=[[], self._native_fields()[:1]]),
            patch.object(storage_location.frappe.db, "get_value", return_value=None),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_missing_purchase_receipt_field_blocks_existing_dimension_rerun(self) -> None:
        existing = frappe._dict(
            dimension_name="Storage Location",
            reference_document="Storage Location",
            source_fieldname="storage_location",
            target_fieldname="storage_location",
            apply_to_all_doctypes=1,
            validate_negative_stock=1,
        )
        native_fields = [
            field
            for field in self._native_fields()
            if (field.dt, field.fieldname) != ("Purchase Receipt Item", "storage_location")
        ]
        self.assertTrue(
            {
                ("Stock Entry Detail", "storage_location"),
                ("Stock Entry Detail", "to_storage_location"),
                ("Stock Ledger Entry", "storage_location"),
                ("Stock Closing Balance", "storage_location"),
            }.issubset({(field.dt, field.fieldname) for field in native_fields})
        )
        with (
            patch.object(
                storage_location, "get_inventory_documents", return_value=self._inventory_documents()
            ),
            patch.object(storage_location.frappe, "get_all", side_effect=[[], native_fields]),
            patch.object(storage_location.frappe.db, "get_value", return_value=existing),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            storage_location._ensure_dimension()
        get_doc.assert_not_called()

    def test_repositions_generated_field_once_after_warehouse(self) -> None:
        field = frappe.get_doc({"doctype": "Custom Field", "insert_after": "inventory_dimension"})
        generated = frappe._dict(
            name="Stock Entry Detail-storage_location",
            dt="Stock Entry Detail",
            fieldname="storage_location",
            insert_after="inventory_dimension",
        )
        meta = MagicMock()
        meta.get_field.side_effect = lambda name: object() if name == "s_warehouse" else None
        with (
            patch.object(storage_location.frappe, "get_all", return_value=[generated]),
            patch.object(storage_location.frappe, "get_meta", return_value=meta),
            patch.object(storage_location.frappe, "get_doc", return_value=field),
            patch.object(field, "save") as save,
        ):
            storage_location.reposition_dimension_fields()
        self.assertEqual(field.insert_after, "s_warehouse")
        save.assert_called_once_with(ignore_permissions=True)

    def test_reposition_rerun_preserves_existing_anchor(self) -> None:
        generated = frappe._dict(
            name="Stock Entry Detail-storage_location",
            dt="Stock Entry Detail",
            fieldname="storage_location",
            insert_after="s_warehouse",
        )
        meta = MagicMock()
        meta.get_field.side_effect = lambda name: object() if name == "s_warehouse" else None
        with (
            patch.object(storage_location.frappe, "get_all", return_value=[generated]),
            patch.object(storage_location.frappe, "get_meta", return_value=meta),
            patch.object(storage_location.frappe, "get_doc") as get_doc,
        ):
            storage_location.reposition_dimension_fields()
        get_doc.assert_not_called()
