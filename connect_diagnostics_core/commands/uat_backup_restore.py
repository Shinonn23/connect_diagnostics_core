# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import frappe
from frappe.commands import pass_context
from frappe.utils import get_bench_path

DEFAULT_SOURCE_SITE_SLUG = "uat_erp_connectdiagnostics_net"
STAGING_FOLDER_NAME = "uat_restore_staging"


@dataclass(frozen=True)
class RcloneBackupFile:
    name: str
    path: str
    modified_time: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class RcloneConfig:
    remote_path: str
    config_path: str | None = None


@click.command("restore-uat-backup")
@click.option(
    "--source-site-slug",
    default=DEFAULT_SOURCE_SITE_SLUG,
    show_default=True,
    help="Source site slug used in Frappe backup filenames.",
)
@click.option("--dry-run", is_flag=True, help="Validate and locate the latest backup without restoring.")
@pass_context
def restore_uat_backup(context: Any, source_site_slug: str, dry_run: bool) -> None:
    """Download the latest UAT database backup with rclone and restore it to this site."""

    site = get_single_site(context)
    backup_file, downloaded_path, bench_path = prepare_restore(site, source_site_slug, download=not dry_run)

    if dry_run:
        click.echo(f"{site}: latest backup is {backup_file.name}")
        click.echo(f"{site}: dry run complete; database was not restored.")
        return

    if not downloaded_path:
        raise click.ClickException("Backup was not downloaded.")

    run_bench_command(["--site", site, "backup", "--ignore-backup-conf"], bench_path=bench_path)
    run_bench_command(["--site", site, "restore", str(downloaded_path), "--force"], bench_path=bench_path)
    run_bench_command(["--site", site, "migrate"], bench_path=bench_path)
    run_bench_command(["--site", site, "clear-cache"], bench_path=bench_path)
    click.echo(f"{site}: restored {backup_file.name}.")


@click.command("test-uat-backup-restore")
@click.option(
    "--source-site-slug",
    default=DEFAULT_SOURCE_SITE_SLUG,
    show_default=True,
    help="Source site slug used in Frappe backup filenames.",
)
@click.option("--download", is_flag=True, help="Download the latest backup into staging, but do not restore.")
@pass_context
def test_uat_backup_restore(context: Any, source_site_slug: str, download: bool) -> None:
    """Validate the UAT backup restore prerequisites without restoring the database."""

    site = get_single_site(context)
    backup_file, downloaded_path, _bench_path = prepare_restore(site, source_site_slug, download=download)
    click.echo(f"{site}: guard ok.")
    click.echo(f"{site}: latest backup is {backup_file.name}.")
    if downloaded_path:
        click.echo(f"{site}: downloaded to {downloaded_path}.")
    else:
        click.echo(f"{site}: download skipped.")


def prepare_restore(
    site: str,
    source_site_slug: str,
    *,
    download: bool,
) -> tuple[RcloneBackupFile, Path | None, str]:
    frappe.init(site=site)
    downloaded_path: Path | None = None
    try:
        validate_environment_guard(site)
        bench_path = get_bench_path()
        staging_dir = ensure_staging_dir()
        get_bench_executable()
        rclone_config = get_rclone_config()
        verify_rclone(rclone_config)

        backup_files = list_rclone_files(rclone_config)
        backup_file = select_latest_database_backup(backup_files, source_site_slug)

        if download:
            downloaded_path = download_rclone_file(rclone_config, backup_file, staging_dir)

        return backup_file, downloaded_path, bench_path
    finally:
        frappe.destroy()


def get_single_site(context: Any) -> str:
    sites = tuple(context.sites or ())
    if len(sites) != 1:
        raise click.UsageError("This command requires exactly one --site.")
    return sites[0]


def validate_environment_guard(site: str) -> None:
    environment = frappe.conf.get("environment")
    allow_uat_restore = frappe.conf.get("allow_uat_restore")

    if environment != "development":
        raise click.ClickException(
            f"{site}: site_config environment must be 'development' before restoring UAT backups."
        )
    if not is_truthy(allow_uat_restore):
        raise click.ClickException(
            f"{site}: site_config allow_uat_restore must be enabled before restoring UAT backups."
        )


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def ensure_staging_dir() -> Path:
    staging_dir = Path(frappe.get_site_path("private", "backups", STAGING_FOLDER_NAME))
    staging_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(staging_dir, os.W_OK):
        raise click.ClickException(f"Staging folder is not writable: {staging_dir}")
    return staging_dir


