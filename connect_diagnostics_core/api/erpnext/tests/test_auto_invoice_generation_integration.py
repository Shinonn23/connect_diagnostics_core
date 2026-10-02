# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native Desk-facing Sales generation guards on the dedicated test site."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.api.erpnext import auto_invoice_generation as generation


class TestSalesAutoInvoiceGenerationIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(frappe.local.site, "local.test")
        self.assertTrue(frappe.db.exists("DocType", generation.RUN_DOCTYPE))
        self._old_user = frappe.session.user

    def tearDown(self) -> None:
        frappe.set_user(self._old_user)
        super().tearDown()

    def test_even_admin_cannot_create_system_run_through_document_insert(self) -> None:
        frappe.set_user("Administrator")
        run = frappe.get_doc({"doctype": generation.RUN_DOCTYPE, "generation_status": "Queued"})
        with self.assertRaises(frappe.PermissionError):
            run.insert(ignore_permissions=True)
        self.assertFalse(run.name and frappe.db.exists(generation.RUN_DOCTYPE, run.name))

    def test_native_sales_invoice_before_insert_denies_unapproved_source_link(self) -> None:
        frappe.set_user("Administrator")
        hooks = frappe.get_hooks("doc_events").get("Sales Invoice", {})
        self.assertIn(
            "connect_diagnostics_core.api.erpnext.auto_invoice_generation.before_insert_sales_invoice_generation",
            hooks.get("before_insert", []),
        )
        invoice = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "items": [{"sales_order": "SO-UNAPPROVED", "so_detail": "SO-ROW-UNAPPROVED"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            invoice.run_method("before_insert")

    def test_status_endpoint_rejects_absent_run_without_disclosing_data(self) -> None:
        frappe.set_user("Guest")
        with self.assertRaises(frappe.ValidationError):
            generation.get_sales_invoice_generation_status("_TEST-MISSING-AUTO-INVOICE-RUN")
