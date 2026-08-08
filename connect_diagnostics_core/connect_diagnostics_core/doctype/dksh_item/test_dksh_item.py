# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

# DKSH Item only links to Item; auto-creating Item's full test-record dependency
# tree is unnecessary here and pulls in unrelated masters. The tests below create
# the single Item they need directly.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Item"]


class TestDKSHItem(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.db.rollback()

    def test_stand_alone_record_saves_without_an_item(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "DKSH Item", "dksh_item_code": "_Test DKSH Standalone"}
        ).insert(ignore_permissions=True)

        self.assertEqual(doc.name, "_Test DKSH Standalone")
        self.assertFalse(doc.item)

    def test_code_trims_surrounding_whitespace(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "DKSH Item", "dksh_item_code": "  _Test DKSH Trim  "}
        ).insert(ignore_permissions=True)

        self.assertEqual(doc.dksh_item_code, "_Test DKSH Trim")

    def test_duplicate_code_is_rejected_by_naming(self) -> None:
        frappe.get_doc(
            {"doctype": "DKSH Item", "dksh_item_code": "_Test DKSH Dup"}
        ).insert(ignore_permissions=True)

        with self.assertRaises(frappe.DuplicateEntryError):
            frappe.get_doc(
                {"doctype": "DKSH Item", "dksh_item_code": "_Test DKSH Dup"}
            ).insert(ignore_permissions=True)

    def test_second_record_for_the_same_item_is_rejected(self) -> None:
        item = _make_item("_Test DKSH Linked Item")
        frappe.get_doc(
            {"doctype": "DKSH Item", "dksh_item_code": "_Test DKSH Link A", "item": item}
        ).insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "DKSH Item", "dksh_item_code": "_Test DKSH Link B", "item": item}
            ).insert(ignore_permissions=True)


def _make_item(item_code: str) -> str:
    """Create a bare Item via db_insert, matching the report tests' pattern.

    db_insert bypasses the controller and doc_event hooks, which is what we want:
    the DKSH Item link only needs the ``tabItem`` row to exist, and this keeps the
    test independent of unrelated Item validation.
    """
    if frappe.db.exists("Item", item_code):
        return item_code
    item = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "item_group": "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": 0,
        }
    )
    item.name = item_code
    item.db_insert()
    return item_code
