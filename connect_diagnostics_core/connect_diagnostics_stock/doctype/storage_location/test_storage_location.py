# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

TEST_NAME = "_Test Storage Location"


class TestStorageLocation(IntegrationTestCase):
    def tearDown(self) -> None:
        if frappe.db.exists("Storage Location", TEST_NAME):
            frappe.delete_doc("Storage Location", TEST_NAME)
        super().tearDown()

    def test_names_document_by_location_code(self) -> None:
        doc = frappe.get_doc({"doctype": "Storage Location", "location_code": TEST_NAME}).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.name, TEST_NAME)

    def test_requires_location_code(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Storage Location"}).insert(ignore_permissions=True)

    def test_rejects_duplicate_location_code(self) -> None:
        frappe.get_doc({"doctype": "Storage Location", "location_code": TEST_NAME}).insert(
            ignore_permissions=True
        )
        with self.assertRaises(frappe.DuplicateEntryError):
            frappe.get_doc({"doctype": "Storage Location", "location_code": TEST_NAME}).insert(
                ignore_permissions=True
            )
