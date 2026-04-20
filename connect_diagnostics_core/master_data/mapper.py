# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field

import frappe

from connect_diagnostics_core.master_data.client import get_sheet_data


@dataclass
class EntityMapping:
	entity_key: str
	doctype: str
	key_field: str
	column_map: dict[str, str] = field(default_factory=dict)


def parse_mappings(spreadsheet_id: str, mapping_sheet: str) -> dict[str, EntityMapping]:
	raw = get_sheet_data(spreadsheet_id, mapping_sheet)
	if not raw:
		frappe.throw(f"Mapping sheet '{mapping_sheet}' is empty or not found")

	header = [h.strip().lower() for h in raw[0]]
	entity_col = _col_index(header, "entity")
	sheet_col = _col_index(header, "sheet_column")
	erpnext_col = _col_index(header, "erpnext_field")
	doctype_col = _col_index(header, "doctype")
	is_key_col = _col_index(header, "is_key")

	entities: dict[str, EntityMapping] = {}
	for row in raw[1:]:
		max_idx = max(entity_col, sheet_col, erpnext_col, doctype_col, is_key_col)
		if len(row) <= max_idx:
			continue

		entity_key = row[entity_col].strip()
		if not entity_key:
			continue

		sheet_column = row[sheet_col].strip()
		erpnext_field = row[erpnext_col].strip()
		doctype_val = row[doctype_col].strip()
		is_key = row[is_key_col].strip().lower() in ("yes", "true", "1")

		if entity_key not in entities:
			entities[entity_key] = EntityMapping(
				entity_key=entity_key,
				doctype=doctype_val,
				key_field="",
			)

		if is_key and erpnext_field:
			entities[entity_key].key_field = erpnext_field
			if doctype_val and not entities[entity_key].doctype:
				entities[entity_key].doctype = doctype_val

		if sheet_column and erpnext_field:
			entities[entity_key].column_map[sheet_column] = erpnext_field

	for key, em in entities.items():
		if not em.doctype:
			frappe.throw(f"Entity '{key}' is missing doctype in mapping")
		if not em.key_field:
			frappe.throw(f"Entity '{key}' has no field marked as is_key in mapping")

	return entities


def map_rows(
	raw_data: list[list[str]],
	column_map: dict[str, str],
	key_field: str,
) -> list[dict[str, str]]:
	if not raw_data:
		return []

	header = [h.strip() for h in raw_data[0]]
	mapped: list[dict[str, str]] = []

	for row in raw_data[1:]:
		row_dict: dict[str, str] = {}
		for i, col_name in enumerate(header):
			if col_name in column_map and i < len(row):
				field_name = column_map[col_name]
				row_dict[field_name] = row[i].strip()

		key_value = row_dict.get(key_field, "")
		if key_value:
			mapped.append(row_dict)

	return mapped


def _col_index(header: list[str], name: str):
	try:
		return header.index(name)
	except ValueError:
		frappe.throw(f"Mapping sheet must have a '{name}' column")
