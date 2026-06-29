# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, mock_open, patch

from connect_diagnostics_core.data_export import drive
from connect_diagnostics_core.data_export.drive import (
    CONFIG_FOLDER,
    GOOGLE_SHEET_MIME,
    XLSX_MIME,
    get_drive_credentials,
    upload_module_as_excel,
    upload_module_as_sheet,
)


def _service_with_existing(file_id: str | None) -> Mock:
    service = Mock()
    files = service.files.return_value
    found = [{"id": file_id}] if file_id else []
    files.list.return_value.execute.return_value = {"files": found}
    files.create.return_value.execute.return_value = {"id": "created-id"}
    files.update.return_value.execute.return_value = {}
    return service


class TestUploadModuleAsSheet(TestCase):
    def test_creates_google_sheet_when_absent(self) -> None:
        service = _service_with_existing(None)

        file_id, action = upload_module_as_sheet(service, "folder", "Stock", b"xlsx")

        self.assertEqual((file_id, action), ("created-id", "created"))
        _, kwargs = service.files.return_value.create.call_args
        self.assertEqual(kwargs["body"]["mimeType"], GOOGLE_SHEET_MIME)
        self.assertEqual(kwargs["body"]["name"], "Stock")
        self.assertEqual(kwargs["body"]["parents"], ["folder"])
        service.files.return_value.update.assert_not_called()

    def test_replaces_existing_google_sheet(self) -> None:
        service = _service_with_existing("existing-id")

        file_id, action = upload_module_as_sheet(service, "folder", "Stock", b"xlsx")

        self.assertEqual((file_id, action), ("existing-id", "updated"))
        _, kwargs = service.files.return_value.update.call_args
        self.assertEqual(kwargs["fileId"], "existing-id")
        service.files.return_value.create.assert_not_called()


class TestUploadModuleAsExcel(TestCase):
    def test_creates_xlsx_file_when_absent(self) -> None:
        service = _service_with_existing(None)

        file_id, action = upload_module_as_excel(service, "folder", "Stock", b"xlsx")

        self.assertEqual((file_id, action), ("created-id", "created"))
        _, kwargs = service.files.return_value.create.call_args
        self.assertEqual(kwargs["body"]["mimeType"], XLSX_MIME)
        self.assertEqual(kwargs["body"]["name"], "Stock.xlsx")
        self.assertEqual(kwargs["body"]["parents"], ["folder"])
        service.files.return_value.update.assert_not_called()

    def test_replaces_existing_xlsx_file(self) -> None:
        service = _service_with_existing("existing-id")

        file_id, action = upload_module_as_excel(service, "folder", "Stock", b"xlsx")

        self.assertEqual((file_id, action), ("existing-id", "updated"))
        _, kwargs = service.files.return_value.update.call_args
        self.assertEqual(kwargs["fileId"], "existing-id")
        service.files.return_value.create.assert_not_called()


class TestGetDriveCredentials(TestCase):
    @patch("google.oauth2.credentials.Credentials")
    @patch.object(drive.os.path, "exists", return_value=True)
    def test_returns_existing_valid_token_without_login(self, _exists: Mock, credentials_cls: Mock) -> None:
        credentials_cls.from_authorized_user_file.return_value = Mock(valid=True)

        creds = get_drive_credentials(token_path="/tmp/token.json")

        self.assertTrue(creds.valid)
        credentials_cls.from_authorized_user_file.assert_called_once_with("/tmp/token.json", drive.SCOPES)

    @patch("builtins.open", new_callable=mock_open)
    @patch("google_auth_oauthlib.flow.InstalledAppFlow")
    @patch.object(drive.os.path, "exists")
    def test_runs_login_and_saves_token(
        self, exists: Mock, installed_app_flow: Mock, open_mock: Mock
    ) -> None:
        exists.side_effect = lambda path: path == "/cs.json"  # token missing, client secret present
        new_creds = Mock()
        new_creds.to_json.return_value = '{"refresh_token": "rt"}'
        flow = Mock()
        flow.run_local_server.return_value = new_creds
        installed_app_flow.from_client_secrets_file.return_value = flow

        creds = get_drive_credentials(
            client_secret_path="/cs.json", token_path="/tmp/token.json", port=9000, allow_login=True
        )

        self.assertIs(creds, new_creds)
        flow.run_local_server.assert_called_once_with(port=9000, open_browser=False)
        open_mock.assert_called_once_with("/tmp/token.json", "w")
        open_mock().write.assert_called_once_with('{"refresh_token": "rt"}')

    @patch.object(drive, "frappe")
    @patch.object(drive.os.path, "exists", return_value=False)
    def test_throws_when_login_allowed_but_client_secret_missing(self, _exists: Mock, frappe: Mock) -> None:
        frappe.throw.side_effect = RuntimeError("client secret missing")

        with self.assertRaises(RuntimeError):
            get_drive_credentials(
                client_secret_path="/cs.json", token_path="/tmp/token.json", allow_login=True
            )

    @patch.object(drive, "frappe")
    @patch.object(drive.os.path, "exists", return_value=False)
    def test_throws_without_token_when_login_not_allowed(self, _exists: Mock, frappe: Mock) -> None:
        frappe.throw.side_effect = RuntimeError("not authorized")

        with self.assertRaises(RuntimeError):
            get_drive_credentials(token_path="/tmp/token.json")


