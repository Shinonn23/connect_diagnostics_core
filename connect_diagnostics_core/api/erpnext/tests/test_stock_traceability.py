# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_traceability


class TestStockTraceability(UnitTestCase):
    @patch.object(stock_traceability, "get_serial_nos", return_value=["SN-1"])
    @patch.object(
        stock_traceability.frappe.db,
        "get_all",
        return_value=[
            {"batch_no": "B-2", "serial_no": "SN-2"},
            {"batch_no": "B-2", "serial_no": "SN-2"},
        ],
    )
    def test_resolves_direct_and_bundle_values_without_duplicates(
        self, _mocked_get_all: MagicMock, _mocked_get_serial_nos: MagicMock
    ) -> None:
        result = stock_traceability.get_item_traceability(
            {
                "batch_no": "B-1",
                "serial_no": "SN-1",
                "serial_and_batch_bundle": "SABB-1",
            }
        )

        self.assertEqual(
            result,
            {
                "batch_nos": ["B-1", "B-2"],
                "serial_nos": ["SN-1", "SN-2"],
                "records": [
                    {"batch_no": "B-1", "serial_no": "SN-1"},
                    {"batch_no": "B-2", "serial_no": "SN-2"},
                ],
            },
        )
