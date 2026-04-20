# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Google Sheets and Drive API reader with ADC and Service Account support."""

from __future__ import annotations

from typing import Any

import frappe
import google.auth
from google.auth.credentials import Credentials
from google.oauth2 import service_account

try:
	from googleapiclient.discovery import build
except ImportError:
	build = None  # ty: ignore[assignment] - optional dependency, falls back to None at runtime


def _get_credentials(credentials_path: str | None) -> Credentials:
	"""Return Google credentials. Prefers Service Account if path is set, otherwise ADC."""
	if credentials_path:
		return service_account.Credentials.from_service_account_file(
			credentials_path,
			scopes=[
				"https://www.googleapis.com/auth/spreadsheets.readonly",
				"https://www.googleapis.com/auth/drive.file",
			],
		)
	return google.auth.default(
		scopes=[
			"https://www.googleapis.com/auth/spreadsheets.readonly",
			"https://www.googleapis.com/auth/drive.file",
		],
	)[0]


def _get_service(credentials_path: str | None):
	"""Build and return a Google Sheets API service instance."""
	if build is None:
		raise ImportError(
			"google-api-python-client is not installed. Run: bench pip install google-api-python-client"
		)
	creds = _get_credentials(credentials_path)
	return build("sheets", "v4", credentials=creds)


def _get_drive_service(credentials_path: str | None):
	"""Build and return a Google Drive API service instance."""
	if build is None:
		raise ImportError(
			"google-api-python-client is not installed. Run: bench pip install google-api-python-client"
		)
	creds = _get_credentials(credentials_path)
	return build("drive", "v3", credentials=creds)


def _rows_to_dicts(value_ranges: list[Any], titles: list[str]) -> dict[str, list[dict[str, Any]]]:
	"""Convert Google Sheets valueRanges to dict of list-of-dicts, using first row as headers."""
	result: dict[str, list[dict[str, Any]]] = {}
	for i, title in enumerate(titles):
		rows: list[list[str]] = value_ranges[i].get("values", []) if i < len(value_ranges) else []
		if len(rows) <= 1:
			result[title] = []
			continue
		headers = rows[0]
		records: list[dict[str, Any]] = []
		for row in rows[1:]:
			record: dict[str, Any] = {}
			for c, header in enumerate(headers):
				record[header] = row[c] if c < len(row) else ""
			records.append(record)
		result[title] = records
	return result


def fetch_all_tabs(sheet_id: str, credentials_path: str | None) -> dict[str, list[dict[str, Any]]]:
	"""Load all tabs from a Google Sheet using batchGet (2 API calls)."""
	service = _get_service(credentials_path)
	sheets_api = service.spreadsheets()

	meta = sheets_api.get(spreadsheetId=sheet_id).execute()
	titles = [
		s["properties"]["title"] for s in meta.get("sheets", []) if s.get("properties", {}).get("title")
	]
	if not titles:
		return {}

	batch_res = sheets_api.values().batchGet(spreadsheetId=sheet_id, ranges=titles).execute()
	return _rows_to_dicts(batch_res.get("valueRanges", []), titles)


def fetch_tabs(
	sheet_id: str, tab_names: list[str], credentials_path: str | None
) -> dict[str, list[dict[str, Any]]]:
	"""Load specific tabs from a Google Sheet."""
	service = _get_service(credentials_path)
	sheets_api = service.spreadsheets()

	batch_res = sheets_api.values().batchGet(spreadsheetId=sheet_id, ranges=tab_names).execute()
	return _rows_to_dicts(batch_res.get("valueRanges", []), tab_names)


def load_master_data(sheet_id: str, credentials_path: str | None) -> dict[str, list[dict[str, Any]]]:
	"""Load master data from Google Sheet with caching via frappe.cache()."""
	cache_key = f"cd_validation:master:{sheet_id}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	print(f"  Loading master data from Google Sheet: {sheet_id}")
	data = fetch_all_tabs(sheet_id, credentials_path)
	print(f"  Loaded {len(data)} tabs")
	frappe.cache().set_value(cache_key, data)
	return data


def load_config_data(config_sheet_id: str, credentials_path: str | None) -> dict[str, list[dict[str, Any]]]:
	"""Load validation config (SheetConfigs, FieldMappings, Aliases) from a separate Google Sheet."""
	cache_key = f"cd_validation:config:{config_sheet_id}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	print(f"  Loading config from Google Sheet: {config_sheet_id}")
	data = fetch_tabs(config_sheet_id, ["SheetConfigs", "FieldMappings", "Aliases"], credentials_path)
	frappe.cache().set_value(cache_key, data)
	return data


def create_report_sheet(
	sheet_title: str,
	headers: list[str],
	rows: list[list[str]],
	folder_id: str,
	credentials_path: str | None,
) -> str:
	"""Create a new Google Sheet in the specified Drive folder and populate it. Returns the sheet URL."""
	from googleapiclient.http import MediaInMemoryUpload

	drive_service = _get_drive_service(credentials_path)

	file_metadata = {
		"name": sheet_title,
		"mimeType": "application/vnd.google-apps.spreadsheet",
		"parents": [folder_id],
	}
	spreadsheet = drive_service.files().create(body=file_metadata, fields="id, webViewLink").execute()
	spreadsheet_id = spreadsheet["id"]
	web_view_link = spreadsheet.get("webViewLink", "")

	sheets_service = _get_service(credentials_path)
	sheets_api = sheets_service.spreadsheets()

	all_values = [headers, *rows]
	sheets_api.values().update(
		spreadsheetId=spreadsheet_id,
		range="A1",
		valueInputOption="RAW",
		body={"values": all_values},
	).execute()

	return web_view_link


def clear_cache() -> None:
	"""Clear all cached validation data from frappe.cache()."""
	frappe.cache().delete_keys("cd_validation:")
