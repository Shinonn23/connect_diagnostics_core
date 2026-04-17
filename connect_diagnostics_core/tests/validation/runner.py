"""Runner สำหรับรัน validation ผ่าน bench command — ดึง config จาก Google Sheet"""

from typing import Any

from .config_loader import SheetConfig, load_all_configs
from .sheets_reader import get_sheet, load_master_data
from .validator import ValidationResult, print_result, print_summary, validate_sheet


def _get_api_records(
	doctype: str, fields: list[str], filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
	"""ดึง records จาก Frappe API โดยใช้ frappe.get_all (bench context)"""
	import frappe

	filters = filters or {}
	return frappe.get_all(doctype, fields=fields, filters=filters, limit_page_length=0)


def _run_validation_for_configs(
	configs: list[SheetConfig], aliases: dict[str, dict[str, list[str]]]
) -> list[ValidationResult]:
	"""รัน validation สำหรับ list ของ SheetConfig"""
	sheet_data = load_master_data()
	all_results: list[ValidationResult] = []

	for config in configs:
		sheet_rows = get_sheet(sheet_data, config.sheet_name)
		api_fields = ["name", *list({f.api for f in config.fields})]
		if config.key_api != "name" and config.key_api not in api_fields:
			api_fields.append(config.key_api)

		try:
			api_records = _get_api_records(config.doctype, api_fields, config.filters)
		except Exception as e:
			print(f"  ERROR fetching {config.doctype}: {e}")
			api_records = []

		result = validate_sheet(sheet_rows, api_records, config, aliases)
		all_results.append(result)
		print_result(result)

	print_summary(all_results)
	return all_results


def run_master_validation() -> None:
	"""รัน master data validation — อ่าน config จาก Google Sheet แล้ว validate ทุก sheet"""
	configs, aliases = load_all_configs()
	if not configs:
		print("  No sheet configs found — ตรวจสอบ CONFIG_SHEET_ID ใน .env")
		return
	results = _run_validation_for_configs(configs, aliases)
	failed = [r for r in results if not r.passed]
	if failed:
		print(f"\n  {len(failed)} sheet(s) failed validation")
	else:
		print("\n  All master data validated successfully!")


def run_stock_validation() -> None:
	"""รัน stock data validation — validate เฉพาะ stock-related sheets"""
	configs, aliases = load_all_configs()
	stock_sheet_names = {"Items", "Warehouses", "UOMs", "Brands", "Item_Groups"}
	stock_configs = [c for c in configs if c.sheet_name in stock_sheet_names]
	if not stock_configs:
		print("  No stock sheet configs found")
		return
	results = _run_validation_for_configs(stock_configs, aliases)
	failed = [r for r in results if not r.passed]
	if failed:
		print(f"\n  {len(failed)} sheet(s) failed validation")
	else:
		print("\n  All stock data validated successfully!")
