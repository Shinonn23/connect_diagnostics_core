# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import restore_thai_withholding_tax_fields as patch_module
from connect_diagnostics_core.patches.v1_0 import (
    rollback_restore_thai_withholding_tax_fields as rollback_module,
)


class TestRestoreThaiWithholdingTaxFields(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "create_custom_fields")
    def test_forward_patch_restores_dependency_contract(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        patch_module.execute()

        mocked_create_custom_fields.assert_called_once_with(
            patch_module.THAI_WITHHOLDING_CUSTOM_FIELDS,
            update=True,
            ignore_validate=True,
        )
        mocked_clear_cache.assert_called_once_with()

    def test_forward_patch_catalog_contains_every_required_field(self) -> None:
        actual = {
            doctype: tuple(field["fieldname"] for field in fields)
            for doctype, fields in patch_module.THAI_WITHHOLDING_CUSTOM_FIELDS.items()
        }

        self.assertEqual(actual, patch_module.THAI_WITHHOLDING_FIELDNAMES)

    def test_rollback_removes_every_restored_field_and_commits(self) -> None:
        with (
            patch.object(rollback_module, "_drop_old") as mocked_drop,
            patch.object(rollback_module.frappe.db, "commit") as mocked_commit,
        ):
            rollback_module.execute()

        self.assertEqual(
            mocked_drop.call_args_list,
            [
                call(doctype, fieldname)
                for doctype, fieldnames in patch_module.THAI_WITHHOLDING_FIELDNAMES.items()
                for fieldname in fieldnames
            ],
        )
        mocked_commit.assert_called_once_with()
