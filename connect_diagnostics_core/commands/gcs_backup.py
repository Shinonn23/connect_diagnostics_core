# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import cast

import click
import frappe
from frappe.commands import get_site, pass_context
from frappe.utils.bench_helper import CliCtxObj
from google.cloud import storage


@click.command("push-backup")
@pass_context
def push_backup(context: CliCtxObj) -> None:
	"""Backup site and upload to Google Cloud Storage."""
	site = get_site(context)
	with frappe.init_site(site):
		frappe.connect()
		bucket_name: str = cast(str, frappe.conf.get("gcs_backup_bucket") or "")
		if not bucket_name:
			click.echo("Error: gcs_backup_bucket not configured.")
			click.echo(f"Run: bench --site {site} set-config gcs_backup_bucket '<bucket_name>'")
			raise SystemExit(1)

		backup_dir = _run_backup(site)
		zip_path = _create_zip(backup_dir, site)
		gcs_url = _upload_to_gcs(bucket_name, site, zip_path)
		click.echo(f"Backup uploaded to: {gcs_url}")

		os.remove(zip_path)
		frappe.destroy()


def _run_backup(site: str) -> str:
	from frappe.utils.backups import scheduled_backup

	odb = scheduled_backup(
		site=site,
		ignore_missing=True,
		backup_path_db=None,
		backup_path_files=None,
		backup_path_private_files=None,
		backup_path_conf=None,
	)
	db_path: str = odb.backup_path_db
	site_config_path: str = odb.backup_path_conf

	if not db_path or not os.path.exists(db_path):
		click.echo("Error: Database backup failed.")
		raise SystemExit(1)
	if not site_config_path or not os.path.exists(site_config_path):
		click.echo("Error: Site config backup failed.")
		raise SystemExit(1)

	backup_dir = str(Path(db_path).parent)
	click.echo(f"Backup created: {db_path}")
	click.echo(f"Site config: {site_config_path}")
	return backup_dir


def _create_zip(backup_dir: str, site: str) -> str:
	db_files = sorted(Path(backup_dir).glob(f"*{site}*-database.sql.gz"))
	conf_files = sorted(Path(backup_dir).glob(f"*{site}*-site_config_backup.json"))

	if not db_files:
		click.echo("Error: No database backup file found.")
		raise SystemExit(1)

	db_file = db_files[-1]
	conf_file = conf_files[-1] if conf_files else None

	timestamp = db_file.name.split("-")[0]
	zip_name = f"{timestamp}-{site}-backup.zip"
	zip_path = os.path.join(backup_dir, zip_name)

	with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
		zf.write(db_file, db_file.name)
		if conf_file:
			zf.write(conf_file, conf_file.name)

	click.echo(f"Created zip: {zip_path} ({_format_size(os.path.getsize(zip_path))})")
	return zip_path


def _upload_to_gcs(bucket_name: str, site: str, zip_path: str) -> str:
	client = storage.Client()
	bucket = client.bucket(bucket_name)

	if not bucket.exists():
		click.echo(f"Error: GCS bucket '{bucket_name}' does not exist.")
		raise SystemExit(1)

	zip_name = Path(zip_path).name
	blob_path = f"{site}/{zip_name}"
	blob = bucket.blob(blob_path)
	blob.upload_from_filename(zip_path)

	gcs_url = f"gs://{bucket_name}/{blob_path}"
	click.echo(f"Uploaded {blob_path} ({_format_size(os.path.getsize(zip_path))})")
	return gcs_url


def _format_size(size_bytes: int) -> str:
	if size_bytes < 1024:
		return f"{size_bytes}B"
	if size_bytes < 1024 * 1024:
		return f"{size_bytes / 1024:.1f}KB"
	return f"{size_bytes / (1024 * 1024):.1f}MB"
