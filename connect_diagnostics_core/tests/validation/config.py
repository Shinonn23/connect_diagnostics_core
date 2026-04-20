# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass

import frappe


@dataclass(frozen=True)
class ValidationConfig:
	"""Configuration read from frappe.conf via bench set-config."""

	google_sheet_id: str
	config_sheet_id: str
	google_credentials_path: str | None
	google_drive_report_folder: str | None


def get_config(conf: dict) -> ValidationConfig:
	"""Read validation configuration from frappe.conf.

	Required keys (set via `bench --site sitename set-config <key> <value>`):
	    - google_sheet_id: Master data Google Sheet ID (42 tabs)
	    - config_sheet_id: Config Google Sheet ID (3 tabs: SheetConfigs, FieldMappings, Aliases)

	Optional keys:
	    - google_credentials_path: Path to Service Account JSON key file
	    - google_drive_report_folder: Google Drive folder ID for validation reports
	"""
	google_sheet_id = conf.get("google_sheet_id")
	config_sheet_id = conf.get("config_sheet_id")

	if not google_sheet_id:
		frappe.throw("google_sheet_id not set. Run: bench --site sitename set-config google_sheet_id <id>")
	if not config_sheet_id:
		frappe.throw("config_sheet_id not set. Run: bench --site sitename set-config config_sheet_id <id>")

	return ValidationConfig(
		google_sheet_id=google_sheet_id,
		config_sheet_id=config_sheet_id,
		google_credentials_path=conf.get("google_credentials_path"),
		google_drive_report_folder=conf.get("google_drive_report_folder"),
	)
