# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext.supplier import supplier_query


class TestSupplierDksh(IntegrationTestCase):
    def _new_supplier(self, name: str, **kwargs: Any) -> Any:
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
