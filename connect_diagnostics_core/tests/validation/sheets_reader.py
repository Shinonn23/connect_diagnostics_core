"""Google Sheets API reader — ดึงข้อมูลจาก Google Sheets ผ่าน batchGet รองรับ ADC และ Service Account"""

import os
from typing import Any

from google.oauth2 import service_account
from google.auth.credentials import Credentials
import google.auth

try:
	from googleapiclient.discovery import build
except ImportError:
	build = None

DEFAULT_SHEET_ID = "1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ"

_data_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}


def _get_credentials() -> Credentials:
	"""สร้าง Google Auth credential — เช็ค Service Account ก่อน ถ้าไม่มีจะใช้ ADC (gcloud auth)"""
	sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
	if sa_path and os.path.exists(sa_path):
		return service_account.Credentials.from_service_account_file(
			sa_path,
			scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
		)
	credentials, _ = google.auth.default(
		scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
	)
	return credentials


def _get_sheets_service():
	"""สร้าง Google Sheets API service"""
	if build is None:
		raise ImportError("google-api-python-client ไม่ได้ติดตั้ง — รัน bench pip install google-api-python-client")
	credentials = _get_credentials()
	return build("sheets", "v4", credentials=credentials)


def _rows_to_dicts(value_ranges: list, titles: list[str]) -> dict[str, list[dict[str, Any]]]:
	"""แปลง valueRanges เป็น dict ของ list[dict] โดยใช้แถวแรกเป็น header"""
	result: dict[str, list[dict[str, Any]]] = {}
	for i, title in enumerate(titles):
		rows = value_ranges[i].get("values", []) if i < len(value_ranges) else []
		if len(rows) <= 1:
			result[title] = []
			continue
		headers = rows[0]
		data = []
		for row in rows[1:]:
			record = {}
			for c, header in enumerate(headers):
				record[header] = row[c] if c < len(row) else ""
			data.append(record)
		result[title] = data
	return result


def fetch_google_sheets(sheet_id: str) -> dict[str, list[dict[str, Any]]]:
	"""โหลดข้อมูลทั้งหมดจาก Google Sheets API โดยใช้ batchGet (2 API calls)"""
	service = _get_sheets_service()
	sheets_api = service.spreadsheets()

	meta = sheets_api.get(spreadsheetId=sheet_id).execute()
	titles = [
		s["properties"]["title"] for s in meta.get("sheets", []) if s.get("properties", {}).get("title")
	]

	if not titles:
		return {}

	batch_res = sheets_api.values().batchGet(spreadsheetId=sheet_id, ranges=titles).execute()
	value_ranges = batch_res.get("valueRanges", [])

	result = _rows_to_dicts(value_ranges, titles)
	print(f"  Loaded {len(result)} sheets from Google Sheets (batchGet: 2 API calls)")
	return result


def fetch_sheet_tabs(sheet_id: str, tab_names: list[str]) -> dict[str, list[dict[str, Any]]]:
	"""โหลดเฉพาะ tabs ที่ระบุจาก Google Sheets"""
	service = _get_sheets_service()
	sheets_api = service.spreadsheets()

	batch_res = sheets_api.values().batchGet(spreadsheetId=sheet_id, ranges=tab_names).execute()
	value_ranges = batch_res.get("valueRanges", [])
	return _rows_to_dicts(value_ranges, tab_names)


def load_master_data() -> dict[str, list[dict[str, Any]]]:
	"""โหลด Master Data จาก Google Sheets (cache ถ้าโหลดแล้ว)"""
	sheet_id = os.environ.get("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID)
	if sheet_id in _data_cache:
		return _data_cache[sheet_id]
	print(f"  Google Sheets Master Data: {sheet_id}")
	data = fetch_google_sheets(sheet_id)
	_data_cache[sheet_id] = data
	return data


def load_config_data() -> dict[str, list[dict[str, Any]]]:
	"""โหลด Config (SheetConfigs, FieldMappings, Aliases) จาก Google Sheet แยก"""
	config_sheet_id = os.environ.get("CONFIG_SHEET_ID")
	if not config_sheet_id:
		raise ValueError("CONFIG_SHEET_ID not set in .env — รัน python setup_config_sheet.py ก่อน")
	if config_sheet_id in _data_cache:
		return _data_cache[config_sheet_id]
	print(f"  Google Sheets Config: {config_sheet_id}")
	tabs = ["SheetConfigs", "FieldMappings", "Aliases"]
	data = fetch_sheet_tabs(config_sheet_id, tabs)
	_data_cache[config_sheet_id] = data
	return data


def get_sheet(data: dict[str, list[dict[str, Any]]], sheet_name: str) -> list[dict[str, Any]]:
	"""ดึง rows ของ sheet ตามชื่อจาก data ที่โหลดแล้ว"""
	rows = data.get(sheet_name)
	if rows is None:
		print(f'  WARNING: Sheet "{sheet_name}" not found')
		return []
	return rows


def clear_cache() -> None:
	"""ล้าง cache ทั้งหมด"""
	_data_cache.clear()
