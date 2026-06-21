# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

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
class GoogleDriveBackupFile:
    file_id: str
    name: str
    modified_time: str | None = None
    size: str | None = None


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
    """Download the latest UAT database backup from Google Drive and restore it to this site."""

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
) -> tuple[GoogleDriveBackupFile, Path | None, str]:
    frappe.init(site=site)
    downloaded_path: Path | None = None
    try:
        validate_environment_guard(site)
        bench_path = get_bench_path()
        staging_dir = ensure_staging_dir()
        get_bench_executable()

        frappe.connect()
        google_drive, account = get_google_drive_object()
        folder_id = get_backup_folder_id(account)
        backup_files = list_google_drive_files(google_drive, folder_id)
        backup_file = select_latest_database_backup(backup_files, source_site_slug)

        if download:
            downloaded_path = download_google_drive_file(google_drive, backup_file, staging_dir)

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


def get_google_drive_object() -> tuple[Any, Any]:
    from frappe.integrations.doctype.google_drive.google_drive import get_google_drive_object

    return get_google_drive_object()


def get_backup_folder_id(account: Any) -> str:
    backup_folder_id = getattr(account, "backup_folder_id", None)
    if not backup_folder_id:
        raise click.ClickException("Google Drive backup_folder_id is not configured.")
    return str(backup_folder_id)


def list_google_drive_files(google_drive: Any, folder_id: str) -> list[GoogleDriveBackupFile]:
    files: list[GoogleDriveBackupFile] = []
    page_token: str | None = None
    query = f"'{folder_id}' in parents and trashed=false"

    while True:
        request = google_drive.files().list(
            q=query,
            fields="nextPageToken, files(id, name, modifiedTime, size)",
            pageToken=page_token,
            pageSize=1000,
        )
        response = request.execute()
        for file_data in response.get("files", []):
            files.append(
                GoogleDriveBackupFile(
                    file_id=file_data["id"],
                    name=file_data["name"],
                    modified_time=file_data.get("modifiedTime"),
                    size=file_data.get("size"),
                )
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def select_latest_database_backup(
    backup_files: list[GoogleDriveBackupFile],
    source_site_slug: str,
) -> GoogleDriveBackupFile:
    pattern = re.compile(rf"^(?P<timestamp>\d{{8}}_\d{{6}})-{re.escape(source_site_slug)}-database\.sql\.gz$")
    candidates: list[tuple[str, GoogleDriveBackupFile]] = []

    for backup_file in backup_files:
        match = pattern.match(backup_file.name)
        if match:
            candidates.append((match.group("timestamp"), backup_file))

    if not candidates:
        raise click.ClickException(f"No database backup found for source site slug {source_site_slug}.")

    return max(candidates, key=lambda candidate: candidate[0])[1]


def download_google_drive_file(
    google_drive: Any,
    backup_file: GoogleDriveBackupFile,
    staging_dir: Path,
) -> Path:
    from googleapiclient.http import MediaIoBaseDownload

    destination = staging_dir / backup_file.name
    request = google_drive.files().get_media(fileId=backup_file.file_id)

    with destination.open("wb") as output_file:
        downloader = MediaIoBaseDownload(output_file, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()

    if destination.stat().st_size == 0:
        raise click.ClickException(f"Downloaded backup is empty: {destination}")

    return destination


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
