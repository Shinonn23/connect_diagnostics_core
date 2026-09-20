# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    add_material_request_demo_fulfillment_fields,
    remove_material_request_submit_checked_snapshots,
    validate_material_request_usage_split,
)


class TestMaterialRequestDemoFulfillmentPatches(UnitTestCase):
    def test_add_patch_does_not_claim_preexisting_request_fields(self) -> None:
        fieldnames = {
            field["fieldname"]
            for field in add_material_request_demo_fulfillment_fields.NEW_FIELDS["Material Request"]
        }

        self.assertNotIn("purchase_reason", fieldnames)
        self.assertNotIn("supporting_document_complete", fieldnames)
        self.assertEqual(len(fieldnames), 7)

    def test_snapshot_patch_keeps_authorized_fields(self) -> None:
        removed = {
            fieldname
            for fieldname, _fieldtype, _options in remove_material_request_submit_checked_snapshots.REMOVED_FIELDS
        }

        self.assertNotIn("authorized_by", removed)
        self.assertNotIn("authorized_at", removed)
        self.assertNotIn("authorized_signature", removed)

    @patch.object(validate_material_request_usage_split.frappe, "get_all", return_value=["MR-1"])
    @patch.object(validate_material_request_usage_split.frappe.db, "has_column", return_value=True)
    def test_combined_demo_loan_value_blocks_migration(
        self, _has_column: MagicMock, _get_all: MagicMock
    ) -> None:
        with self.assertRaises(frappe.ValidationError):
            validate_material_request_usage_split.execute()
