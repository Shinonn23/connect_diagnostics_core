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
SUMMARY_WIDTH = 72
MAX_VALUE_DISPLAY_LENGTH = 96


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

	ordered_results = sorted(results, key=lambda result: result.entity_key.lower())

	total_entities = len(ordered_results)
	total_expected_rows = sum(r.total for r in ordered_results)
	total_matched = sum(r.matched for r in ordered_results)
	total_mismatches = sum(len(r.mismatches) for r in ordered_results)
	total_missing_db = sum(len(r.missing_in_db) for r in ordered_results)
	total_missing_sheet = sum(len(r.missing_in_sheet) for r in ordered_results)
	total_issues = total_mismatches + total_missing_db + total_missing_sheet
	match_rate = (
		f"{(total_matched / total_expected_rows) * 100:.1f}%"
		if total_expected_rows
		else "n/a (no expected rows)"
	)

	print(f"\n{'=' * SUMMARY_WIDTH}")
	print("Master Data Verification Summary")
	print(f"{'=' * SUMMARY_WIDTH}")
	print(f"{'Entities checked':<18}: {total_entities}")
	print(f"{'Rows expected':<18}: {total_expected_rows}")
	print(f"{'Rows matched':<18}: {total_matched}")
	print(f"{'Mismatches':<18}: {total_mismatches}")
	print(f"{'Missing in ERPNext':<18}: {total_missing_db}")
	print(f"{'Missing in Sheet':<18}: {total_missing_sheet}")
	print(f"{'Total issues':<18}: {total_issues}")
	print(f"{'Match rate':<18}: {match_rate}")
	print(f"{'-' * SUMMARY_WIDTH}")

	if total_issues == 0:
		print("Status: PASS - all entities verified successfully.")
		print(f"{'=' * SUMMARY_WIDTH}")
		return

	print("Status: FAIL - issues found.")
	print("Entity details (issues only):")

	issue_results = [
		result
		for result in ordered_results
		if result.mismatches or result.missing_in_db or result.missing_in_sheet
	]
	for idx, result in enumerate(issue_results, start=1):
		print(
			f"{idx:>2}. {result.entity_key} | matched {result.matched}/{result.total}"
			f" | mismatch {len(result.mismatches)}"
			f" | missing in ERPNext {len(result.missing_in_db)}"
			f" | missing in sheet {len(result.missing_in_sheet)}"
		)

		for mismatch in sorted(
			result.mismatches,
			key=lambda item: (item.key_value, item.field_name, item.expected, item.actual),
		):
			print(f"    MISMATCH: {mismatch.key_value}.{mismatch.field_name}")
			print(f"      expected: '{_format_value(mismatch.expected)}'")
			print(f"      actual  : '{_format_value(mismatch.actual)}'")

		for key_val in sorted(result.missing_in_db):
			print(f"    MISSING IN ERPNext: {_format_value(key_val)}")

		for key_val in sorted(result.missing_in_sheet):
			print(f"    MISSING IN SHEET: {_format_value(key_val)}")

	print(f"{'=' * SUMMARY_WIDTH}")


def _format_value(value: str) -> str:
	normalized = value.replace("\r", "\\r").replace("\n", "\\n")
	if len(normalized) <= MAX_VALUE_DISPLAY_LENGTH:
		return normalized
	return f"{normalized[: MAX_VALUE_DISPLAY_LENGTH - 3]}..."
