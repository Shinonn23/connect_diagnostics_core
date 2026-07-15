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


class TestPrintFormatCleanup(UnitTestCase):
    @patch.object(print_format, "frappe")
    def test_removes_print_formats_not_owned_by_app_or_explicitly_retired(self, frappe_mock: Mock) -> None:
        frappe_mock.get_all.return_value = [
            {"name": "Core Invoice", "module": "Connect Diagnostics Core"},
            {"name": "Accounting Invoice", "module": "Connect Diagnostics Accounting"},
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
