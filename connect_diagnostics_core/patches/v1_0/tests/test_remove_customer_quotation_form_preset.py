# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_customer_quotation_form_preset as patch_module


class TestRemoveCustomerQuotationFormPreset(UnitTestCase):
    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "delete_custom_fields")
    def test_execute_deletes_only_the_retired_customer_preset(
        self, mocked_delete_custom_fields: MagicMock, mocked_clear_cache: MagicMock
    ) -> None:
        patch_module.execute()

        mocked_delete_custom_fields.assert_called_once_with(
            {"Customer": ["quotation_form_preset"]}, bypass_hooks=True
        )
        mocked_clear_cache.assert_called_once_with()
