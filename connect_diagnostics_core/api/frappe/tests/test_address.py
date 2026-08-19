# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import address


class StripLocationPrefixesTest(UnitTestCase):
    def test_strips_upcountry_prefixes(self) -> None:
        result = address._strip_location_prefixes(
            {"city": "ต.จักรวรรดิ", "county": "อ.สัมพันธวงศ์", "state": "จ.สมุทรปราการ"}
        )
        self.assertEqual(result["city"], "จักรวรรดิ")
        self.assertEqual(result["county"], "สัมพันธวงศ์")
        self.assertEqual(result["state"], "สมุทรปราการ")

    def test_strips_bangkok_prefixes(self) -> None:
        result = address._strip_location_prefixes(
            {"city": "แขวงจักรวรรดิ", "county": "เขตสัมพันธวงศ์", "state": "กรุงเทพมหานคร"}
        )
        self.assertEqual(result["city"], "จักรวรรดิ")
        self.assertEqual(result["county"], "สัมพันธวงศ์")
        self.assertEqual(result["state"], "กรุงเทพมหานคร")

    def test_leaves_empty_and_unprefixed_values_untouched(self) -> None:
        result = address._strip_location_prefixes({"city": "", "county": "สัมพันธวงศ์", "state": None})
        self.assertEqual(result["city"], "")
        self.assertEqual(result["county"], "สัมพันธวงศ์")
        self.assertEqual(result["state"], "")


class GetAddressByTaxIdOverrideTest(UnitTestCase):
    def test_delegates_to_original_and_strips_prefixes(self) -> None:
        fetched: dict[str, Any] = {
            "name": "บริษัท ทดสอบ จำกัด",
            "address_line1": "123",
            "city": "ต.จักรวรรดิ",
            "county": "อ.สัมพันธวงศ์",
            "state": "จ.สมุทรปราการ",
            "pincode": "10100",
        }
        with patch("erpnext_thailand.utils.get_address_by_tax_id", return_value=fetched) as mock_fetch:
            result = address.get_address_by_tax_id(tax_id="1234567890123", branch="0")

        mock_fetch.assert_called_once_with(tax_id="1234567890123", branch="0")
        self.assertEqual(result["city"], "จักรวรรดิ")
        self.assertEqual(result["county"], "สัมพันธวงศ์")
        self.assertEqual(result["state"], "สมุทรปราการ")
        # Untouched keys pass through unchanged.
        self.assertEqual(result["name"], "บริษัท ทดสอบ จำกัด")
        self.assertEqual(result["pincode"], "10100")
