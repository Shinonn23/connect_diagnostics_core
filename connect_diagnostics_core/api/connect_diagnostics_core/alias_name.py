# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_supported_doctypes(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict | None,
) -> list:
	if not frappe.has_permission("Alias Supported DocType", "read"):
		raise frappe.PermissionError

	supported: list[str] = cast(
		list[str],
		frappe.get_all(
			"Alias Supported DocType",
			filters={"is_enabled": 1},
			pluck="reference_doctype",
		),
	)

	if not supported:
		return []

	return frappe.db.sql(
		f"""
		SELECT name FROM tabDocType
		WHERE name IN %(supported)s AND name LIKE %(txt)s
		ORDER BY name
		LIMIT {start}, {page_len}
		""",
		{"supported": tuple(supported), "txt": f"%{txt}%"},
	)


@frappe.whitelist()
def get_original_display_name(reference_doctype: str, primary_name: str) -> dict[str, str]:
	if not frappe.has_permission(reference_doctype, "read"):
		raise frappe.PermissionError

	alias_field: str = cast(
		str,
		frappe.db.get_value(
			"Alias Supported DocType",
			{"reference_doctype": reference_doctype, "is_enabled": 1},
			"alias_field",
		)
		or "",
	)

	if not alias_field:
		return {"data": ""}

	value: str = cast(
		str,
		frappe.db.get_value(reference_doctype, primary_name, alias_field) or "",
	)

	return {"data": value}


@frappe.whitelist()
def get_alias_map(reference_doctype: str) -> dict[str, dict[str, str]]:
	if not frappe.has_permission(reference_doctype, "read"):
		raise frappe.PermissionError

	alias_field: str = cast(
		str,
		frappe.db.get_value(
			"Alias Supported DocType",
			{"reference_doctype": reference_doctype, "is_enabled": 1},
			"alias_field",
		)
		or "",
	)

	if not alias_field:
		return {"data": {}}

	meta = frappe.get_meta(reference_doctype)
	if not meta.has_field(alias_field):
		return {"data": {}}

	source_rows: list[dict] = cast(
		list[dict],
		frappe.get_all(reference_doctype, fields=["name", alias_field]),
	)

	alias_rows: list[dict] = cast(
		list[dict],
		frappe.get_all(
			"Alias Name",
			filters={"documents": reference_doctype},
			fields=["primary_name", "alias_name"],
		),
	)

	alias_lookup: dict[str, str] = {
		cast(str, row["primary_name"]): cast(str, row["alias_name"]) for row in alias_rows
	}

	result: dict[str, str] = {
		cast(str, row["name"]): alias_lookup.get(
			cast(str, row["name"]),
			cast(str, row.get(alias_field) or ""),
		)
		for row in source_rows
	}

	return {"data": result}
