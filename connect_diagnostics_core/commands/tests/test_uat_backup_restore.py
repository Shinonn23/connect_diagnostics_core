# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, call, patch

import click
from click.testing import CliRunner

from connect_diagnostics_core.commands.uat_backup_restore import (
    RcloneBackupFile,
    RcloneConfig,
    build_rclone_command,
    download_rclone_file,
    ensure_staging_dir,
    get_rclone_config,
    list_rclone_files,
    restore_uat_backup,
    select_latest_database_backup,
    validate_environment_guard,
)
from connect_diagnostics_core.commands.uat_backup_restore import (
    test_uat_backup_restore as test_uat_backup_restore_command,
)


class TestUatBackupRestoreHelpers(TestCase):
    def test_select_latest_database_backup_uses_source_slug_and_ignores_sidecar_files(self) -> None:
        backup_file = select_latest_database_backup(
            [
                RcloneBackupFile(
                    "20260620_190631-uat_erp_connectdiagnostics_net-database.sql.gz",
                    "20260620_190631-uat_erp_connectdiagnostics_net-database.sql.gz",
                ),
                RcloneBackupFile(
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz:Zone.Identifier",
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz:Zone.Identifier",
                ),
                RcloneBackupFile(
                    "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz",
                    "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz",
                ),
                RcloneBackupFile(
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                ),
            ],
            "uat_erp_connectdiagnostics_net",
        )

        self.assertEqual(backup_file.name, "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz")

    def test_select_latest_database_backup_fails_when_no_candidate_exists(self) -> None:
        with self.assertRaises(click.ClickException):
            select_latest_database_backup(
                [
                    RcloneBackupFile(
                        "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz",
                        "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz",
                    )
                ],
                "uat_erp_connectdiagnostics_net",
            )

    @patch("connect_diagnostics_core.commands.uat_backup_restore.frappe")
    def test_get_rclone_config_reads_remote_path_from_site_config(self, frappe: Mock) -> None:
        frappe.conf.get.side_effect = lambda key: {
            "uat_backup_rclone_remote_path": "gdrive:ERPNext/UAT/backups/",
            "uat_backup_rclone_config_path": "/home/erp/.config/rclone/rclone.conf",
        }.get(key)

        rclone_config = get_rclone_config()

        self.assertEqual(rclone_config.remote_path, "gdrive:ERPNext/UAT/backups")
        self.assertEqual(rclone_config.config_path, "/home/erp/.config/rclone/rclone.conf")

    @patch("connect_diagnostics_core.commands.uat_backup_restore.frappe")
    def test_get_rclone_config_requires_remote_path(self, frappe: Mock) -> None:
        frappe.conf.get.return_value = None

        with self.assertRaises(click.ClickException) as error:
            get_rclone_config()

        self.assertIn("uat_backup_rclone_remote_path", str(error.exception))

    @patch("connect_diagnostics_core.commands.uat_backup_restore.get_rclone_executable")
    def test_build_rclone_command_includes_optional_config(self, get_rclone_executable: Mock) -> None:
        get_rclone_executable.return_value = "/usr/bin/rclone"

        command = build_rclone_command(
            ["lsjson", "gdrive:backups"],
            rclone_config=RcloneConfig(
                remote_path="gdrive:backups",
                config_path="/home/erp/.config/rclone/rclone.conf",
            ),
        )

        self.assertEqual(
            command,
            [
                "/usr/bin/rclone",
                "--config",
                "/home/erp/.config/rclone/rclone.conf",
                "lsjson",
                "gdrive:backups",
            ],
        )

    @patch("connect_diagnostics_core.commands.uat_backup_restore.run_rclone_command")
    def test_list_rclone_files_skips_directories_and_uses_names(self, run_rclone_command: Mock) -> None:
        run_rclone_command.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                [
                    {"Name": "folder", "IsDir": True},
                    {
                        "Path": "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                        "Name": "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                        "Size": 123,
                        "ModTime": "2026-06-21T12:00:03Z",
                    },
                ]
            ),
        )

        files = list_rclone_files(RcloneConfig(remote_path="gdrive:backups"))

        self.assertEqual(
            files,
            [
                RcloneBackupFile(
                    name="20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                    path="20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                    modified_time="2026-06-21T12:00:03Z",
                    size=123,
                )
            ],
        )
        run_rclone_command.assert_called_once_with(
            ["lsjson", "gdrive:backups", "--files-only"],
            rclone_config=RcloneConfig(remote_path="gdrive:backups"),
            capture_output=True,
        )

    @patch("connect_diagnostics_core.commands.uat_backup_restore.run_rclone_command")
    def test_download_rclone_file_uses_copyto(self, run_rclone_command: Mock) -> None:
        def write_downloaded_file(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            Path(args[2]).write_bytes(b"backup")
            return subprocess.CompletedProcess(args=args, returncode=0)

        run_rclone_command.side_effect = write_downloaded_file

        with TemporaryDirectory() as temporary_directory:
            downloaded_path = download_rclone_file(
                RcloneConfig(remote_path="gdrive:backups"),
                RcloneBackupFile(
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                ),
                Path(temporary_directory),
            )

        self.assertEqual(
            downloaded_path.name, "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"
        )
        run_rclone_command.assert_called_once_with(
            [
                "copyto",
                "gdrive:backups/20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                str(downloaded_path),
            ],
            rclone_config=RcloneConfig(remote_path="gdrive:backups"),
        )

    @patch("pathlib.Path.mkdir")
    @patch("connect_diagnostics_core.commands.uat_backup_restore.os.access")
    @patch("connect_diagnostics_core.commands.uat_backup_restore.frappe")
    def test_staging_dir_is_not_inside_frappe_backup_folder(
        self,
        frappe: Mock,
        os_access: Mock,
        path_mkdir: Mock,
    ) -> None:
        frappe.get_site_path.side_effect = lambda *parts: (
            "/sites/deverp.connectdiagnostics.net/" + "/".join(parts)
        )
        os_access.return_value = True

        staging_dir = ensure_staging_dir()

        self.assertEqual(
            staging_dir,
            Path("/sites/deverp.connectdiagnostics.net/private/uat_restore_staging"),
        )
        self.assertNotIn("/private/backups/", str(staging_dir))
        path_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("connect_diagnostics_core.commands.uat_backup_restore.frappe")
    def test_validate_environment_guard_requires_development_marker(self, frappe: Mock) -> None:
        frappe.conf.get.side_effect = lambda key: {
            "environment": "uat",
            "allow_uat_restore": 1,
        }.get(key)

        with self.assertRaises(click.ClickException) as error:
            validate_environment_guard("deverp.connectdiagnostics.net")

        self.assertIn("environment must be 'development'", str(error.exception))

    @patch("connect_diagnostics_core.commands.uat_backup_restore.frappe")
    def test_validate_environment_guard_requires_restore_marker(self, frappe: Mock) -> None:
        frappe.conf.get.side_effect = lambda key: {
            "environment": "development",
            "allow_uat_restore": 0,
        }.get(key)

        with self.assertRaises(click.ClickException) as error:
            validate_environment_guard("deverp.connectdiagnostics.net")

        self.assertIn("allow_uat_restore must be enabled", str(error.exception))


class TestUatBackupRestoreCommands(TestCase):
    @patch("connect_diagnostics_core.commands.uat_backup_restore.prepare_restore")
    def test_test_command_checks_without_download(self, prepare_restore: Mock) -> None:
        prepare_restore.return_value = (
            RcloneBackupFile(
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
            ),
            None,
            "/home/frappe/frappe-bench",
        )

        result = CliRunner().invoke(
            test_uat_backup_restore_command,
            ["--source-site-slug", "uat_erp_connectdiagnostics_net"],
            obj={"sites": ["deverp.connectdiagnostics.net"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        prepare_restore.assert_called_once_with(
            "deverp.connectdiagnostics.net",
            "uat_erp_connectdiagnostics_net",
            download=False,
        )
        self.assertIn("download skipped", result.output)

    @patch("connect_diagnostics_core.commands.uat_backup_restore.prepare_restore")
    def test_test_command_can_download_without_restore(self, prepare_restore: Mock) -> None:
        prepare_restore.return_value = (
            RcloneBackupFile(
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
            ),
            Path("/tmp/20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"),
            "/home/frappe/frappe-bench",
        )

        result = CliRunner().invoke(
            test_uat_backup_restore_command,
            ["--source-site-slug", "uat_erp_connectdiagnostics_net", "--download"],
            obj={"sites": ["deverp.connectdiagnostics.net"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        prepare_restore.assert_called_once_with(
            "deverp.connectdiagnostics.net",
            "uat_erp_connectdiagnostics_net",
            download=True,
        )
        self.assertIn("downloaded to /tmp/20260621_120003", result.output)

    @patch("connect_diagnostics_core.commands.uat_backup_restore.run_bench_command")
    @patch("connect_diagnostics_core.commands.uat_backup_restore.prepare_restore")
    def test_restore_command_dry_run_does_not_run_bench(
        self,
        prepare_restore: Mock,
        run_bench_command: Mock,
    ) -> None:
        prepare_restore.return_value = (
            RcloneBackupFile(
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
            ),
            None,
            "/home/frappe/frappe-bench",
        )

        result = CliRunner().invoke(
            restore_uat_backup,
            ["--source-site-slug", "uat_erp_connectdiagnostics_net", "--dry-run"],
            obj={"sites": ["deverp.connectdiagnostics.net"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        prepare_restore.assert_called_once_with(
            "deverp.connectdiagnostics.net",
            "uat_erp_connectdiagnostics_net",
            download=False,
        )
        run_bench_command.assert_not_called()

    @patch("connect_diagnostics_core.commands.uat_backup_restore.run_bench_command")
    @patch("connect_diagnostics_core.commands.uat_backup_restore.prepare_restore")
    def test_restore_command_runs_backup_restore_migrate_and_clear_cache(
        self,
        prepare_restore: Mock,
        run_bench_command: Mock,
    ) -> None:
        downloaded_path = Path("/tmp/20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz")
        prepare_restore.return_value = (
            RcloneBackupFile(
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
                "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz",
            ),
            downloaded_path,
            "/home/frappe/frappe-bench",
        )

        result = CliRunner().invoke(
            restore_uat_backup,
            ["--source-site-slug", "uat_erp_connectdiagnostics_net"],
            obj={"sites": ["deverp.connectdiagnostics.net"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            run_bench_command.call_args_list,
            [
                call(
                    ["--site", "deverp.connectdiagnostics.net", "backup", "--ignore-backup-conf"],
                    bench_path="/home/frappe/frappe-bench",
                ),
                call(
                    [
                        "--site",
                        "deverp.connectdiagnostics.net",
                        "restore",
                        str(downloaded_path),
                        "--force",
                    ],
                    bench_path="/home/frappe/frappe-bench",
                ),
                call(
                    ["--site", "deverp.connectdiagnostics.net", "migrate"],
                    bench_path="/home/frappe/frappe-bench",
                ),
                call(
                    ["--site", "deverp.connectdiagnostics.net", "clear-cache"],
                    bench_path="/home/frappe/frappe-bench",
                ),
            ],
        )
