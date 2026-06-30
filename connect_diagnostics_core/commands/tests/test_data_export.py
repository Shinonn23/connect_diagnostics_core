# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from click.testing import CliRunner

from connect_diagnostics_core.commands.data_export import cd_data_export
from connect_diagnostics_core.data_export.exporter import FrappeClient


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
        export_to_drive.assert_called_once_with((), None, None, excel=False, client=None, catalog=None)
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
        export_to_drive.assert_called_once_with(
            ("Stock", "Accounts"), None, None, excel=False, client=None, catalog=None
        )

    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_excel_uploads_xlsx_files(self, frappe: Mock, export_to_drive: Mock) -> None:
        export_to_drive.return_value = [
            {"module": "Stock", "file_id": "id1", "action": "created", "doctypes": 4},
        ]

        result = CliRunner().invoke(
            cd_data_export,
            ["run", "--excel"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev.local: uploaded 1 Excel file(s)", result.output)
        export_to_drive.assert_called_once_with((), None, None, excel=True, client=None, catalog=None)

    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_remote_uses_api_client_and_skips_connect(self, frappe: Mock, export_to_drive: Mock) -> None:
        export_to_drive.return_value = [
            {"module": "Stock", "file_id": "id1", "action": "created", "doctypes": 4},
        ]

        result = CliRunner().invoke(
            cd_data_export,
            ["run", "--url", "https://uat.example.com", "--api-key", "key123", "--api-secret", "sec456"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        frappe.connect.assert_not_called()
        frappe.destroy.assert_called_once_with()
        _, kwargs = export_to_drive.call_args
        self.assertIsInstance(kwargs["client"], FrappeClient)
        self.assertEqual(kwargs["client"].base_url, "https://uat.example.com")

    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_remote_requires_api_key_and_secret(self, frappe: Mock, export_to_drive: Mock) -> None:
        result = CliRunner().invoke(
            cd_data_export,
            ["run", "--url", "https://uat.example.com"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertNotEqual(result.exit_code, 0)
        export_to_drive.assert_not_called()


class TestDataExportRunLocalCommand(TestCase):
    @patch("connect_diagnostics_core.commands.data_export.build_module_workbook")
    @patch("connect_diagnostics_core.commands.data_export.list_target_doctypes")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_local_saves_xlsx_files_to_disk(
        self, frappe: Mock, list_target_doctypes: Mock, build_module_workbook: Mock
    ) -> None:
        list_target_doctypes.return_value = {"Stock": [{"name": "Item", "category": "Master"}]}
        build_module_workbook.return_value = b"xlsx-content"

        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(
                cd_data_export,
                ["run", "--local", "--output-dir", tmp],
                obj=SimpleNamespace(sites=["dev.local"], profile=False),
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue((Path(tmp) / "Stock.xlsx").exists())
            self.assertEqual((Path(tmp) / "Stock.xlsx").read_bytes(), b"xlsx-content")
            self.assertIn("saved 'Stock' (1 doctypes)", result.output)
            self.assertIn("saved 1 workbook(s)", result.output)
            list_target_doctypes.assert_called_once_with((), client=None, catalog=None)
            build_module_workbook.assert_called_once_with(
                [{"name": "Item", "category": "Master"}], client=None
            )
            frappe.connect.assert_called_once_with()

    @patch("connect_diagnostics_core.commands.data_export.build_module_workbook")
    @patch("connect_diagnostics_core.commands.data_export.list_target_doctypes")
    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_local_does_not_call_drive(
        self,
        frappe: Mock,
        export_to_drive: Mock,
        list_target_doctypes: Mock,
        build_module_workbook: Mock,
    ) -> None:
        list_target_doctypes.return_value = {}
        build_module_workbook.return_value = b""

        with tempfile.TemporaryDirectory() as tmp:
            CliRunner().invoke(
                cd_data_export,
                ["run", "--local", "--output-dir", tmp],
                obj=SimpleNamespace(sites=["dev.local"], profile=False),
            )

        export_to_drive.assert_not_called()

    @patch("connect_diagnostics_core.commands.data_export.build_module_workbook")
    @patch("connect_diagnostics_core.commands.data_export.list_target_doctypes")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_local_remote_skips_frappe_connect(
        self, frappe: Mock, list_target_doctypes: Mock, build_module_workbook: Mock
    ) -> None:
        list_target_doctypes.return_value = {}

        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(
                cd_data_export,
                [
                    "run",
                    "--local",
                    "--output-dir",
                    tmp,
                    "--url",
                    "https://uat.example.com",
                    "--api-key",
                    "k",
                    "--api-secret",
                    "s",
                ],
                obj=SimpleNamespace(sites=["dev.local"], profile=False),
            )

        self.assertEqual(result.exit_code, 0, result.output)
        frappe.connect.assert_not_called()


class TestDataExportRunWithCatalog(TestCase):
    @patch("connect_diagnostics_core.commands.data_export.load_catalog")
    @patch("connect_diagnostics_core.commands.data_export.export_to_drive")
    @patch("connect_diagnostics_core.commands.data_export.frappe")
    def test_run_with_catalog_loads_and_passes_catalog(
        self, frappe: Mock, export_to_drive: Mock, load_catalog: Mock
    ) -> None:
        fake_catalog = {"Account": "Master Data"}
        load_catalog.return_value = fake_catalog
        export_to_drive.return_value = []

        result = CliRunner().invoke(
            cd_data_export,
            ["run", "--catalog", "/tmp/DocType_Categorized.xlsx"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        load_catalog.assert_called_once_with(Path("/tmp/DocType_Categorized.xlsx"))
        _, kwargs = export_to_drive.call_args
        self.assertEqual(kwargs["catalog"], fake_catalog)
