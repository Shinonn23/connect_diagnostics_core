"""Sheet vs API field-by-field validation engine — เปรียบเทียบ Google Sheets กับ ERPNext API"""

import re
from typing import Any

from .config_loader import FieldMapping, SheetConfig


class FieldDiff:
	"""ผลต่างของ field เดียวระหว่าง Sheet กับ API"""

	__slots__ = ("field", "excel_value", "api_value")

	def __init__(self, field: str, excel_value: Any, api_value: Any):
		self.field = field
		self.excel_value = excel_value
		self.api_value = api_value

	def to_dict(self) -> dict:
		return {"field": self.field, "excelValue": self.excel_value, "apiValue": self.api_value}


class RecordDiff:
	"""ผลต่างของ record เดียว (key + list ของ FieldDiff)"""

	__slots__ = ("key", "diffs")

	def __init__(self, key: str, diffs: list[FieldDiff]):
		self.key = key
		self.diffs = diffs

	def to_dict(self) -> dict:
		return {"key": self.key, "diffs": [d.to_dict() for d in self.diffs]}


class ValidationResult:
	"""ผล validation ของ sheet เดียว"""

	__slots__ = (
		"sheet_name",
		"doctype",
		"label",
		"excel_count",
		"api_count",
		"matched",
		"missing_in_api",
		"extra_in_api",
		"field_mismatches",
		"passed",
	)

	def __init__(self, sheet_name: str, doctype: str, label: str):
		self.sheet_name = sheet_name
		self.doctype = doctype
		self.label = label
		self.excel_count = 0
		self.api_count = 0
		self.matched = 0
		self.missing_in_api: list[str] = []
		self.extra_in_api: list[str] = []
		self.field_mismatches: list[RecordDiff] = []
		self.passed = True


def normalize(val: Any) -> str:
	"""Normalize string โดยแปลงค่า None/empty เป็น string ว่าง และลบ whitespace ซ้ำ"""
	if val is None or val == "":
		return ""
	if isinstance(val, (int, float)):
		return str(val)
	s = str(val).strip()
	return re.sub(r"\s{2,}", " ", s)


def to_bool(val: Any) -> bool | None:
	"""แปลงค่าเป็น boolean รองรับ '1', 'yes', 'true', '0', 'no', 'false', '✓', '✗'"""
	if val is None or val == "":
		return None
	s = str(val).strip().lower()
	if s in ("1", "yes", "true", "\u2713", "checked"):
		return True
	if s in ("0", "no", "false", "\u2717", "unchecked"):
		return False
	return None


def strip_cd_suffix(val: str) -> str:
	"""ตัด suffix '- CD' ออกจากท้าย string"""
	return re.sub(r"\s*-\s*CD\s*$", "", val).strip()


def strip_tax_suffix(val: str) -> str:
	"""ตัด tax suffix เช่น '- CD/DKSH/UBIQ' และตัวเลขท้ายสุด"""
	v = re.sub(r"\s*-\s*(CD|DKSH|UBIQ)\s*$", "", val).strip()
	v = re.sub(r"\s+\d+$", "", v).strip()
	return v


def float_to_string(val: Any) -> str:
	"""แปลง float string โดยตัดท้าย '.0' ออก"""
	s = str(val).strip()
	if s.endswith(".0"):
		return s[:-2]
	return s


def compare_values(
	excel_val: Any,
	api_val: Any,
	mapping: FieldMapping,
	aliases: dict[str, dict[str, list[str]]],
) -> bool:
	"""เปรียบเทียบค่า Sheet กับ API value ตาม mapping config + alias mapping"""
	norm_ex = normalize(excel_val)
	norm_ap = normalize(api_val)

	if norm_ex == "" and norm_ap == "":
		return True

	is_account_type = mapping.alias_type == "account_type" or mapping.fuzzy_match == "account-type"
	if not is_account_type and (norm_ex == "" or norm_ap == ""):
		return norm_ex == norm_ap

	if mapping.boolean_field:
		ex_bool = to_bool(excel_val)
		ap_bool = to_bool(api_val)
		if ex_bool is not None and ap_bool is not None:
			return ex_bool == ap_bool

	if mapping.alias_type:
		alias_map = aliases.get(mapping.alias_type, {})
		alias_group = alias_map.get(norm_ex) or alias_map.get(norm_ap)
		if alias_group:
			return norm_ex in alias_group and norm_ap in alias_group

	if mapping.fuzzy_match == "account-type":
		alias_map = aliases.get("account_type", {})
		alias_group = alias_map.get(norm_ex) or alias_map.get(norm_ap)
		if alias_group:
			return norm_ex in alias_group and norm_ap in alias_group
		return norm_ex == norm_ap

	if mapping.fuzzy_match == "strip-cd":
		return strip_cd_suffix(norm_ex) == strip_cd_suffix(norm_ap)

	if mapping.fuzzy_match == "strip-tax-suffix":
		return strip_tax_suffix(norm_ex) == strip_tax_suffix(norm_ap)

	if mapping.first_name_only:
		return norm_ap.lower().startswith(norm_ex.lower())

	if mapping.ignore_case:
		return norm_ex.lower() == norm_ap.lower()

	return norm_ex == norm_ap


