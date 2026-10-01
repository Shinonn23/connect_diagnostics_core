# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_asset_conversion


class TestStockAssetConversionApi(UnitTestCase):
    @patch.object(stock_asset_conversion.frappe, "get_roles", return_value=["Stock Manager"])
    def test_preview_approval_requires_accounts_manager(self, _get_roles) -> None:
        with self.assertRaises(frappe.PermissionError):
            stock_asset_conversion.approve_preview("SAC-1")
