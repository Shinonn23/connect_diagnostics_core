# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import Mock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import print_format


def before_tests() -> None:
    """Minimal test bootstrap.

    The app's unit and integration tests create their own required records, so there
    is no need to run the ERPNext setup wizard here. Doing so previously created a
    THB "_Test Company" that collided with ERPNext's own USD "_Test Company" test
    records under Frappe v16's eager test-record bootstrap.
    """
    frappe.clear_cache()
    _bootstrap_erpnext_test_records()


def _bootstrap_erpnext_test_records() -> None:
    """Run ERPNext's own `_Test *` record bootstrap once per database, with this
    app's extra mandatory fields supplied.

    `erpnext.tests.utils.BootStrapTestData` runs as a module-level side effect the
    first time anything imports `erpnext.tests.utils` -- which normally happens
    lazily, triggered by whichever IntegrationTestCase's dependency graph reaches
    "Company" first via Frappe's `make_test_records`. Its records never set this
    app's app-specific mandatory fields (Customer Code from
    `connect_diagnostics_core.naming.customer`, Employee's `employment_type`
    property setter in `connect_diagnostics_core.setup.employee`), so that
    bootstrap throws wherever it happens to first need one, and none of
    `_Test Company` / `_Test Warehouse - _TC` / `_Test Item` etc. ever get
    created. Triggering the import here -- before any test runs, with the
    missing fields auto-filled only for the duration of this one call -- makes
    the bootstrap succeed.

    Each test category (unit/integration) runs as its own process against the
    *same* site database, so Python's module cache -- which would otherwise stop
    a second `import erpnext.tests.utils` from re-running `BootStrapTestData()`
    -- is reset every time. Without this guard, the second category's run tries
    to re-insert records the first category's run already committed and dies on
    a duplicate key. Checking for "_Test Company" makes the whole function
    idempotent across processes, the same way BootStrapTestData's own per-record
    existence checks are meant to.
    """
    if frappe.db.exists("Company", "_Test Company"):
        return

    from frappe.model.document import Document

    original_insert = Document.insert

    def insert_with_app_mandatory_fields(self, *args, **kwargs):
        if self.doctype == "Customer" and not str(self.get("customer_code") or "").strip():
            self.set("customer_code", self.get("customer_name"))
        elif self.doctype == "Employee" and not str(self.get("employment_type") or "").strip():
            self.set("employment_type", _test_employment_type())
        return original_insert(self, *args, **kwargs)

    with patch.object(Document, "insert", insert_with_app_mandatory_fields):
        import erpnext.tests.utils


def _test_employment_type() -> str:
    """Get-or-create a placeholder Employment Type for the ERPNext bootstrap.

    Its own default Employment Types (if any) aren't a stable name to depend on,
    so this creates one deterministically instead of guessing.
    """
    name = "_Test Employment Type"
    if not frappe.db.exists("Employment Type", name):
        frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert(
            ignore_permissions=True
        )
    return name


class TestPrintFormatCleanup(UnitTestCase):
    @patch.object(print_format, "frappe")
    def test_removes_print_formats_not_owned_by_app_or_explicitly_retired(self, frappe_mock: Mock) -> None:
        frappe_mock.get_all.return_value = [
            {"name": "Core Invoice", "module": "Connect Diagnostics Core"},
            {"name": "Accounting Invoice", "module": "Connect Diagnostics Accounting"},
            {"name": "Withholding Tax Cert", "module": "Thai Tax"},
            {"name": "ERPNext Invoice", "module": "Accounts"},
            {"name": "User Format", "module": None},
            {"name": "Sales Invoice Print", "module": "Connect Diagnostics Accounting"},
        ]

        print_format.remove_non_app_print_formats()

        frappe_mock.get_all.assert_called_once_with("Print Format", fields=["name", "module"])
        self.assertEqual(
            frappe_mock.delete_doc.call_args_list,
            [
                call("Print Format", "ERPNext Invoice", force=True, ignore_missing=True),
                call("Print Format", "User Format", force=True, ignore_missing=True),
                call("Print Format", "Sales Invoice Print", force=True, ignore_missing=True),
            ],
        )
