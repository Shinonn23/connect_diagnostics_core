# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

import click
from click.testing import CliRunner

from connect_diagnostics_core.commands.uat_backup_restore import (
    GoogleDriveBackupFile,
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
                GoogleDriveBackupFile(
                    "old", "20260620_190631-uat_erp_connectdiagnostics_net-database.sql.gz"
                ),
                GoogleDriveBackupFile(
                    "sidecar",
                    "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz:Zone.Identifier",
                ),
                GoogleDriveBackupFile(
                    "dev", "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz"
                ),
                GoogleDriveBackupFile(
                    "latest", "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"
                ),
            ],
            "uat_erp_connectdiagnostics_net",
        )

        self.assertEqual(backup_file.file_id, "latest")

    def test_select_latest_database_backup_fails_when_no_candidate_exists(self) -> None:
        with self.assertRaises(click.ClickException):
            select_latest_database_backup(
                [
                    GoogleDriveBackupFile(
                        "dev", "20260621_120005-dev_erp_connectdiagnostics_net-database.sql.gz"
                    )
                ],
                "uat_erp_connectdiagnostics_net",
            )

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
            GoogleDriveBackupFile("latest", "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"),
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
            GoogleDriveBackupFile("latest", "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"),
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
            GoogleDriveBackupFile("latest", "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"),
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
            GoogleDriveBackupFile("latest", "20260621_120003-uat_erp_connectdiagnostics_net-database.sql.gz"),
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
