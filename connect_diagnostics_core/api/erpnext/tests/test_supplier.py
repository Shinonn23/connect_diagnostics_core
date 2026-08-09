# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.supplier import supplier_query


class TestSupplierSearch(UnitTestCase):
    @patch("connect_diagnostics_core.api.erpnext.supplier.frappe.get_list", return_value=[])
    @patch("connect_diagnostics_core.api.erpnext.supplier.frappe.has_permission")
    def test_supplier_query_matches_id_and_name(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_list: MagicMock,
    ) -> None:
        supplier_query("Supplier", "SUP-001", "name", 0, 20, {"disabled": 0})

        self.assertEqual(
            mocked_get_list.call_args.kwargs["or_filters"],
            [
                ["Supplier", "name", "like", "%SUP-001%"],
                ["Supplier", "supplier_name", "like", "%SUP-001%"],
            ],
        )
        self.assertEqual(mocked_get_list.call_args.kwargs["filters"], {"disabled": 0})
