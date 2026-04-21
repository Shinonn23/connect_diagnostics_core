# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import cast

import click
import frappe
from frappe.commands import get_site, pass_context
from frappe.utils.bench_helper import CliCtxObj
from google.cloud import storage


@click.command("pull-backup")
@click.option("--date", default=None, help="Restore specific date (YYYY-MM-DD). Latest if omitted.")
@click.option(
	"--list", "list_only", is_flag=True, default=False, help="List available backups without restoring."
)
@pass_context
def pull_backup(context: CliCtxObj, date: str | None, list_only: bool) -> None:
	"""Download backup from Google Cloud Storage and restore site."""

	site = get_site(context)
	with frappe.init_site(site):
		frappe.connect()
		bucket_name: str = cast(str, frappe.conf.get("gcs_backup_bucket") or "")
		if not bucket_name:
			click.echo("Error: gcs_backup_bucket not configured.")
			click.echo(f"Run: bench --site {site} set-config gcs_backup_bucket '<bucket_name>'")
			raise SystemExit(1)

		backups = _list_backups(bucket_name, site)

		if not backups:
			click.echo(f"No backups found for site '{site}' in bucket '{bucket_name}'.")
			raise SystemExit(1)

		if list_only:
			_print_backups(backups)
			frappe.destroy()
			return

		target = _select_backup(backups, date)
		if not target:
			click.echo(f"No backup found for date '{date}'.")
			raise SystemExit(1)

		click.echo(f"Selected: {target.name}")

		with tempfile.TemporaryDirectory() as tmp_dir:
			zip_path = _download_from_gcs(bucket_name, target, tmp_dir)
			sql_path = _extract_zip(zip_path, tmp_dir)
			_run_restore(site, sql_path)

		click.echo("Restore complete.")
		frappe.destroy()


def _list_backups(bucket_name: str, site: str) -> list[storage.Blob]:
	client = storage.Client()
	bucket = client.bucket(bucket_name)
	prefix = f"{site}/"
	blobs = list(bucket.list_blobs(prefix=prefix))
	backups = [b for b in blobs if b.name.endswith(".zip")]
	backups.sort(key=lambda b: b.name, reverse=True)
	return backups


def _print_backups(backups: list[storage.Blob]) -> None:
	click.echo("\nAvailable backups:")
	click.echo("-" * 70)
	for i, blob in enumerate(backups, 1):
		name = Path(blob.name).stem
		size_mb = (blob.size or 0) / (1024 * 1024)
		updated = blob.updated.strftime("%Y-%m-%d %H:%M UTC") if blob.updated else "unknown"
		click.echo(f"  {i}. {name} | {size_mb:.1f}MB | {updated}")
	click.echo("-" * 70)
	click.echo(f"Total: {len(backups)} backup(s)")


def _select_backup(backups: list[storage.Blob], date: str | None) -> storage.Blob | None:
	if not date:
		return backups[0]

	for blob in backups:
		if date in blob.name:
			return blob
	return None


def _download_from_gcs(bucket_name: str, blob: storage.Blob, tmp_dir: str) -> str:
	client = storage.Client()
	bucket = client.bucket(bucket_name)
	source = bucket.blob(blob.name)

	zip_name = Path(blob.name).name
	zip_path = os.path.join(tmp_dir, zip_name)
	size_mb = (blob.size or 0) / (1024 * 1024)

	click.echo(f"Downloading {size_mb:.1f}MB...")
	source.download_to_filename(zip_path)
	click.echo(f"Downloaded to: {zip_path}")
	return zip_path


def _extract_zip(zip_path: str, tmp_dir: str) -> str:
	with zipfile.ZipFile(zip_path, "r") as zf:
		zf.extractall(tmp_dir)
		members = zf.namelist()

	sql_files = [f for f in members if f.endswith(".sql.gz")]
	if not sql_files:
		click.echo("Error: No .sql.gz file found in backup zip.")
		raise SystemExit(1)

	sql_path = os.path.join(tmp_dir, sql_files[0])
	click.echo(f"Extracted: {sql_files[0]}")
	return sql_path


def _run_restore(site: str, sql_path: str) -> None:
	from frappe.installer import restore_db

	db_root_password = frappe.conf.db_root_password or frappe.conf.get("db_root_password") or ""
	admin_password = frappe.conf.admin_password or frappe.conf.get("admin_password") or ""

	click.echo("Restoring database...")
	restore_db(
		sql_path,
		site,
		db_root_password=db_root_password,
		admin_password=admin_password,
	)
	click.echo("Database restored successfully.")
