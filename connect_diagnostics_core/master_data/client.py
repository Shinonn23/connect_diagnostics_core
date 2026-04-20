# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SHEETS_API = "sheets"
SHEETS_VERSION = "v4"

CACHE_PREFIX = "master_data_sheet"
CACHE_TTL = 300  # 5 minutes


def _get_credentials() -> Credentials:
	creds_path: str = cast(str, frappe.conf.cd_google_credentials_path or "")
	if not creds_path:
		msg = "Google credentials path not configured. Set via: bench --site <site> set-config cd_google_credentials_path '/path/to/service-account.json'"
		raise frappe.ValidationError(msg)

	return Credentials.from_service_account_file(
		creds_path,
		scopes=["https://www.googleapis.com/auth/spreadsheets"],
	)


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


def write_results(
	spreadsheet_id: str,
	range_name: str,
	rows: list[list[str]],
) -> None:
	service = _get_sheets_service()
	body = {"values": rows}
	service.spreadsheets().values().update(
		spreadsheetId=spreadsheet_id,
		range=range_name,
		valueInputOption="RAW",
		body=body,
	).execute()
