# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHEETS_API = "sheets"
SHEETS_VERSION = "v4"

CACHE_PREFIX = "master_data_sheet"
CACHE_TTL = 5  # 5 seconds

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_credentials() -> Credentials:
	creds_path: str = cast(str, frappe.conf.get("google_credentials_path") or "")
	if not creds_path:
		msg = "Google credentials path not configured. Set via: bench --site <site> set-config google_credentials_path '/path/to/service-account.json'"
		raise frappe.ValidationError(msg)

	return Credentials.from_service_account_file(creds_path, scopes=SCOPES)


def _get_sheets_service():
	creds = _get_credentials()
	return build(SHEETS_API, SHEETS_VERSION, credentials=creds)


def get_sheet_data(spreadsheet_id: str, range_name: str) -> list[list[str]]:
	cache_key = f"{CACHE_PREFIX}:{spreadsheet_id}:{range_name}"
	cached: list[list[str]] | None = cast(list[list[str]] | None, frappe.cache().get_value(cache_key))
	if cached is not None:
		return cached

	service = _get_sheets_service()
	result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()

	values: list[list[str]] = result.get("values", [])
	frappe.cache().set_value(cache_key, values, expires_in_sec=CACHE_TTL)
	return values


def ensure_sheet_tab(spreadsheet_id: str, title: str) -> None:
	service = _get_sheets_service()
	body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
	try:
		service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
	except HttpError as e:
		if "already exists" not in str(e).lower():
			raise


def write_results(
	spreadsheet_id: str,
	range_name: str,
	rows: list[list[str]],
	tab_title: str = "",
) -> None:
	if tab_title:
		ensure_sheet_tab(spreadsheet_id, tab_title)
	service = _get_sheets_service()
	body = {"values": rows}
	service.spreadsheets().values().update(
		spreadsheetId=spreadsheet_id,
		range=range_name,
		valueInputOption="RAW",
		body=body,
	).execute()
