# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_print_configuration_templates as patch_module
from connect_diagnostics_core.setup import customer as customer_setup


class TestMigratePrintConfigurationTemplates(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "delete_custom_fields")
    @patch.object(patch_module, "_link_existing_customers")
    @patch.object(patch_module, "_ensure_default_template")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_preserves_customer_values_and_removes_quotation_snapshots(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_ensure_template: MagicMock,
        mocked_link_customers: MagicMock,
        mocked_delete_custom_fields: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        patch_module.execute()

        mocked_create_custom_fields.assert_called_once_with(
            customer_setup.CUSTOM_FIELDS, ignore_validate=True
        )
        mocked_ensure_template.assert_called_once_with()
        mocked_link_customers.assert_called_once_with()
        mocked_delete_custom_fields.assert_called_once_with(
            {"Quotation": list(patch_module.RETIRED_QUOTATION_FIELDS)}, bypass_hooks=True
        )
        mocked_clear_cache.assert_called_once_with()

    @patch.object(patch_module.frappe, "get_doc")
    @patch.object(patch_module.frappe.db, "exists", return_value=False)
    def test_default_template_uses_shared_defaults(
        self, _mocked_exists: MagicMock, mocked_get_doc: MagicMock
    ) -> None:
        template = MagicMock()
        mocked_get_doc.return_value = template

        patch_module._ensure_default_template()

        values = mocked_get_doc.call_args.args[0]
        self.assertEqual(values["doctype"], "Print Configuration Template")
        self.assertEqual(values["template_name"], "Default")
        self.assertEqual(values["show_quotation_date"], 1)
        template.insert.assert_called_once_with(ignore_permissions=True)

    @patch.object(patch_module.frappe.db, "bulk_update")
    @patch.object(patch_module.frappe, "get_all")
    def test_existing_customers_are_linked_only_when_template_is_empty(
        self, mocked_get_all: MagicMock, mocked_bulk_update: MagicMock
    ) -> None:
        mocked_get_all.return_value = [
            {"name": "CUST-0001", "print_configuration_template": ""},
            {"name": "CUST-0002", "print_configuration_template": "Existing Template"},
        ]

        patch_module._link_existing_customers()

        mocked_bulk_update.assert_called_once_with(
            "Customer",
            {"CUST-0001": {"print_configuration_template": "Default"}},
            update_modified=False,
        )
