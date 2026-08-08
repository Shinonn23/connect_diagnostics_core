# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import customer as customer_api

# DKSH Customer only links to Customer; auto-creating Customer's full test-record
# dependency tree pulls in unrelated masters. The tests below create the single
# Customer they need directly via db_insert.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Customer"]


class TestDKSHCustomer(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.db.rollback()

    def test_stand_alone_record_saves_without_a_customer(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "DKSH Customer", "dksh_customer_code": "_Test DKSH Cust Standalone"}
        ).insert(ignore_permissions=True)

        self.assertEqual(doc.name, "_Test DKSH Cust Standalone")
        self.assertFalse(doc.customer)

    def test_code_trims_surrounding_whitespace(self) -> None:
        doc = frappe.get_doc(
            {"doctype": "DKSH Customer", "dksh_customer_code": "  _Test DKSH Cust Trim  "}
        ).insert(ignore_permissions=True)

        self.assertEqual(doc.dksh_customer_code, "_Test DKSH Cust Trim")

    def test_duplicate_code_is_rejected_by_naming(self) -> None:
        frappe.get_doc({"doctype": "DKSH Customer", "dksh_customer_code": "_Test DKSH Cust Dup"}).insert(
            ignore_permissions=True
        )

        with self.assertRaises(frappe.DuplicateEntryError):
            frappe.get_doc(
                {"doctype": "DKSH Customer", "dksh_customer_code": "_Test DKSH Cust Dup"}
            ).insert(ignore_permissions=True)

    def test_second_record_for_the_same_customer_is_rejected(self) -> None:
        customer = _make_customer("_Test DKSH Linked Customer")
        frappe.get_doc(
            {
                "doctype": "DKSH Customer",
                "dksh_customer_code": "_Test DKSH Cust Link A",
                "customer": customer,
            }
        ).insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "DKSH Customer",
                    "dksh_customer_code": "_Test DKSH Cust Link B",
                    "customer": customer,
                }
            ).insert(ignore_permissions=True)


class TestLinkSourceDKSHCustomer(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.db.rollback()

    def test_links_dksh_customer_and_creates_primary_billing_address(self) -> None:
        dksh = frappe.get_doc(
            {
                "doctype": "DKSH Customer",
                "dksh_customer_code": "_Test DKSH Conv Src",
                "customer_name": "_Test DKSH Converted Co",
                "tax_id": "0105551234567",
                "branch_code": "00000",
                "address_line1": "1 Test Road",
                "city": "Bangkok",
                "county": "Watthana",
                "state": "Bangkok",
                "pincode": "10110",
                "country": "Thailand",
            }
        ).insert(ignore_permissions=True)
        customer = _make_customer("_Test DKSH Conv Cust")

        customer_api.link_source_dksh_customer(
            _CustomerStub(customer, dksh.name)  # ty: ignore[invalid-argument-type] - test double
        )

        self.assertEqual(frappe.db.get_value("DKSH Customer", dksh.name, "customer"), customer)
        addresses = _primary_billing_addresses(customer)
        self.assertEqual(len(addresses), 1)
        address = frappe.get_doc("Address", addresses[0])
        self.assertEqual(address.address_line1, "1 Test Road")
        self.assertEqual(address.tax_id, "0105551234567")
        self.assertEqual(address.branch_code, "00000")

    def test_is_a_noop_when_the_dksh_customer_is_already_linked(self) -> None:
        other = _make_customer("_Test DKSH Other Cust")
        dksh = frappe.get_doc(
            {
                "doctype": "DKSH Customer",
                "dksh_customer_code": "_Test DKSH Conv Taken",
                "customer": other,
            }
        ).insert(ignore_permissions=True)
        customer = _make_customer("_Test DKSH Conv Late")

        customer_api.link_source_dksh_customer(
            _CustomerStub(customer, dksh.name)  # ty: ignore[invalid-argument-type] - test double
        )

        self.assertEqual(frappe.db.get_value("DKSH Customer", dksh.name, "customer"), other)

    def test_no_source_is_a_noop(self) -> None:
        customer_api.link_source_dksh_customer(
            _CustomerStub("_Test DKSH No Source", "")  # ty: ignore[invalid-argument-type] - test double
        )


class _CustomerStub:
    """Minimal stand-in for the newly inserted Customer document."""

    def __init__(self, name: str, source_dksh_customer: str) -> None:
        self.name = name
        self._values = {"source_dksh_customer": source_dksh_customer}

    def get(self, fieldname: str) -> object:
        return self._values.get(fieldname)


def _make_customer(customer_code: str) -> str:
    """Create a bare Customer via db_insert, matching the report tests' pattern.

    db_insert bypasses the controller and doc_event hooks, so no naming, readiness,
    or auto-link logic runs; the DKSH Customer link and Address only need the
    ``tabCustomer`` row to exist.
    """
    if frappe.db.exists("Customer", customer_code):
        return customer_code
    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_code,
            "customer_code": customer_code,
            "customer_type": "Company",
            "customer_group": "All Customer Groups",
            "territory": "All Territories",
        }
    )
    customer.name = customer_code
    customer.db_insert()
    return customer_code


def _primary_billing_addresses(customer: str) -> list[str]:
    address_names = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
        pluck="parent",
    )
    if not address_names:
        return []
    return frappe.get_all(
        "Address",
        filters={"name": ["in", address_names], "address_type": "Billing", "is_primary_address": 1},
        pluck="name",
    )
