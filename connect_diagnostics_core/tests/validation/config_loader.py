"""อ่าน config (SheetConfigs, FieldMappings, Aliases) จาก Google Sheet แล้วสร้าง config objects"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .sheets_reader import load_config_data


class FieldMapping:
	"""Mapping ระหว่าง Google Sheet column ↔ ERPNext API field"""

	__slots__ = (
		"alias_type",
		"api",
		"boolean_field",
		"excel",
		"first_name_only",
		"fuzzy_match",
		"ignore_case",
		"skip_when",
	)

	def __init__(
		self,
		excel: list[str],
		api: str,
		ignore_case: bool = False,
		fuzzy_match: str | None = None,
		boolean_field: bool = False,
		alias_type: str | None = None,
		first_name_only: bool = False,
		skip_when: Callable[[dict[str, Any]], bool] | None = None,
	):
		self.excel = excel
		self.api = api
		self.ignore_case = ignore_case
		self.fuzzy_match = fuzzy_match
		self.boolean_field = boolean_field
		self.alias_type = alias_type
		self.first_name_only = first_name_only
		self.skip_when = skip_when


class SheetConfig:
	"""Config สำหรับ mapping แต่ละ Google Sheet tab ↔ ERPNext DocType"""

	__slots__ = (
		"composite_key",
		"doctype",
		"fields",
		"filters",
		"key_api",
		"key_excel",
		"key_extractor",
		"key_fuzzy_match",
		"key_ignore_case",
		"label",
		"sheet_name",
	)

	def __init__(
		self,
		sheet_name: str,
		doctype: str,
		label: str,
		key_excel: list[str],
		key_api: str,
		key_ignore_case: bool = False,
		key_fuzzy_match: str | None = None,
		fields: list[FieldMapping] | None = None,
		composite_key: Callable[[dict[str, Any]], str] | None = None,
		filters: dict[str, Any] | None = None,
		key_extractor: Callable[[str], str] | None = None,
	):
		self.sheet_name = sheet_name
		self.doctype = doctype
		self.label = label
		self.key_excel = key_excel
		self.key_api = key_api
		self.key_ignore_case = key_ignore_case
		self.key_fuzzy_match = key_fuzzy_match
		self.fields = fields or []
		self.composite_key = composite_key
		self.filters = filters
		self.key_extractor = key_extractor


# --- Handler registries: string identifier → callable ---
# เพิ่ม handler ใหม่ที่นี่เมื่อต้องการ logic พิเศษ (แทบไม่ต้องเปลี่ยน)

SKIP_WHEN_HANDLERS: dict[str, Callable[[dict[str, Any]], bool]] = {
	"not_is_stock_item": lambda rec: not rec.get("is_stock_item"),
}

KEY_EXTRACTOR_HANDLERS: dict[str, Callable[[str], str]] = {
	"split_dash": lambda val: val.split(" - ")[0].strip(),
}

COMPOSITE_KEY_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
	"item_code_pipe_price_list": lambda row: f"{row.get('Item Code', '')}|{row.get('Price List', '')}",
}


def _str_to_bool(val: Any) -> bool:
	"""แปลง string เป็น boolean (true/1/yes/✓ → True)"""
	if isinstance(val, bool):
		return val
	if isinstance(val, str):
		return val.strip().lower() in ("true", "1", "yes", "\u2713")
	return False


def _parse_filters(filters_str: str | None) -> dict[str, Any] | None:
	"""แปลง filter string เช่น 'company=Connect Diagnostics;is_group=1' → dict"""
	if not filters_str or not filters_str.strip():
		return None
	result: dict[str, Any] = {}
	for pair in filters_str.split(";"):
		pair = pair.strip()
		if "=" not in pair:
			continue
		key, value = pair.split("=", 1)
		result[key.strip()] = value.strip()
	return result if result else None


def load_aliases(config_data: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, list[str]]]:
	"""อ่าน Aliases tab แล้วสร้าง alias mapping แยกตาม alias_type"""
	alias_rows = config_data.get("Aliases", [])
	result: dict[str, dict[str, list[str]]] = {}
	for row in alias_rows:
		alias_type = str(row.get("alias_type", "")).strip()
		key = str(row.get("key", "")).strip()
		values_str = str(row.get("values", "")).strip()
		if not alias_type or not key:
			continue
		if alias_type not in result:
			result[alias_type] = {}
		result[alias_type][key] = [v.strip() for v in values_str.split(";") if v.strip()]
	return result


def load_field_mappings(
	config_data: dict[str, list[dict[str, Any]]],
	sheet_name: str,
) -> list[FieldMapping]:
	"""อ่าน FieldMappings tab แล้วสร้าง FieldMapping objects สำหรับ sheet_name ที่ระบุ"""
	field_rows = config_data.get("FieldMappings", [])
	mappings: list[FieldMapping] = []
	for row in field_rows:
		row_sheet = str(row.get("sheet_name", "")).strip()
		if row_sheet != sheet_name:
			continue
		excel_str = str(row.get("excel_column", "")).strip()
		api_field = str(row.get("api_field", "")).strip()
		if not excel_str or not api_field:
			continue
		mappings.append(
			FieldMapping(
				excel=[c.strip() for c in excel_str.split(";") if c.strip()],
				api=api_field,
				ignore_case=_str_to_bool(row.get("ignore_case")),
				fuzzy_match=str(row.get("fuzzy_match", "")).strip() or None,
				boolean_field=_str_to_bool(row.get("boolean_field")),
				alias_type=str(row.get("alias_type", "")).strip() or None,
				first_name_only=_str_to_bool(row.get("first_name_only")),
				skip_when=SKIP_WHEN_HANDLERS.get(str(row.get("skip_when", "")).strip()),
			)
		)
	return mappings


def load_all_configs() -> tuple[list[SheetConfig], dict[str, dict[str, list[str]]]]:
	"""โหลด config ทั้งหมดจาก Google Sheet → (SheetConfig list, alias mapping)"""
	config_data = load_config_data()

	sheet_rows = config_data.get("SheetConfigs", [])
	configs: list[SheetConfig] = []

	for row in sheet_rows:
		sheet_name = str(row.get("sheet_name", "")).strip()
		doctype = str(row.get("doctype", "")).strip()
		label = str(row.get("label", "")).strip()
		key_excel_str = str(row.get("key_excel", "")).strip()
		key_api = str(row.get("key_api", "")).strip()
		if not sheet_name or not doctype:
			continue

		key_fuzzy = str(row.get("key_fuzzy_match", "")).strip() or None
		key_extractor_name = str(row.get("key_extractor", "")).strip() or None
		composite_key_name = str(row.get("composite_key", "")).strip() or None

		config = SheetConfig(
			sheet_name=sheet_name,
			doctype=doctype,
			label=label or sheet_name,
			key_excel=[k.strip() for k in key_excel_str.split(";") if k.strip()],
			key_api=key_api,
			key_ignore_case=_str_to_bool(row.get("key_ignore_case")),
			key_fuzzy_match=key_fuzzy,
			fields=load_field_mappings(config_data, sheet_name),
			composite_key=COMPOSITE_KEY_HANDLERS.get(composite_key_name) if composite_key_name else None,
			filters=_parse_filters(str(row.get("filters", "")).strip()),
			key_extractor=KEY_EXTRACTOR_HANDLERS.get(key_extractor_name) if key_extractor_name else None,
		)
		configs.append(config)

	aliases = load_aliases(config_data)
	print(f"  Loaded {len(configs)} sheet configs, {sum(len(c.fields) for c in configs)} field mappings")
	return configs, aliases
