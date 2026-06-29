# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch

from openpyxl import load_workbook

from connect_diagnostics_core.data_export import exporter
from connect_diagnostics_core.data_export.exporter import (
    INDEX_HEADERS,
    INDEX_SHEET_NAME,
    _unique_sheet_name,
    build_module_workbook,
    classify_doctype,
    list_target_doctypes,
)


class TestClassifyDoctype(TestCase):
    def test_single_doctype_is_setup(self) -> None:
        self.assertEqual(classify_doctype(issingle=True, is_submittable=False), "Setup")

    def test_submittable_doctype_is_transaction(self) -> None:
        self.assertEqual(classify_doctype(issingle=False, is_submittable=True), "Transaction")

    def test_plain_doctype_is_master(self) -> None:
        self.assertEqual(classify_doctype(issingle=False, is_submittable=False), "Master")

    def test_single_takes_priority_over_submittable(self) -> None:
        self.assertEqual(classify_doctype(issingle=True, is_submittable=True), "Setup")


class TestUniqueSheetName(TestCase):
    def test_returns_doctype_name_when_unused(self) -> None:
        used: set[str] = set()
        self.assertEqual(_unique_sheet_name("Account", used), "Account")

    def test_deduplicates_collisions_with_suffix(self) -> None:
        used: set[str] = set()
        first = _unique_sheet_name("Account", used)
        second = _unique_sheet_name("Account", used)
        self.assertEqual(first, "Account")
        self.assertEqual(second, "Account 2")

    def test_truncates_to_excel_limit(self) -> None:
        used: set[str] = set()
        name = _unique_sheet_name("A" * 50, used)
        self.assertLessEqual(len(name), 31)

    def test_truncated_collision_stays_within_limit_and_unique(self) -> None:
        used: set[str] = set()
        long_name = "B" * 40
        first = _unique_sheet_name(long_name, used)
        second = _unique_sheet_name(long_name, used)
        self.assertLessEqual(len(second), 31)
        self.assertNotEqual(first, second)


class TestListTargetDoctypes(TestCase):
    @patch.object(exporter, "frappe")
    def test_groups_by_module_with_category(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [
            {"name": "Account", "module": "Accounts", "issingle": 0, "is_submittable": 0},
            {"name": "Sales Invoice", "module": "Accounts", "issingle": 0, "is_submittable": 1},
            {"name": "Stock Settings", "module": "Stock", "issingle": 1, "is_submittable": 0},
        ]

        grouped = list_target_doctypes()

        self.assertEqual(set(grouped), {"Accounts", "Stock"})
        self.assertEqual(
            grouped["Accounts"],
            [
                {"name": "Account", "category": "Master"},
                {"name": "Sales Invoice", "category": "Transaction"},
            ],
        )
        self.assertEqual(grouped["Stock"], [{"name": "Stock Settings", "category": "Setup"}])

    @patch.object(exporter, "frappe")
    def test_excludes_child_and_virtual_doctypes(self, frappe: Mock) -> None:
        frappe.get_all.return_value = []

        list_target_doctypes()

        _, kwargs = frappe.get_all.call_args
        self.assertEqual(kwargs["filters"], {"istable": 0, "is_virtual": 0})

    @patch.object(exporter, "frappe")
    def test_module_filter_is_applied(self, frappe: Mock) -> None:
        frappe.get_all.return_value = []

        list_target_doctypes(modules=("Stock",))

        _, kwargs = frappe.get_all.call_args
        self.assertEqual(kwargs["filters"]["module"], ["in", ["Stock"]])


class TestBuildModuleWorkbook(TestCase):
    @patch.object(exporter, "frappe")
    @patch.object(exporter, "export_doctype_rows")
    def test_workbook_has_index_and_doctype_sheets(self, export_doctype_rows: Mock, frappe: Mock) -> None:
        frappe.db.count.return_value = 3
        export_doctype_rows.return_value = [
            [""],
            ["DocType:", "Account"],
            ["Column Labels:", "ID", "Account Name"],
            ["Column Name:", "name", "account_name"],
            ["Mandatory:", "Yes", "Yes"],
            ["Type:", "Data", "Data"],
            ["Info:", "", ""],
        ]

        content = build_module_workbook([{"name": "Account", "category": "Master"}])

        workbook = load_workbook(BytesIO(content))
        self.assertEqual(workbook.sheetnames, [INDEX_SHEET_NAME, "Account"])

        index = workbook[INDEX_SHEET_NAME]
        self.assertEqual([cell.value for cell in index[1]], INDEX_HEADERS)
        self.assertEqual([cell.value for cell in index[2]], ["Account", "Master", "Account", 3])

        account = workbook["Account"]
        self.assertEqual(account["A2"].value, "DocType:")
        self.assertEqual(account["B2"].value, "Account")
        self.assertEqual(account["A4"].value, "Column Name:")

    @patch.object(exporter, "frappe")
    @patch.object(exporter, "export_doctype_rows")
    def test_failed_doctype_is_indexed_but_skipped(self, export_doctype_rows: Mock, frappe: Mock) -> None:
        export_doctype_rows.side_effect = Exception("no table")

        content = build_module_workbook([{"name": "System Settings", "category": "Setup"}])

        workbook = load_workbook(BytesIO(content))
        self.assertEqual(workbook.sheetnames, [INDEX_SHEET_NAME])

        index = workbook[INDEX_SHEET_NAME]
        self.assertEqual([cell.value for cell in index[2]], ["System Settings", "Setup", None, 0])
