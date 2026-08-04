# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import replace_quotation_validity_mode as patch_module
from connect_diagnostics_core.setup import customer as customer_setup


class TestReplaceQuotationValidityMode(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "delete_custom_fields")
    @patch.object(patch_module, "_migrate_custom_validity_overrides")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_migrates_overrides_before_retiring_customer_mode(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_migrate_overrides: MagicMock,
        mocked_delete_custom_fields: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        patch_module.execute()

        mocked_create_custom_fields.assert_called_once_with(
            customer_setup.CUSTOM_FIELDS, ignore_validate=True
        )
        mocked_migrate_overrides.assert_has_calls(
            [
                call("Customer"),
                call("Print Configuration Template"),
            ]
        )
        mocked_delete_custom_fields.assert_called_once_with(
            {"Customer": ["quotation_validity_mode"]}, bypass_hooks=True
        )
        mocked_clear_cache.assert_called_once_with()

    @patch.object(patch_module.frappe.db, "bulk_update")
    @patch.object(patch_module.frappe.qb, "from_")
    @patch.object(patch_module.frappe.qb, "DocType")
    @patch.object(patch_module.frappe.db, "has_column", return_value=True)
    def test_custom_text_mode_becomes_an_override(
        self,
        _mocked_has_column: MagicMock,
        mocked_doctype: MagicMock,
        mocked_from: MagicMock,
        mocked_bulk_update: MagicMock,
    ) -> None:
        mocked_doctype.return_value = MagicMock()
        mocked_from.return_value.select.return_value.where.return_value.run.return_value = [
            {"name": "CUST-0001"}
        ]

        patch_module._migrate_custom_validity_overrides("Customer")

        mocked_bulk_update.assert_called_once_with(
            "Customer",
            {"CUST-0001": {"override_quotation_validity_text": 1}},
            update_modified=False,
        )
