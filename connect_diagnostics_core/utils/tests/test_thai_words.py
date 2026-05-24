# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.utils.thai_words import number_to_thai_currency


class TestNumberToThaiCurrency(FrappeTestCase):
    def test_thb_whole_number_appends_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(100), "หนึ่งร้อยบาทถ้วน")

    def test_thb_with_satang_appends_satang_unit(self) -> None:
        self.assertEqual(number_to_thai_currency(100.50), "หนึ่งร้อยบาทห้าสิบสตางค์")

    def test_thb_zero_returns_sun_baht_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(0), "ศูนย์บาทถ้วน")

    def test_thb_is_default_currency(self) -> None:
        self.assertEqual(number_to_thai_currency(100), number_to_thai_currency(100, "THB"))

    def test_jpy_whole_number_appends_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(100, "JPY"), "หนึ่งร้อยเยนถ้วน")

    def test_jpy_with_decimal_ignores_subunit(self) -> None:
        self.assertEqual(number_to_thai_currency(100.50, "JPY"), "หนึ่งร้อยเยนถ้วน")

    def test_usd_whole_number_appends_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(100, "USD"), "หนึ่งร้อยดอลลาร์ถ้วน")

    def test_usd_with_cents_appends_cent_unit(self) -> None:
        self.assertEqual(number_to_thai_currency(99.99, "USD"), "เก้าสิบเก้าดอลลาร์เก้าสิบเก้าเซนต์")

    def test_gbp_whole_number_appends_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(25, "GBP"), "ยี่สิบห้าปอนด์ถ้วน")

    def test_gbp_with_pence_appends_penny_unit(self) -> None:
        self.assertEqual(number_to_thai_currency(25.50, "GBP"), "ยี่สิบห้าปอนด์ห้าสิบเพนนี")

    def test_eur_with_subunit_appends_cent_unit(self) -> None:
        self.assertEqual(number_to_thai_currency(10.10, "EUR"), "สิบยูโรสิบเซนต์")

    def test_cny_whole_number_appends_thouan(self) -> None:
        self.assertEqual(number_to_thai_currency(1, "CNY"), "หนึ่งหยวนถ้วน")

    def test_unknown_currency_returns_number_only(self) -> None:
        self.assertEqual(number_to_thai_currency(100, "XYZ"), "หนึ่งร้อย")