def get_excel_value(row: dict[str, Any], excel_cols: list[str]) -> Any:
	"""ดึงค่าจาก Sheet row ตามชื่อ column รองรับหลาย columns คืนค่าแรกที่ไม่ว่าง"""
	for col in excel_cols:
		v = row.get(col)
		if v is not None and v != "":
			return v
	return ""


def get_excel_key(row: dict[str, Any], config: SheetConfig) -> str:
	"""สร้าง lookup key จาก Sheet row ตาม config"""
	for k in config.key_excel:
		v = normalize(row.get(k))
		if not v:
			continue
		if config.key_extractor:
			v = config.key_extractor(v)
		if config.key_fuzzy_match == "float-to-string":
			v = float_to_string(v)
		if config.key_ignore_case:
			return v.lower()
		if config.key_fuzzy_match == "strip-cd":
			return strip_cd_suffix(v)
		if config.key_fuzzy_match == "strip-tax-suffix":
			return strip_tax_suffix(v)
		return v
	return ""


def get_api_key(rec: dict[str, Any], config: SheetConfig) -> str:
	"""สร้าง lookup key จาก API record ตาม config"""
	v = normalize(rec.get(config.key_api))
	if config.key_extractor:
		v = config.key_extractor(v)
	if config.key_fuzzy_match == "float-to-string":
		v = float_to_string(v)
	if config.key_ignore_case:
		return v.lower()
	if config.key_fuzzy_match == "strip-cd":
		return strip_cd_suffix(v)
	if config.key_fuzzy_match == "strip-tax-suffix":
		return strip_tax_suffix(v)
	return v


def validate_sheet(
	sheet_rows: list[dict[str, Any]],
	api_records: list[dict[str, Any]],
	config: SheetConfig,
	aliases: dict[str, dict[str, list[str]]],
) -> ValidationResult:
	"""เปรียบเทียบ Sheet rows กับ API records แล้วคืน ValidationResult"""
	result = ValidationResult(config.sheet_name, config.doctype, config.label)
	result.api_count = len(api_records)

	api_map: dict[str, dict[str, Any]] = {}
	for rec in api_records:
		key = get_api_key(rec, config)
		api_map[key] = rec
		if config.composite_key:
			ck = f"{normalize(rec.get('item_code'))}|{normalize(rec.get('price_list'))}".lower()
			api_map[ck] = rec
		if config.key_fuzzy_match == "float-to-string":
			fts = float_to_string(normalize(rec.get(config.key_api)))
			if fts:
				api_map[fts] = rec

	matched_api_keys: set[str] = set()

	for row in sheet_rows:
		if config.composite_key:
			parts = config.composite_key(row)
			excel_key = parts.lower()
			display_key = parts.replace("|", " / ")
		else:
			excel_key = get_excel_key(row, config)
			display_key = excel_key

		if not excel_key and not config.composite_key:
			if all(v is None or v == "" for v in row.values()):
				continue

		non_key_values = [v for k, v in row.items() if k not in config.key_excel]
		if all(v is None or v == "" for v in non_key_values) and not config.composite_key:
			continue

		result.excel_count += 1
		if not excel_key and not config.composite_key:
			continue

		api_rec = api_map.get(excel_key)
		if not api_rec and not config.key_ignore_case:
			for k in api_map:
				if k.lower() == excel_key.lower():
					api_rec = api_map[k]
					break

		if not api_rec:
			result.missing_in_api.append(display_key)
			result.passed = False
			continue

		matched_api_keys.add(get_api_key(api_rec, config))
		result.matched += 1

		diffs: list[FieldDiff] = []
		for field_map in config.fields:
			if field_map.skip_when and field_map.skip_when(api_rec):
				continue
			ex_val = get_excel_value(row, field_map.excel)
			ap_val = api_rec.get(field_map.api)
			if normalize(ex_val) == "":
				continue
			if not compare_values(ex_val, ap_val, field_map, aliases):
				diffs.append(FieldDiff(field_map.api, ex_val, ap_val))

		if diffs:
			result.field_mismatches.append(RecordDiff(display_key, diffs))
			result.passed = False

	excel_keys: set[str] = set()
	for row in sheet_rows:
		if config.composite_key:
			ck = config.composite_key(row).lower()
			if ck:
				excel_keys.add(ck)
		else:
			k = get_excel_key(row, config)
			if k:
				excel_keys.add(k)

	for rec in api_records:
		api_key = get_api_key(rec, config)
		found = api_key in excel_keys
		if not found and config.composite_key:
			ck = f"{normalize(rec.get('item_code'))}|{normalize(rec.get('price_list'))}".lower()
			found = ck in excel_keys
		if not found:
			if config.composite_key:
				display = f"{rec.get('item_code', '')} / {rec.get('price_list', '')}"
			else:
				display = str(rec.get("name") or rec.get(config.key_api) or api_key)
			result.extra_in_api.append(display)

	return result


