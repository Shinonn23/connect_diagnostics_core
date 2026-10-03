# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase


class TestDeliveryTermsTemplate(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.db.rollback()

    def test_template_name_must_be_unique(self) -> None:
        frappe.get_doc(
            {
                "doctype": "Delivery Terms Template",
                "template_name": "_Test Delivery Terms Dup",
                "delivery_terms_text": "60 days after PO",
            }
        ).insert(ignore_permissions=True)

        with self.assertRaises(frappe.DuplicateEntryError):
            frappe.get_doc(
                {
                    "doctype": "Delivery Terms Template",
                    "template_name": "_Test Delivery Terms Dup",
                    "delivery_terms_text": "Immediate",
                }
            ).insert(ignore_permissions=True)

    def test_delivery_terms_text_is_required(self) -> None:
        with self.assertRaises(frappe.MandatoryError):
            frappe.get_doc(
                {
                    "doctype": "Delivery Terms Template",
                    "template_name": "_Test Delivery Terms No Text",
                }
            ).insert(ignore_permissions=True)
