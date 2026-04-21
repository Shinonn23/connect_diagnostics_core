# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field

import frappe

from connect_diagnostics_core.master_data.client import get_sheet_data

SYSTEM_FIELD_ALIASES: dict[str, str] = {
	"id": "name",
	"name": "name",
	"parent": "parent",
}


def _build_label_map(doctype: str) -> dict[str, str]:
	meta = frappe.get_meta(doctype)
	label_map: dict[str, str] = dict(SYSTEM_FIELD_ALIASES)
	for df in meta.fields:
		if df.fieldname:
			label_map[df.fieldname] = df.fieldname
			if df.label:
				label_map[df.label] = df.fieldname
	return label_map


def _resolve_field(value: str, label_map: dict[str, str], entity_key: str, doctype: str = "") -> str:
	if value in label_map:
		return label_map[value]
	available = sorted(v for v in label_map if v not in SYSTEM_FIELD_ALIASES or v == label_map[v])
	frappe.throw(
		f"Unknown field '{value}' for entity '{entity_key}'"
		f"{f' (DocType: {doctype})' if doctype else ''}."
		f" Available fields: {', '.join(available) if available else 'none — check DocType name'}"
	)
	raise AssertionError("unreachable")  # frappe.throw doesn't satisfy type checkers


def _col_index(header: list[str], name: str) -> int:
	try:
		return header.index(name)
	except ValueError:
		frappe.throw(f"Mapping sheet must have a '{name}' column")
		raise AssertionError("unreachable")  # frappe.throw doesn't satisfy type checkers


def _optional_col_index(header: list[str], name: str) -> int | None:
	try:
		return header.index(name)
	except ValueError:
		return None


@dataclass
class EntityMapping:
	entity_key: str
	doctype: str
	key_field: str
	column_map: dict[str, str] = field(default_factory=dict)
	child_doctype: str | None = None
	child_fields: set[str] = field(default_factory=set)
	sheet_name: str = ""


@dataclass
class _RawEntity:
	sheet_name: str = ""
	doctype: str = ""
	key_field: str = ""
	key_sheet_column: str = ""
	key_is_child: bool = False
	child_doctype: str = ""
	column_map_raw: dict[str, str] = field(default_factory=dict)
	child_columns: set[str] = field(default_factory=set)


