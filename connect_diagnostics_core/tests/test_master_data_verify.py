# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.exceptions import ValidationError
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.master_data.comparator import ComparisonResult, Mismatch, compare_entity
from connect_diagnostics_core.master_data.mapper import (
	EntityMapping,
	map_rows,
	parse_mappings,
)
from connect_diagnostics_core.master_data.reporter import print_summary, report_results


def _make_uom_mapping() -> EntityMapping:
	return EntityMapping(
		entity_key="Uom",
		doctype="UOM",
		key_field="uom_name",
		column_map={"UOM Name": "uom_name", "Must Be Whole Number": "must_be_whole_number"},
	)


class TestParseMappings(FrappeTestCase):
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_builds_entities(self, mock_get_sheet: MagicMock) -> None:
		mock_get_sheet.return_value = [
			["entity", "sheet_column", "erpnext_field", "doctype", "is_key"],
			["Uom", "UOM Name", "uom_name", "UOM", "yes"],
			["Uom", "Whole Number", "must_be_whole_number", "", "no"],
			["Brand", "Brand Name", "brand", "Brand", "yes"],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(len(result), 2)
		self.assertEqual(result["Uom"].doctype, "UOM")
		self.assertEqual(result["Uom"].key_field, "uom_name")
		self.assertEqual(
			result["Uom"].column_map, {"UOM Name": "uom_name", "Whole Number": "must_be_whole_number"}
		)
		self.assertEqual(result["Brand"].doctype, "Brand")
		self.assertEqual(result["Brand"].key_field, "brand")

	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_throws_on_empty(self, mock_get_sheet: MagicMock) -> None:
		mock_get_sheet.return_value = []
		with self.assertRaises(ValidationError):
			parse_mappings("fake-id", "Mapping")


class TestMapper(FrappeTestCase):
	def test_map_rows_produces_correct_dicts(self) -> None:
		mapping = {"UOM Name": "uom_name", "Must Be Whole Number": "must_be_whole_number"}
		raw_data = [
			["UOM Name", "UOM Abbreviation", "Must Be Whole Number"],
			["Kilogram", "kg", "Yes"],
			["Meter", "m", "No"],
		]

		result = map_rows(raw_data, mapping, "uom_name")

		self.assertEqual(len(result), 2)
		self.assertEqual(result[0], {"uom_name": "Kilogram", "must_be_whole_number": "Yes"})
		self.assertEqual(result[1], {"uom_name": "Meter", "must_be_whole_number": "No"})

	def test_map_rows_skips_empty_key(self) -> None:
		mapping = {"Name": "name"}
		raw_data = [["Name"], ["Valid"], [""]]

		result = map_rows(raw_data, mapping, "name")

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["name"], "Valid")

	def test_map_rows_empty_data(self) -> None:
		result = map_rows([], {"col": "field"}, "field")
		self.assertEqual(result, [])


class TestComparator(FrappeTestCase):
	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_match(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"Kilogram": {"uom_name": "Kilogram", "must_be_whole_number": "No"},
		}
		expected = [{"uom_name": "Kilogram", "must_be_whole_number": "No"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.matched, 1)
		self.assertEqual(len(result.mismatches), 0)

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_mismatch(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"Kilogram": {"uom_name": "Kilogram", "must_be_whole_number": "No"},
		}
		expected = [{"uom_name": "Kilogram", "must_be_whole_number": "Yes"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.matched, 0)
		self.assertEqual(len(result.mismatches), 1)
		self.assertEqual(result.mismatches[0].expected, "Yes")
		self.assertEqual(result.mismatches[0].actual, "No")

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_missing_in_db(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {}
		expected = [{"uom_name": "Kilogram", "must_be_whole_number": "No"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.missing_in_db, ["Kilogram"])

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_missing_in_sheet(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"Kilogram": {"uom_name": "Kilogram"},
			"Gram": {"uom_name": "Gram"},
		}
		expected = [{"uom_name": "Kilogram"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.missing_in_sheet, ["Gram"])


class TestReporter(FrappeTestCase):
	@patch("connect_diagnostics_core.master_data.reporter.write_results")
	def test_report_results_writes_when_mismatches(self, mock_write: MagicMock) -> None:
		results = [
			ComparisonResult(
				entity_key="Uom",
				total=2,
				matched=1,
				mismatches=[
					Mismatch(
						entity_key="Uom",
						key_value="Kilogram",
						field_name="must_be_whole_number",
						expected="Yes",
						actual="No",
					)
				],
				missing_in_db=[],
				missing_in_sheet=[],
			)
		]

		total_issues = report_results("fake-id", results)

		self.assertEqual(total_issues, 1)
		mock_write.assert_called_once()

	@patch("connect_diagnostics_core.master_data.reporter.write_results")
	def test_report_results_no_write_when_all_match(self, mock_write: MagicMock) -> None:
		results = [
			ComparisonResult(entity_key="Uom", total=3, matched=3),
		]

		total_issues = report_results("fake-id", results)

		self.assertEqual(total_issues, 0)
		mock_write.assert_not_called()