class TestExportToDrive(TestCase):
    @patch.object(drive, "_drive_service")
    @patch.object(drive, "build_module_workbook")
    @patch.object(drive, "list_target_doctypes")
    @patch.object(drive, "frappe")
    def test_uploads_each_module(
        self, frappe: Mock, list_target_doctypes: Mock, build_module_workbook: Mock, drive_service: Mock
    ) -> None:
        frappe.conf.get.return_value = "folder123"
        list_target_doctypes.return_value = {"Stock": [{"name": "Item", "category": "Master"}]}
        build_module_workbook.return_value = b"xlsx"
        drive_service.return_value = _service_with_existing(None)

        summary = drive.export_to_drive()

        self.assertEqual(
            summary,
            [{"module": "Stock", "file_id": "created-id", "action": "created", "doctypes": 1}],
        )

    @patch.object(drive, "_drive_service")
    @patch.object(drive, "build_module_workbook")
    @patch.object(drive, "list_target_doctypes")
    @patch.object(drive, "frappe")
    def test_uploads_excel_files_when_requested(
        self, frappe: Mock, list_target_doctypes: Mock, build_module_workbook: Mock, drive_service: Mock
    ) -> None:
        frappe.conf.get.return_value = "folder123"
        list_target_doctypes.return_value = {"Stock": [{"name": "Item", "category": "Master"}]}
        build_module_workbook.return_value = b"xlsx"
        drive_service.return_value = _service_with_existing(None)

        summary = drive.export_to_drive(excel=True)

        self.assertEqual(
            summary,
            [{"module": "Stock", "file_id": "created-id", "action": "created", "doctypes": 1}],
        )
        _, kwargs = drive_service.return_value.files.return_value.create.call_args
        self.assertEqual(kwargs["body"]["name"], "Stock.xlsx")
        self.assertEqual(kwargs["body"]["mimeType"], XLSX_MIME)

    @patch.object(drive, "frappe")
    def test_throws_without_configured_folder(self, frappe: Mock) -> None:
        frappe.conf.get.return_value = None
        frappe.throw.side_effect = RuntimeError("no folder")

        with self.assertRaises(RuntimeError):
            drive.export_to_drive()


class TestAuthorize(TestCase):
    @patch("frappe.installer.update_site_config")
    @patch.object(drive, "get_drive_credentials")
    @patch.object(drive, "frappe")
    def test_logs_in_and_saves_folder(
        self, frappe: Mock, get_drive_credentials: Mock, update_site_config: Mock
    ) -> None:
        result = drive.authorize("/cs.json", "folder", "/tmp/token.json")

        get_drive_credentials.assert_called_once_with(
            client_secret_path="/cs.json", token_path="/tmp/token.json", port=0, allow_login=True
        )
        update_site_config.assert_called_once_with(CONFIG_FOLDER, "folder")
        self.assertIn("/tmp/token.json", str(result["message"]))

    @patch("frappe.installer.update_site_config")
    @patch.object(drive, "get_drive_credentials")
    @patch.object(drive, "frappe")
    def test_skips_folder_save_when_not_given(
        self, frappe: Mock, get_drive_credentials: Mock, update_site_config: Mock
    ) -> None:
        drive.authorize("/cs.json", None, "/tmp/token.json")

        update_site_config.assert_not_called()
