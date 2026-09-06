# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import customer


class TestCustomerPropertySetters(UnitTestCase):
    def test_customer_name_in_arabic_is_hidden_everywhere_it_exists(self) -> None:
        hidden_setter = ("customer_name_in_arabic", "hidden", "1", "Check")

        self.assertEqual(
            set(customer.CUSTOMER_NAME_IN_ARABIC_DOCTYPES),
            {"Customer", "Delivery Note", "POS Invoice", "Sales Invoice", "Sales Order"},
        )
        for doctype in customer.CUSTOMER_NAME_IN_ARABIC_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIn(hidden_setter, customer.PROPERTY_SETTERS[doctype])
