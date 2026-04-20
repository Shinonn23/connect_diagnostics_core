# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import click
import frappe

from connect_diagnostics_core.master_data.client import get_sheet_data
from connect_diagnostics_core.master_data.comparator import compare_entity
from connect_diagnostics_core.master_data.mapper import EntityMapping, map_rows, parse_mappings
from connect_diagnostics_core.master_data.reporter import RESULTS_SHEET, print_summary, report_results

MAPPING_TAB = "Mapping"


@click.command("verify-master-data")
@click.option(
	"--spreadsheet-id",
	required=True,
	help="Google Sheets spreadsheet ID.",
)
@click.option(
	"--entity",
	default=None,
	help="Verify a single entity (e.g., 'uom'). All entities if omitted.",
)
def verify_master_data(spreadsheet_id: str, entity: str | None) -> None:
	"""Verify master data in ERPNext against Google Sheets."""

	with frappe.init_site():
		frappe.connect()
		_run_verify(spreadsheet_id, entity)
		frappe.destroy()


def _run_verify(spreadsheet_id: str, entity: str | None) -> None:
	all_mappings = parse_mappings(spreadsheet_id, MAPPING_TAB)
	entities = _filter_entities(all_mappings, entity)
	results = []

	for entity_key, mapping in entities.items():
		try:
			raw_data = get_sheet_data(spreadsheet_id, entity_key)
			expected_rows = map_rows(raw_data, mapping.column_map, mapping.key_field)
			result = compare_entity(entity_key, mapping, expected_rows)
			results.append(result)
		except Exception:
			frappe.log_error(f"Master Data Verify Error: {entity_key}")

	print_summary(results)
	total_issues = report_results(spreadsheet_id, results)

	if total_issues > 0:
		click.echo(f"\n{total_issues} issues written to '{RESULTS_SHEET}' sheet.")
	else:
		click.echo("\nNo issues found.")


def _filter_entities(
	all_mappings: dict[str, EntityMapping],
	entity: str | None,
) -> dict[str, EntityMapping]:
	if entity:
		if entity not in all_mappings:
			available = ", ".join(sorted(all_mappings.keys()))
			click.echo(f"Unknown entity '{entity}'. Available: {available}")
			raise SystemExit(1)
		return {entity: all_mappings[entity]}

	return dict(all_mappings)
