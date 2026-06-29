# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from click.testing import CliRunner

from connect_diagnostics_core.commands.data_export import cd_data_export


class TestDataExportLoginCommand(TestCase):
    @patch("connect_diagnostics_core.commands.data_export.authorize")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_login_authorizes_and_reports(self, frappe: Mock, authorize: Mock) -> None:
        authorize.return_value = {"data": {"folder_id": "abc"}, "message": "Google Drive authorized."}

        result = CliRunner().invoke(
            cd_data_export,
            ["login", "--client-secret", "/path/cs.json", "--folder", "abc"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev.local: Google Drive authorized.", result.output)
        authorize.assert_called_once_with("/path/cs.json", "abc", None, 0)
        frappe.destroy.assert_called_once_with()


class TestDataExportRunCommand(TestCase):
    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_uploads_and_reports_summary(self, frappe: Mock, export_to_drive: Mock) -> None:
        export_to_drive.return_value = [
            {"module": "Stock", "file_id": "id1", "action": "created", "doctypes": 4},
            {"module": "Accounts", "file_id": "id2", "action": "updated", "doctypes": 6},
        ]

        result = CliRunner().invoke(
            cd_data_export,
            ["run"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("created 'Stock' (4 doctypes) -> id1", result.output)
        self.assertIn("updated 'Accounts' (6 doctypes) -> id2", result.output)
        self.assertIn("dev.local: uploaded 2 module spreadsheet(s)", result.output)
        frappe.connect.assert_called_once_with()
        frappe.destroy.assert_called_once_with()

    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_forwards_module_filter(self, frappe: Mock, export_to_drive: Mock) -> None:
        export_to_drive.return_value = []

        result = CliRunner().invoke(
            cd_data_export,
            ["run", "--module", "Stock", "--module", "Accounts"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        export_to_drive.assert_called_once_with(("Stock", "Accounts"), None, None)
