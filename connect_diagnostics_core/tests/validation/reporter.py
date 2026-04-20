# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Report generation — create Google Sheet reports in Drive when validation fails."""

from __future__ import annotations

from typing import Any

import click
import frappe

from .sheets_reader import create_report_sheet
from .validator import FieldDiff, RecordDiff, ValidationResult


def _build_failure_rows(results: list[ValidationResult]) -> tuple[list[str], list[list[str]]]:
	"""Convert failed ValidationResult objects into rows for a Google Sheet report."""
	headers = [
		"Sheet",
		"DocType",
		"Record Key",
		"Field",
		"Sheet Value",
		"API Value",
		"Status",
	]
	rows: list[list[str]] = []

	for r in results:
		if r.passed:
			rows.append([r.label, r.doctype, "", "", "", "", "PASS"])
			continue

		for rec_diff in r.field_mismatches:
			for diff in rec_diff.diffs:
				rows.append(
					[
						r.label,
						r.doctype,
						rec_diff.key,
						diff.field,
						str(diff.excel_value),
						str(diff.api_value),
						"FIELD_MISMATCH",
					]
				)

		for missing in r.missing_in_api:
			rows.append([r.label, r.doctype, missing, "", "", "", "MISSING_IN_API"])

		for extra in r.extra_in_api:
			rows.append([r.label, r.doctype, extra, "", "", "", "EXTRA_IN_API"])

	return headers, rows


def _build_summary_rows(results: list[ValidationResult]) -> tuple[list[str], list[list[str]]]:
	"""Build a summary tab for the report."""
	headers = [
		"Sheet",
		"DocType",
		"Sheet Records",
		"API Records",
		"Matched",
		"Missing",
		"Mismatches",
		"Status",
	]
	rows: list[list[str]] = []

	for r in results:
		status = "PASS" if r.passed else "FAIL"
		rows.append(
			[
				r.label,
				r.doctype,
				str(r.excel_count),
				str(r.api_count),
				str(r.matched),
				str(len(r.missing_in_api)),
				str(len(r.field_mismatches)),
				status,
			]
		)

	return headers, rows


def create_validation_report(
	results: list[ValidationResult],
	folder_id: str,
	credentials_path: str | None,
) -> str | None:
	"""Create a Google Sheet report in Drive if there are failures. Returns the report URL or None."""
	failed = [r for r in results if not r.passed]
	if not failed:
		return None

	timestamp = frappe.utils.now_datetime().strftime("%Y-%m-%d_%H%M%S")
	report_title = f"Validation Report {timestamp}"

	headers, rows = _build_failure_rows(results)
	url = create_report_sheet(report_title, headers, rows, folder_id, credentials_path)

	click.echo(f"\n  Report created: {url}")
	return url