def print_result(r: ValidationResult) -> None:
	"""พิมพ์ ValidationResult เดียวไปที่ console"""
	icon = "\u2705" if r.passed else "\u274c"
	print(f"\n{'=' * 65}")
	print(f"  {icon} {r.label} -> {r.doctype}")
	print(f"{'=' * 65}")
	print(f"  Sheet: {r.excel_count} records | API: {r.api_count} records")
	print(f"  Matched: {r.matched}")

	if r.missing_in_api:
		print(f"  Missing in API ({len(r.missing_in_api)}):")
		for m in r.missing_in_api[:20]:
			print(f"     - {m}")
		if len(r.missing_in_api) > 20:
			print(f"     ... and {len(r.missing_in_api) - 20} more")

	if r.extra_in_api:
		print(f"  Extra in API ({len(r.extra_in_api)}):")
		for m in r.extra_in_api[:10]:
			print(f"     - {m}")
		if len(r.extra_in_api) > 10:
			print(f"     ... and {len(r.extra_in_api) - 10} more")

	if r.field_mismatches:
		print(f"  Field Mismatches ({len(r.field_mismatches)}):")
		for rec in r.field_mismatches[:20]:
			print(f"     - {rec.key}:")
			for d in rec.diffs:
				print(f'       .{d.field}: Sheet="{d.excel_value}" -> API="{d.api_value}"')
		if len(r.field_mismatches) > 20:
			print(f"     ... and {len(r.field_mismatches) - 20} more records")


def print_summary(results: list[ValidationResult]) -> None:
	"""พิมพ์สรุปผลรวมจาก ValidationResult ทั้งหมด"""
	passed = sum(1 for r in results if r.passed)
	failed = sum(1 for r in results if not r.passed)
	total_sheet = sum(r.excel_count for r in results)
	total_api = sum(r.api_count for r in results)
	total_missing = sum(len(r.missing_in_api) for r in results)
	total_mismatches = sum(len(r.field_mismatches) for r in results)

	print(f"\n{'=' * 65}")
	print("  FINAL SUMMARY")
	print(f"{'=' * 65}")
	print(f"  Sheets checked:  {len(results)}")
	print(f"  Passed:          {passed}")
	print(f"  Failed:          {failed}")
	print(f"  Total Sheet:     {total_sheet} records")
	print(f"  Total API:       {total_api} records")
	print(f"  Missing in API:  {total_missing} records")
	print(f"  Field mismatch:  {total_mismatches} records")
	print(f"{'=' * 65}")

	if failed > 0:
		print("\n  Failed sheets:")
		for r in results:
			if not r.passed:
				print(
					f"    - {r.label} ({r.doctype}): missing={len(r.missing_in_api)}, mismatches={len(r.field_mismatches)}"
				)
	else:
		print("\n  ALL DATA VALIDATED SUCCESSFULLY!")
	print()