def parse_mappings(spreadsheet_id: str, mapping_sheet: str) -> dict[str, EntityMapping]:
	raw = get_sheet_data(spreadsheet_id, mapping_sheet)
	if not raw:
		frappe.throw(f"Mapping sheet '{mapping_sheet}' is empty or not found")

	header = [h.strip().lower().replace(" ", "_") for h in raw[0]]
	sheet_name_col = _col_index(header, "sheet_name")
	sheet_col = _col_index(header, "sheet_column")
	erpnext_col = _col_index(header, "erpnext_field")
	doctype_col = _col_index(header, "doctype")
	is_key_col = _col_index(header, "is_key")
	parent_doctype_col = _optional_col_index(header, "parent_doctype")

	has_parent_doctype = parent_doctype_col is not None

	last_doctype_per_sheet: dict[str, str] = {}
	last_child_doctype_per_parent: dict[tuple[str, str], str] = {}
	entities_raw: dict[tuple[str, str, str], _RawEntity] = {}

	for row in raw[1:]:
		col_indices = [sheet_name_col, sheet_col, erpnext_col, doctype_col, is_key_col]
		if has_parent_doctype and parent_doctype_col is not None:
			col_indices.append(parent_doctype_col)
		if len(row) <= max(col_indices):
			continue

		sheet_name = row[sheet_name_col].strip()
		if not sheet_name:
			continue

		sheet_column = row[sheet_col].strip()
		erpnext_field = row[erpnext_col].strip()
		doctype_val = row[doctype_col].strip()
		is_key = row[is_key_col].strip().lower() in ("yes", "true", "1")
		parent_doctype_val = (
			row[parent_doctype_col].strip()
			if parent_doctype_col is not None and len(row) > parent_doctype_col
			else ""
		)

		if parent_doctype_val:
			group_doctype = parent_doctype_val
			parent_key = (sheet_name, group_doctype)
			if not doctype_val:
				doctype_val = last_child_doctype_per_parent.get(parent_key, "")
			if not doctype_val:
				frappe.throw(
					f"Entity '{sheet_name}' has a child mapping row for parent doctype"
					f" '{group_doctype}' without child doctype."
				)
			last_child_doctype_per_parent[parent_key] = doctype_val
			group_child_doctype = doctype_val
		else:
			if not doctype_val:
				doctype_val = last_doctype_per_sheet.get(sheet_name, "")
			if not doctype_val:
				continue
			group_doctype = doctype_val
			last_doctype_per_sheet[sheet_name] = doctype_val
			group_child_doctype = ""

		raw_key = (sheet_name, group_doctype, group_child_doctype)

		if raw_key not in entities_raw:
			entities_raw[raw_key] = _RawEntity(
				sheet_name=sheet_name,
				doctype=group_doctype,
				child_doctype=group_child_doctype,
			)

		ent = entities_raw[raw_key]

		if parent_doctype_val:
			ent.child_columns.add(sheet_column)

		if is_key and sheet_column:
			ent.key_field = "parent" if parent_doctype_val else "name"
			ent.key_sheet_column = sheet_column
			ent.key_is_child = bool(parent_doctype_val)

		if sheet_column and erpnext_field and not is_key:
			ent.column_map_raw[sheet_column] = erpnext_field

	for (sheet_name, doctype, _child_doctype), raw_ent in entities_raw.items():
		if raw_ent.key_field:
			continue
		parent_ent = entities_raw.get((sheet_name, doctype, ""))
		if parent_ent and parent_ent.key_field:
			raw_ent.key_field = parent_ent.key_field
			raw_ent.key_sheet_column = parent_ent.key_sheet_column
			raw_ent.key_is_child = parent_ent.key_is_child

	included_entities: list[_RawEntity] = []
	sheet_name_counts: dict[str, int] = {}
	parent_groups = {(sheet_name, doctype) for sheet_name, doctype, _ in entities_raw}
	for sheet_name, doctype in sorted(parent_groups, key=lambda item: (item[0].lower(), item[1].lower())):
		parent_ent = entities_raw.get((sheet_name, doctype, ""))
		child_ents = sorted(
			[
				raw_ent
				for (entity_sheet_name, entity_doctype, child_doctype), raw_ent in entities_raw.items()
				if entity_sheet_name == sheet_name and entity_doctype == doctype and child_doctype
			],
			key=lambda item: item.child_doctype.lower(),
		)

		if parent_ent and (parent_ent.column_map_raw or not child_ents):
			included_entities.append(parent_ent)
			sheet_name_counts[sheet_name] = sheet_name_counts.get(sheet_name, 0) + 1

		for child_ent in child_ents:
			included_entities.append(child_ent)
			sheet_name_counts[sheet_name] = sheet_name_counts.get(sheet_name, 0) + 1

	entities: dict[str, EntityMapping] = {}
	for raw_ent in included_entities:
		sheet_name = raw_ent.sheet_name
		doctype = raw_ent.doctype
		if not raw_ent.doctype:
			frappe.throw(f"Entity '{sheet_name}' is missing doctype in mapping")
		if not raw_ent.key_field:
			frappe.throw(
				f"Entity '{sheet_name}' (DocType: {doctype}) has no field marked as is_key in mapping"
			)

		parent_label_map = _build_label_map(raw_ent.doctype)

		if raw_ent.child_doctype:
			child_label_map = _build_label_map(raw_ent.child_doctype)
		else:
			child_label_map = parent_label_map

		resolved_map: dict[str, str] = {}
		child_fields: set[str] = set()

		if raw_ent.key_sheet_column:
			resolved_map[raw_ent.key_sheet_column] = raw_ent.key_field

		for col, raw_field in raw_ent.column_map_raw.items():
			if col in raw_ent.child_columns:
				label_map = child_label_map
				resolved_doctype = raw_ent.child_doctype
			else:
				label_map = parent_label_map
				resolved_doctype = raw_ent.doctype
			resolved = _resolve_field(raw_field, label_map, sheet_name, resolved_doctype)
			resolved_map[col] = resolved
			if col in raw_ent.child_columns:
				child_fields.add(resolved)

		entity_key = _build_entity_key(raw_ent, sheet_name_counts.get(sheet_name, 1))

		entities[entity_key] = EntityMapping(
			entity_key=entity_key,
			doctype=raw_ent.doctype,
			key_field=raw_ent.key_field,
			column_map=resolved_map,
			child_doctype=raw_ent.child_doctype or None,
			child_fields=child_fields,
			sheet_name=sheet_name,
		)

	return entities


def _build_entity_key(raw_ent: _RawEntity, mappings_in_sheet: int) -> str:
	if mappings_in_sheet <= 1:
		return raw_ent.sheet_name
	if raw_ent.child_doctype:
		return f"{raw_ent.sheet_name}:{raw_ent.doctype}:{raw_ent.child_doctype}"
	return f"{raw_ent.sheet_name}:{raw_ent.doctype}"


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