def get_rclone_config() -> RcloneConfig:
    remote_path = frappe.conf.get("uat_backup_rclone_remote_path")
    if not remote_path:
        raise click.ClickException(
            "site_config uat_backup_rclone_remote_path must point to the rclone backup folder."
        )

    config_path = frappe.conf.get("uat_backup_rclone_config_path")
    return RcloneConfig(
        remote_path=str(remote_path).rstrip("/"), config_path=str(config_path) if config_path else None
    )


def verify_rclone(rclone_config: RcloneConfig) -> None:
    get_rclone_executable()
    run_rclone_command(["version"], rclone_config=rclone_config, capture_output=True)


def list_rclone_files(rclone_config: RcloneConfig) -> list[RcloneBackupFile]:
    result = run_rclone_command(
        ["lsjson", rclone_config.remote_path, "--files-only"],
        rclone_config=rclone_config,
        capture_output=True,
    )
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as error:
        raise click.ClickException("rclone lsjson returned invalid JSON.") from error

    files: list[RcloneBackupFile] = []
    for file_data in data:
        if file_data.get("IsDir"):
            continue
        path = file_data.get("Path")
        name = file_data.get("Name") or path
        if not name or not path:
            continue
        files.append(
            RcloneBackupFile(
                name=str(name),
                path=str(path),
                modified_time=file_data.get("ModTime"),
                size=file_data.get("Size"),
            )
        )

    return files


def select_latest_database_backup(
    backup_files: list[RcloneBackupFile],
    source_site_slug: str,
) -> RcloneBackupFile:
    pattern = re.compile(rf"^(?P<timestamp>\d{{8}}_\d{{6}})-{re.escape(source_site_slug)}-database\.sql\.gz$")
    candidates: list[tuple[str, RcloneBackupFile]] = []

    for backup_file in backup_files:
        match = pattern.match(backup_file.name)
        if match:
            candidates.append((match.group("timestamp"), backup_file))

    if not candidates:
        raise click.ClickException(f"No database backup found for source site slug {source_site_slug}.")

    return max(candidates, key=lambda candidate: candidate[0])[1]


def download_rclone_file(
    rclone_config: RcloneConfig,
    backup_file: RcloneBackupFile,
    staging_dir: Path,
) -> Path:
    destination = staging_dir / backup_file.name
    source = f"{rclone_config.remote_path}/{backup_file.path}"
    run_rclone_command(["copyto", source, str(destination)], rclone_config=rclone_config)

    if not destination.exists() or destination.stat().st_size == 0:
        raise click.ClickException(f"Downloaded backup is empty: {destination}")

    return destination


def get_rclone_executable() -> str:
    executable = shutil.which("rclone")
    if executable:
        return executable
    raise click.ClickException("rclone executable was not found in PATH.")


def build_rclone_command(args: list[str], *, rclone_config: RcloneConfig) -> list[str]:
    command = [get_rclone_executable()]
    if rclone_config.config_path:
        command.extend(["--config", rclone_config.config_path])
    command.extend(args)
    return command


def run_rclone_command(
    args: list[str],
    *,
    rclone_config: RcloneConfig,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = build_rclone_command(args, rclone_config=rclone_config)
    if not capture_output:
        click.echo("Running: " + " ".join(command))
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def get_bench_executable() -> str:
    executable = shutil.which("bench")
    if executable:
        return executable
    if sys.argv and Path(sys.argv[0]).name == "bench":
        return sys.argv[0]
    raise click.ClickException("bench executable was not found in PATH.")


def run_bench_command(args: list[str], *, bench_path: str) -> None:
    command = [get_bench_executable(), *args]
    click.echo("Running: " + " ".join(command))
    subprocess.run(command, cwd=bench_path, check=True)
