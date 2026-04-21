# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import click
import frappe
from frappe.commands import get_site, pass_context

from connect_diagnostics_core.master_data.client import get_sheet_data
from connect_diagnostics_core.master_data.comparator import ComparisonResult, compare_entity
from connect_diagnostics_core.master_data.mapper import EntityMapping, map_rows, parse_mappings
from connect_diagnostics_core.master_data.reporter import print_summary, report_results

MAPPING_TAB = "Mapping"


@click.command("verify-master-data")
@click.option(
	"--spreadsheet-id",
	default=None,
	help="Google Sheets spreadsheet ID. Falls back to google_sheet_id in site config.",
)
@click.option(
	"--entity",
	default=None,
	help="Verify a single entity (e.g., 'uom'). All entities if omitted.",
)
@click.option(
	"--ignore-missing-in-sheet",
	is_flag=True,
	default=False,
	help="Skip reporting records that exist in DB but not in sheet.",
)
@pass_context
def verify_master_data(
	context: object, spreadsheet_id: str | None, entity: str | None, ignore_missing_in_sheet: bool
) -> None:
	"""Verify master data in ERPNext against Google Sheets."""

	site = get_site(context)
	with frappe.init_site(site):
		frappe.connect()
		resolved_id = spreadsheet_id or frappe.conf.get("google_sheet_id")
		if not resolved_id:
			click.echo(
				"spreadsheet-id is required. Pass --spreadsheet-id or set google_sheet_id in site config."
			)
			raise SystemExit(1)
		_run_verify(resolved_id, entity, ignore_missing_in_sheet)
		frappe.destroy()


def _run_verify(spreadsheet_id: str, entity: str | None, ignore_missing_in_sheet: bool) -> None:
	all_mappings = parse_mappings(spreadsheet_id, MAPPING_TAB)
	entities = _filter_entities(all_mappings, entity)
	results: list[ComparisonResult] = []

	doctype_sheet_keys: dict[str, set[str]] = {}
	doctype_key_field: dict[str, str] = {}

	sheet_groups: dict[str, list[tuple[str, EntityMapping]]] = {}
	for entity_key, mapping in entities.items():
		sheet_groups.setdefault(mapping.sheet_name, []).append((entity_key, mapping))

	for sheet_name, entity_list in sheet_groups.items():
		try:
			raw_data = get_sheet_data(spreadsheet_id, sheet_name)
		except Exception:
			for entity_key, _ in entity_list:
				frappe.log_error(f"Master Data Verify Error: {entity_key}")
			continue

		for entity_key, mapping in entity_list:
			try:
				expected_rows = map_rows(raw_data, mapping.column_map, mapping.key_field)
				result = compare_entity(entity_key, mapping, expected_rows)
				results.append(result)

				doctype_sheet_keys.setdefault(mapping.doctype, set()).update(result.sheet_keys)
				doctype_key_field[mapping.doctype] = mapping.key_field
			except Exception:
				frappe.log_error(f"Master Data Verify Error: {entity_key}")

	if not ignore_missing_in_sheet:
		results.extend(_compute_missing_in_sheet(doctype_sheet_keys, doctype_key_field))

	print_summary(results)
	total_issues, report_spreadsheet_id = report_results(spreadsheet_id, results)

	if total_issues > 0:
		url = f"https://docs.google.com/spreadsheets/d/{report_spreadsheet_id}"
		click.echo(f"\n{total_issues} issues written to 'report tab: {url}")
	else:
		click.echo("\nNo issues found.")


def _filter_entities(
	all_mappings: dict[str, EntityMapping],
	entity: str | None,
) -> dict[str, EntityMapping]:
	if entity:
		matching = {k: v for k, v in all_mappings.items() if k == entity or v.sheet_name == entity}
		if not matching:
			available = ", ".join(sorted(all_mappings.keys()))
			click.echo(f"Unknown entity '{entity}'. Available: {available}")
			raise SystemExit(1)
		return matching

	return dict(all_mappings)


def _compute_missing_in_sheet(
	doctype_sheet_keys: dict[str, set[str]],
	doctype_key_field: dict[str, str],
) -> list[ComparisonResult]:
	results: list[ComparisonResult] = []
	for doctype, sheet_keys in doctype_sheet_keys.items():
		key_field = doctype_key_field[doctype]
		db_rows = frappe.get_all(doctype, fields=[key_field], as_list=False)
		db_keys = {str(r[key_field]) for r in db_rows if r.get(key_field)}
		missing = db_keys - sheet_keys
		if missing:
			results.append(
				ComparisonResult(
					entity_key=doctype,
					total=0,
					matched=0,
					missing_in_sheet=sorted(missing),
				)
			)
	return results
