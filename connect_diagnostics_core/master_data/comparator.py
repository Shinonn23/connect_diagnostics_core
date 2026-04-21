# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import cast

import frappe

from connect_diagnostics_core.master_data.mapper import EntityMapping


def _values_match(expected: str, actual: str) -> bool:
	if expected == actual:
		return True
	expected = html.unescape(expected)
	actual = html.unescape(actual)
	if expected == actual:
		return True
	try:
		return float(expected) == float(actual)
	except (ValueError, TypeError):
		return False


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
	sheet_keys: set[str] = field(default_factory=set)


def compare_entity(
	entity_key: str,
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> ComparisonResult:
	if mapping.child_doctype:
		return _compare_child_entity(entity_key, mapping, expected_rows)
	return _compare_flat_entity(entity_key, mapping, expected_rows)


def _compare_flat_entity(
	entity_key: str,
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> ComparisonResult:
	fields_to_fetch = _get_comparison_fields(mapping, expected_rows)
	actual_data = _fetch_actual_data(mapping.doctype, fields_to_fetch, mapping.key_field)

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
			if not _values_match(expected_val, actual_val):
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

	result.sheet_keys = {row.get(mapping.key_field, "") for row in expected_rows}

	return result


def _compare_child_entity(
	entity_key: str,
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> ComparisonResult:
	child_fields = list(mapping.child_fields)
	if not child_fields:
		return ComparisonResult(entity_key=entity_key, total=len(expected_rows), matched=0)

	assert mapping.child_doctype is not None
	actual_groups = _fetch_child_data(mapping.child_doctype, child_fields)
	expected_groups = _group_rows(expected_rows, mapping.key_field)

	result = ComparisonResult(entity_key=entity_key, total=len(expected_rows), matched=0)

	for parent_key, expected_children in expected_groups.items():
		actual_children = actual_groups.get(parent_key)
		if actual_children is None:
			result.missing_in_db.append(parent_key)
			continue

		unmatched_actual = list(actual_children)

		for expected_child in expected_children:
			child_id = _describe_child(expected_child, mapping.key_field)
			match, match_idx = _find_best_match(expected_child, unmatched_actual, mapping.key_field)

			if match is None:
				for field_name, expected_val in expected_child.items():
					if field_name == mapping.key_field:
						continue
					result.mismatches.append(
						Mismatch(
							entity_key=entity_key,
							key_value=f"{parent_key} / {child_id}",
							field_name=field_name,
							expected=expected_val,
							actual="",
						)
					)
			else:
				row_matched = True
				for field_name, expected_val in expected_child.items():
					if field_name == mapping.key_field:
						continue
					actual_val = str(match.get(field_name) or "").strip()
					if not _values_match(expected_val, actual_val):
						result.mismatches.append(
							Mismatch(
								entity_key=entity_key,
								key_value=f"{parent_key} / {child_id}",
								field_name=field_name,
								expected=expected_val,
								actual=actual_val,
							)
						)
						row_matched = False

				if row_matched:
					result.matched += 1
				assert match_idx is not None
				unmatched_actual.pop(match_idx)

	result.sheet_keys = set(expected_groups.keys())

	return result


def _get_comparison_fields(
	mapping: EntityMapping,
	expected_rows: list[dict[str, str]],
) -> list[str]:
	if not expected_rows:
		return [mapping.key_field]
	seen: set[str] = set()
	fields: list[str] = []
	for row in expected_rows:
		for key in row:
			if key not in seen:
				seen.add(key)
				fields.append(key)
	return fields


def _fetch_actual_data(
	doctype: str,
	fields: list[str],
	key_field: str,
) -> dict[str, dict[str, str]]:
	if key_field not in fields:
		fields = [key_field, *fields]

	rows = frappe.get_all(doctype, fields=fields, as_list=False)
	data: dict[str, dict[str, str]] = {}
	for row in rows:
		key_val: str = cast(str, row.get(key_field, ""))
		if key_val:
			data[key_val] = {k: str(v or "") for k, v in row.items()}
	return data


def _fetch_child_data(
	child_doctype: str,
	child_fields: list[str],
) -> dict[str, list[dict[str, str]]]:
	fields = ["parent", *child_fields]
	rows = frappe.get_all(child_doctype, fields=fields, as_list=False)
	groups: dict[str, list[dict[str, str]]] = {}
	for row in rows:
		parent_val: str = cast(str, row.get("parent", ""))
		if parent_val:
			groups.setdefault(parent_val, []).append({k: str(v or "") for k, v in row.items()})
	return groups


def _group_rows(
	rows: list[dict[str, str]],
	key_field: str,
) -> dict[str, list[dict[str, str]]]:
	groups: dict[str, list[dict[str, str]]] = {}
	for row in rows:
		key_val = row.get(key_field, "")
		if key_val:
			groups.setdefault(key_val, []).append(row)
	return groups


def _find_best_match(
	expected: dict[str, str],
	actual_list: list[dict[str, str]],
	key_field: str,
) -> tuple[dict[str, str] | None, int | None]:
	best_match: dict[str, str] | None = None
	best_idx: int | None = None
	best_score = -1

	for i, actual in enumerate(actual_list):
		score = sum(
			1
			for fld, val in expected.items()
			if fld != key_field and _values_match(val, str(actual.get(fld) or "").strip())
		)
		if score > best_score:
			best_score = score
			best_match = actual
			best_idx = i

	if best_score <= 0:
		return None, None

	return best_match, best_idx


def _describe_child(row: dict[str, str], key_field: str) -> str:
	for fld, value in row.items():
		if fld != key_field:
			return value
	return ""
