# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import frappe

from connect_diagnostics_core.master_data.client import write_results

if TYPE_CHECKING:
	from connect_diagnostics_core.master_data.comparator import ComparisonResult

BANGKOK_TZ = timezone(timedelta(hours=7))
RESULTS_HEADER = ["Entity", "Key", "Field", "Expected", "Actual", "Issue Type"]


def _report_tab_name() -> str:
	ts = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d %H:%M UTC+7")
	return f"Verify Results {ts}"


def report_results(
	spreadsheet_id: str,
	results: list[ComparisonResult],
) -> tuple[int, str]:
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

	report_id = _get_report_spreadsheet_id()
	if total_issues > 0:
		tab_name = _report_tab_name()
		write_results(report_id, f"'{tab_name}'!A1", rows, tab_title=tab_name)

	return total_issues, report_id


def _get_report_spreadsheet_id() -> str:
	report_id: str = frappe.conf.get("google_report_sheet_id") or ""
	if not report_id:
		msg = "google_report_sheet_id is not configured. Set via: bench --site <site> set-config google_report_sheet_id '<spreadsheet_id>'"
		raise frappe.ValidationError(msg)
	return report_id


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
