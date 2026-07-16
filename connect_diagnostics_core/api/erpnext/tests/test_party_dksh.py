# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import frappe
import frappe.defaults
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext.customer import customer_query
from connect_diagnostics_core.api.erpnext.supplier import supplier_query
from connect_diagnostics_core.naming.customer import series_for_customer


def _leaf(doctype: str, name_field: str, parent_field: str, root_name: str, new_name: str) -> str:
    """Return an existing leaf node, or create one (under an existing/created root).

    Kept environment-agnostic: the CI test DB is not seeded with the ERPNext default
    tree roots, so fall back to reusing whatever leaf exists before creating any node.
    """
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


class TestCustomerSeries(UnitTestCase):
    def test_series_for_customer_matches_business_rules(self) -> None:
        cases = (
            ("Individual", "Commercial", "2S.###"),
            ("Company", "Commercial", "4A.###"),
            ("Company", "Hospital", "4H.###"),
            ("Company", "Government", "4H.###"),
        )

        for customer_type, customer_group, expected_series in cases:
            with self.subTest(customer_type=customer_type, customer_group=customer_group):
                doc = SimpleNamespace(customer_type=customer_type, customer_group=customer_group)
                self.assertEqual(series_for_customer(doc), expected_series)


class TestPartyDkshNaming(IntegrationTestCase):
    group: str
    territory: str
    _old_master_name: str | None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # CD code = naming-series number, which requires Customer naming by series.
        # The CI test DB does not seed this global default, so set it explicitly.
        cls._old_master_name = frappe.defaults.get_global_default("cust_master_name")
        frappe.db.set_default("cust_master_name", "Naming Series")
        cls.group = _leaf(
            "Customer Group",
            "customer_group_name",
            "parent_customer_group",
            "All Customer Groups",
            "_Test CD Customer Group",
        )
        cls.territory = _leaf(
            "Territory", "territory_name", "parent_territory", "All Territories", "_Test CD Territory"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._old_master_name:
            frappe.db.set_default("cust_master_name", cls._old_master_name)
        else:
            frappe.db.set_default("cust_master_name", "")
        super().tearDownClass()

    def _new_customer(self, name: str, **kwargs) -> Any:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Company",
                "customer_group": self.group,
                "territory": self.territory,
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
        expected_prefix = series_for_customer(doc).partition(".")[0]
        doc.save(ignore_permissions=True)

        # Record is renamed to a CD series number; the DKSH code is preserved.
        self.assertTrue(doc.name.startswith(expected_prefix))
        self.assertTrue(doc.name[len(expected_prefix) :].isdigit())
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


class TestSupplierDksh(IntegrationTestCase):
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
