# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import frappe

from connect_diagnostics_core.master_data.mapper import EntityMapping


@dataclass
class Mismatch:
	entity_key: str
	key_value: str
	field_name: str
	expected: str
	actual: str


@dataclass
class ComparisonResult:
	entity_key: str
	total: int
	matched: int
	mismatches: list[Mismatch] = field(default_factory=list)
	missing_in_db: list[str] = field(default_factory=list)
	missing_in_sheet: list[str] = field(default_factory=list)


def compare_entity(
	entity_key: str,
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> ComparisonResult:
	fields_to_fetch = _get_comparison_fields(mapping, expected_rows)
	actual_data = _fetch_actual_data(mapping, fields_to_fetch)

	result = ComparisonResult(entity_key=entity_key, total=len(expected_rows), matched=0)

	for expected in expected_rows:
		key_value = expected.get(mapping.key_field, "")
		if not key_value:
			continue

		actual = actual_data.get(key_value)
		if actual is None:
			result.missing_in_db.append(key_value)
			continue

		row_matched = True
		for sheet_field, expected_val in expected.items():
			if sheet_field == mapping.key_field:
				continue
			actual_val = str(actual.get(sheet_field) or "").strip()
			if actual_val != expected_val:
				result.mismatches.append(
					Mismatch(
						entity_key=entity_key,
						key_value=key_value,
						field_name=sheet_field,
						expected=expected_val,
						actual=actual_val,
					)
				)
				row_matched = False

		if row_matched:
			result.matched += 1

	sheet_keys = {row.get(mapping.key_field, "") for row in expected_rows}
	for db_key in actual_data:
		if db_key not in sheet_keys:
			result.missing_in_sheet.append(db_key)

	return result


def _get_comparison_fields(
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> list[str]:
	if not expected_rows:
		return [mapping.key_field]
	return list(expected_rows[0].keys())


def _fetch_actual_data(
	mapping: EntityMapping,
	fields: list[str],
) -> dict[str, dict[str, str]]:
	if mapping.key_field not in fields:
		fields = [mapping.key_field, *fields]

	rows = frappe.get_all(mapping.doctype, fields=fields, as_list=False)
	data: dict[str, dict[str, str]] = {}
	for row in rows:
		key_val: str = cast(str, row.get(mapping.key_field, ""))
		if key_val:
			data[key_val] = {k: str(v or "") for k, v in row.items()}
	return data
