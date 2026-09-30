# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.erpnext import sales_invoice_credit_workflow as adapter


class TestSalesInvoiceCreditWorkflowIntegration(UnitTestCase):
    def test_hooks_register_lifecycle_guards_and_tasks(self) -> None:
        events = hooks.doc_events["Sales Invoice"]
        module = "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow"
        self.assertIn(module + ".validate_approval_fields", [events["validate"]])
        self.assertIn(module + ".validate_before_submit", events["before_submit"])
        methods = {entry["method"] for entry in hooks.workflow_methods}
        self.assertIn(f"{module}.capture_maker", methods)
        self.assertIn(f"{module}.capture_review", methods)
        self.assertIn(f"{module}.capture_approval", methods)
        self.assertIn(f"{module}.authorize_submit_transition", methods)

    def test_ordinary_invoice_is_outside_route(self) -> None:
        class OrdinaryInvoice:
            doctype = "Sales Invoice"
            name = "NEW-SI"

            def get(self, field: str) -> object:
                return {"is_return": 0, "return_against": None}.get(field)

            def is_new(self) -> bool:
                return True

        doc: Any = OrdinaryInvoice()
        self.assertFalse(adapter.is_credit_note(doc))
