# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

from connect_diagnostics_core.master_data.client import write_results

if TYPE_CHECKING:
	from connect_diagnostics_core.master_data.comparator import ComparisonResult

RESULTS_SHEET = "Verify Results"
RESULTS_HEADER = ["Entity", "Key", "Field", "Expected", "Actual", "Issue Type"]


def report_results(
	spreadsheet_id: str,
	results: list[ComparisonResult],
) -> int:
	total_issues = 0
	rows: list[list[str]] = [RESULTS_HEADER]

	for result in results:
		for m in result.mismatches:
			rows.append([m.entity_key, m.key_value, m.field_name, m.expected, m.actual, "Mismatch"])
			total_issues += 1

		for key_val in result.missing_in_db:
			rows.append([result.entity_key, key_val, "", "", "", "Missing in ERPNext"])
			total_issues += 1

		for key_val in result.missing_in_sheet:
			rows.append([result.entity_key, key_val, "", "", "", "Missing in Sheet"])
			total_issues += 1

	if total_issues > 0:
		write_results(spreadsheet_id, f"{RESULTS_SHEET}!A1", rows)

	return total_issues


def print_summary(results: list[ComparisonResult]) -> None:
	if not results:
		print("No entities verified.")
		return

	total_entities = len(results)
	total_matched = sum(r.matched for r in results)
	total_mismatches = sum(len(r.mismatches) for r in results)
	total_missing_db = sum(len(r.missing_in_db) for r in results)
	total_missing_sheet = sum(len(r.missing_in_sheet) for r in results)

	print(f"\n{'=' * 60}")
	print("Master Data Verification Summary")
	print(f"{'=' * 60}")
	print(f"Entities checked: {total_entities}")
	print(f"Records matched:  {total_matched}")
	print(f"Mismatches:       {total_mismatches}")
	print(f"Missing in DB:    {total_missing_db}")
	print(f"Missing in Sheet: {total_missing_sheet}")
	print(f"{'=' * 60}")

	if total_mismatches == 0 and total_missing_db == 0 and total_missing_sheet == 0:
		print("All entities verified successfully.")
	else:
		for result in results:
			if result.mismatches or result.missing_in_db or result.missing_in_sheet:
				print(f"\n  [{result.entity_key}] {result.matched}/{result.total} matched")
				for m in result.mismatches:
					print(
						f"    MISMATCH: {m.key_value}.{m.field_name}: expected='{m.expected}', actual='{m.actual}'"
					)
				for key_val in result.missing_in_db:
					print(f"    MISSING IN DB: {key_val}")
				for key_val in result.missing_in_sheet:
					print(f"    MISSING IN SHEET: {key_val}")
