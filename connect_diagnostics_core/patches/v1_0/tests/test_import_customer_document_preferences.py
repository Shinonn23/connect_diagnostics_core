# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.patches.v1_0 import import_customer_document_preferences as patch_module


def _leaf(doctype: str, name_field: str, parent_field: str, root_name: str, new_name: str) -> str:
    existing = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if existing:
        return existing
    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        frappe.get_doc({"doctype": doctype, name_field: root_name, "is_group": 1}).insert(
            ignore_permissions=True
        )
        root = root_name
    doc = frappe.get_doc(
        {"doctype": doctype, name_field: new_name, parent_field: root, "is_group": 0}
    ).insert(ignore_permissions=True)
    return cast(str, doc.name)


class TestImportCustomerDocumentPreferences(FrappeTestCase):
    group: str
    territory: str

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.group = _leaf(
            "Customer Group",
            "customer_group_name",
            "parent_customer_group",
            "All Customer Groups",
            "_Test CD DocPref Group",
        )
        cls.territory = _leaf(
            "Territory",
            "territory_name",
            "parent_territory",
            "All Territories",
            "_Test CD DocPref Territory",
        )

    def _new_customer(self, name: str) -> Any:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Company",
                "customer_group": self.group,
                "territory": self.territory,
            }
        )
        doc.insert(ignore_permissions=True)
        return doc

    def test_bundled_data_file_is_well_formed(self) -> None:
        prefs = patch_module.load_preferences()
        self.assertTrue(prefs)
        for record in prefs.values():
            self.assertEqual(set(record) & set(patch_module.FIELD_MAP), set(patch_module.FIELD_MAP))
            for key in patch_module.FIELD_MAP:
                self.assertIn(record[key], (0, 1))

    def test_import_sets_customer_flags(self) -> None:
        doc = self._new_customer("_Test CD DocPref Set")
        prefs = {
            doc.name: {
                "use_quotation": 1,
                "use_customer_po": 0,
                "use_tax_invoice": 1,
                "use_receipt": 1,
                "use_abbreviated_tax_invoice": 0,
                "print_date": 0,
            }
        }
        with patch.object(patch_module, "load_preferences", return_value=prefs):
            patch_module.execute()

        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_use_quotation"), 1)
        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_use_customer_po"), 0)
        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_use_tax_invoice"), 1)
        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_use_receipt"), 1)
        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_print_date"), 0)

    def test_import_is_idempotent(self) -> None:
        doc = self._new_customer("_Test CD DocPref Idempotent")
        prefs = {
            doc.name: {
                "use_quotation": 0,
                "use_customer_po": 0,
                "use_tax_invoice": 1,
                "use_receipt": 0,
                "use_abbreviated_tax_invoice": 0,
                "print_date": 1,
            }
        }
        with patch.object(patch_module, "load_preferences", return_value=prefs):
            patch_module.execute()
            patch_module.execute()

        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_use_tax_invoice"), 1)
        self.assertEqual(frappe.db.get_value("Customer", doc.name, "cd_print_date"), 1)

    def test_import_skips_missing_customer(self) -> None:
        prefs = {
            "_TEST_CD_DOCPREF_MISSING": {
                "use_quotation": 1,
                "use_customer_po": 1,
                "use_tax_invoice": 1,
                "use_receipt": 1,
                "use_abbreviated_tax_invoice": 1,
                "print_date": 0,
            }
        }
        with patch.object(patch_module, "load_preferences", return_value=prefs):
            patch_module.execute()

        self.assertFalse(frappe.db.exists("Customer", "_TEST_CD_DOCPREF_MISSING"))
