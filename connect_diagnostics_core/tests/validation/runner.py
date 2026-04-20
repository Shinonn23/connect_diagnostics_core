# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Main runner for bench check-master-data — orchestrates the validation pipeline."""

from __future__ import annotations

from typing import Any

import click
import frappe

from .config import ValidationConfig
from .config_loader import SheetConfig, load_all_configs
from .reporter import create_validation_report
from .sheets_reader import load_master_data
from .validator import ValidationResult, print_result, print_summary, validate_sheet

_logger = frappe.logger(__name__)


def _get_api_records(
	doctype: str, fields: list[str], filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
	"""Fetch records from ERPNext using frappe.get_all (read-only, no SQL)."""
	filters = filters or {}
	return frappe.get_all(doctype, fields=fields, filters=filters, limit_page_length=0)


def _run_validation(config: ValidationConfig) -> list[ValidationResult]:
	"""Run validation for all configured sheets."""
	configs, aliases = load_all_configs(config.config_sheet_id, config.google_credentials_path)
	if not configs:
		_logger.warning("No sheet configs found. Check config_sheet_id in bench config.")
		return []

	sheet_data = load_master_data(config.google_sheet_id, config.google_credentials_path)
	all_results: list[ValidationResult] = []

	for sheet_config in configs:
		sheet_rows = sheet_data.get(sheet_config.sheet_name)
		if sheet_rows is None:
			_logger.warning('Sheet "%s" not found in master data', sheet_config.sheet_name)
			sheet_rows = []

		api_fields = ["name", *list({f.api for f in sheet_config.fields})]
		if sheet_config.key_api != "name" and sheet_config.key_api not in api_fields:
			api_fields.append(sheet_config.key_api)

		try:
			api_records = _get_api_records(sheet_config.doctype, api_fields, sheet_config.filters)
		except Exception as e:
			_logger.error("Error fetching %s: %s", sheet_config.doctype, e)
			api_records = []

		result = validate_sheet(sheet_rows, api_records, sheet_config, aliases)
		all_results.append(result)
		print_result(result)

	print_summary(all_results)
	return all_results


def run_validation(config: ValidationConfig) -> None:
	"""Entry point for bench check-master-data."""
	click.echo("\n" + "=" * 65)
	click.echo("  Master Data Validation")
	click.echo("=" * 65)

	results = _run_validation(config)

	failed = [r for r in results if not r.passed]
	if failed and config.google_drive_report_folder:
		click.echo("\n  Generating failure report...")
		create_validation_report(
			results,
			config.google_drive_report_folder,
			config.google_credentials_path,
		)
	elif failed:
		click.echo(
			"\n  Validation failed. Set google_drive_report_folder in bench config to generate reports."
		)
	else:
		click.echo("\n  All master data validated successfully!")
