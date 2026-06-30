# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.api.erpnext.customer import customer_query
from connect_diagnostics_core.api.erpnext.supplier import supplier_query

_GROUP = "_Test CD Customer Group"
_TERRITORY = "_Test CD Territory"


class TestPartyDkshNaming(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not frappe.db.exists("Customer Group", _GROUP):
            frappe.get_doc(
                {
                    "doctype": "Customer Group",
                    "customer_group_name": _GROUP,
                    "parent_customer_group": "All Customer Groups",
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)
        if not frappe.db.exists("Territory", _TERRITORY):
            frappe.get_doc(
                {
                    "doctype": "Territory",
                    "territory_name": _TERRITORY,
                    "parent_territory": "All Territories",
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)

    def _new_customer(self, name: str, **kwargs) -> Any:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Company",
                "customer_group": _GROUP,
                "territory": _TERRITORY,
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True)
        return doc

    def test_normal_customer_gets_cd_series(self) -> None:
        doc = self._new_customer("_Test CD Normal")
        # A non-DKSH customer is named by a CD naming series, not a DKSH code.
        self.assertIn(doc.name[:2], {"2S", "4A", "4H"})
        self.assertTrue(doc.name[2:].isdigit())
        self.assertFalse(doc.has_dksh_code)

    def test_dksh_only_customer_uses_dksh_code_as_id(self) -> None:
        doc = self._new_customer(
            "_Test CD DkshOnly",
            has_dksh_code=1,
            customer_code_is_dksh_code=1,
            dksh_customer_code="_TEST_DKSH_ONLY_1",
        )
        # The DKSH code becomes the record ID; the field is cleared to avoid the
        # unique constraint duplicating the name.
        self.assertEqual(doc.name, "_TEST_DKSH_ONLY_1")
        self.assertFalse(doc.dksh_customer_code)

    def test_cd_customer_keeps_separate_dksh_code(self) -> None:
        doc = self._new_customer(
            "_Test CD WithDksh",
            has_dksh_code=1,
            customer_code_is_dksh_code=0,
            dksh_customer_code="_TEST_DKSH_SEP_1",
        )
        # CD-coded (series) ID, with the DKSH code kept separately in its field.
        self.assertIn(doc.name[:2], {"2S", "4A", "4H"})
        self.assertEqual(doc.dksh_customer_code, "_TEST_DKSH_SEP_1")

    def test_dksh_required_when_has_dksh_code_ticked(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            self._new_customer("_Test CD MissingDksh", has_dksh_code=1, customer_code_is_dksh_code=0)

    def test_untick_clears_dksh_fields(self) -> None:
        doc = self._new_customer(
            "_Test CD Toggle",
            has_dksh_code=1,
            customer_code_is_dksh_code=0,
            dksh_customer_code="_TEST_DKSH_TOGGLE_1",
        )
        doc.has_dksh_code = 0
        doc.save(ignore_permissions=True)
        self.assertFalse(doc.dksh_customer_code)
        self.assertFalse(doc.customer_code_is_dksh_code)

    def test_convert_dksh_only_to_cd_code(self) -> None:
        doc = self._new_customer(
            "_Test CD Convert",
            has_dksh_code=1,
            customer_code_is_dksh_code=1,
            dksh_customer_code="_TEST_DKSH_CONV_1",
        )
        old_name = doc.name
        self.assertEqual(old_name, "_TEST_DKSH_CONV_1")

        doc.reload()
        doc.customer_code_is_dksh_code = 0
        doc.save(ignore_permissions=True)

        # Record is renamed to a CD series number; the DKSH code is preserved.
        self.assertTrue(doc.name.startswith("4A"))
        self.assertFalse(frappe.db.exists("Customer", old_name))
        self.assertEqual(doc.dksh_customer_code, "_TEST_DKSH_CONV_1")
        self.assertTrue(doc.has_dksh_code)

    def test_customer_query_matches_alternative_name(self) -> None:
        doc = self._new_customer("_Test CD AltSearch")
        doc.append("alternative_names", {"name_value": "_TEST_ALT_UNIQUE_XYZ"})
        doc.save(ignore_permissions=True)

        rows = customer_query("Customer", "_TEST_ALT_UNIQUE_XYZ", "name", 0, 20, None)
        self.assertIn(doc.name, [row[0] for row in rows])

    def test_customer_query_matches_dksh_code(self) -> None:
        doc = self._new_customer(
            "_Test CD DkshSearch",
            has_dksh_code=1,
            customer_code_is_dksh_code=0,
            dksh_customer_code="_TEST_DKSH_SEARCH_1",
        )
        rows = customer_query("Customer", "_TEST_DKSH_SEARCH_1", "name", 0, 20, None)
        self.assertIn(doc.name, [row[0] for row in rows])


class TestSupplierDksh(FrappeTestCase):
    def _new_supplier(self, name: str, **kwargs) -> Any:
        doc = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": name,
                "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True)
        return doc

    def test_dksh_only_supplier_uses_dksh_code_as_id(self) -> None:
        doc = self._new_supplier(
            "_Test CD Supplier DkshOnly",
            has_dksh_code=1,
            supplier_code_is_dksh_code=1,
            dksh_supplier_code="_TEST_SUP_DKSH_1",
        )
        self.assertEqual(doc.name, "_TEST_SUP_DKSH_1")
        self.assertFalse(doc.dksh_supplier_code)

    def test_supplier_query_matches_alternative_name(self) -> None:
        doc = self._new_supplier("_Test CD Supplier Alt")
        doc.append("alternative_names", {"name_value": "_TEST_SUP_ALT_XYZ"})
        doc.save(ignore_permissions=True)

        rows = supplier_query("Supplier", "_TEST_SUP_ALT_XYZ", "name", 0, 20, None)
        self.assertIn(doc.name, [row[0] for row in rows])
