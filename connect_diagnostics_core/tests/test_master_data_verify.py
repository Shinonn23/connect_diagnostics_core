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
		key_field="name",
		column_map={"UOM Name": "name", "Must Be Whole Number": "must_be_whole_number"},
		sheet_name="Uom",
	)


def _make_bundle_mapping() -> EntityMapping:
	return EntityMapping(
		entity_key="Product Bundle",
		doctype="Product Bundle",
		key_field="name",
		column_map={
			"Parent Item Code": "name",
			"Item": "item_code",
			"Qty": "qty",
		},
		child_doctype="Product Bundle Item",
		child_fields={"item_code", "qty"},
		sheet_name="Product Bundle",
	)


def _fake_label_map(doctype: str) -> dict[str, str]:
	maps: dict[str, dict[str, str]] = {
		"UOM": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"uom_name": "uom_name",
			"UOM Name": "uom_name",
			"must_be_whole_number": "must_be_whole_number",
			"Must Be Whole Number": "must_be_whole_number",
		},
		"Brand": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"brand": "brand",
			"Brand Name": "brand",
		},
		"Item": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"item_code": "item_code",
			"Item Code": "item_code",
			"item_name": "item_name",
			"Item Name": "item_name",
		},
		"Product Bundle": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"new_item_code": "new_item_code",
			"New Item Code": "new_item_code",
		},
		"Product Bundle Item": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"item_code": "item_code",
			"Item Code": "item_code",
			"Item": "item_code",
			"qty": "qty",
			"Qty": "qty",
		},
		"Company": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"abbr": "abbr",
			"Abbr": "abbr",
			"tax_id": "tax_id",
			"Tax ID": "tax_id",
		},
		"Address": {
			"id": "name",
			"name": "name",
			"parent": "parent",
			"address_title": "address_title",
			"Address Title": "address_title",
			"address_line1": "address_line1",
			"Address Line 1": "address_line1",
		},
	}
	return maps.get(doctype, {})


class TestParseMappings(FrappeTestCase):
	@patch("connect_diagnostics_core.master_data.mapper._build_label_map", side_effect=_fake_label_map)
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_builds_entities(
		self, mock_get_sheet: MagicMock, mock_label_map: MagicMock
	) -> None:
		mock_get_sheet.return_value = [
			["sheet_name", "sheet_column", "erpnext_field", "doctype", "is_key"],
			["Uom", "UOM Name", "uom_name", "UOM", "yes"],
			["Uom", "Whole Number", "must_be_whole_number", "", "no"],
			["Brand", "Brand Name", "brand", "Brand", "yes"],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(len(result), 2)
		self.assertEqual(result["Uom"].doctype, "UOM")
		self.assertEqual(result["Uom"].key_field, "name")
		self.assertEqual(
			result["Uom"].column_map,
			{"UOM Name": "name", "Whole Number": "must_be_whole_number"},
		)
		self.assertIsNone(result["Uom"].child_doctype)
		self.assertEqual(result["Uom"].sheet_name, "Uom")
		self.assertEqual(result["Brand"].doctype, "Brand")
		self.assertEqual(result["Brand"].key_field, "name")
		self.assertEqual(result["Brand"].sheet_name, "Brand")

	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_throws_on_empty(self, mock_get_sheet: MagicMock) -> None:
		mock_get_sheet.return_value = []
		with self.assertRaises(ValidationError):
			parse_mappings("fake-id", "Mapping")

	@patch("connect_diagnostics_core.master_data.mapper._build_label_map", side_effect=_fake_label_map)
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_resolves_labels(
		self, mock_get_sheet: MagicMock, mock_label_map: MagicMock
	) -> None:
		mock_get_sheet.return_value = [
			["sheet_name", "sheet_column", "erpnext_field", "doctype", "is_key"],
			["Uom", "UOM Name", "ignored", "UOM", "yes"],
			["Uom", "Whole Number", "Must Be Whole Number", "", "no"],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(result["Uom"].key_field, "name")
		self.assertEqual(result["Uom"].column_map["Whole Number"], "must_be_whole_number")

	@patch("connect_diagnostics_core.master_data.mapper._build_label_map", side_effect=_fake_label_map)
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_child_entity(self, mock_get_sheet: MagicMock, mock_label_map: MagicMock) -> None:
		mock_get_sheet.return_value = [
			["sheet_name", "sheet_column", "erpnext_field", "doctype", "is_key", "parent_doctype"],
			["Product Bundle", "Parent Item Code", "ignored", "Product Bundle", "1", ""],
			["Product Bundle", "Item", "Item", "Product Bundle Item", "", "Product Bundle"],
			["Product Bundle", "Qty", "Qty", "Product Bundle Item", "", "Product Bundle"],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(result["Product Bundle"].doctype, "Product Bundle")
		self.assertEqual(result["Product Bundle"].key_field, "name")
		self.assertEqual(result["Product Bundle"].child_doctype, "Product Bundle Item")
		self.assertEqual(result["Product Bundle"].child_fields, {"item_code", "qty"})
		self.assertEqual(result["Product Bundle"].sheet_name, "Product Bundle")

	@patch("connect_diagnostics_core.master_data.mapper._build_label_map", side_effect=_fake_label_map)
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_without_parent_doctype_column(
		self, mock_get_sheet: MagicMock, mock_label_map: MagicMock
	) -> None:
		mock_get_sheet.return_value = [
			["sheet_name", "sheet_column", "erpnext_field", "doctype", "is_key"],
			["Uom", "UOM Name", "uom_name", "UOM", "yes"],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(result["Uom"].doctype, "UOM")
		self.assertIsNone(result["Uom"].child_doctype)

	@patch("connect_diagnostics_core.master_data.mapper._build_label_map", side_effect=_fake_label_map)
	@patch("connect_diagnostics_core.master_data.mapper.get_sheet_data")
	def test_parse_mappings_multi_doctype_per_sheet(
		self, mock_get_sheet: MagicMock, mock_label_map: MagicMock
	) -> None:
		mock_get_sheet.return_value = [
			["sheet_name", "sheet_column", "erpnext_field", "doctype", "is_key", "parent_doctype"],
			["Companies", "Company", "ignored", "Company", "1", ""],
			["Companies", "Abbr", "Abbr", "Company", "", ""],
			["Companies", "Tax ID", "Tax ID", "Company", "", ""],
			["Companies", "Address ID", "Address Title", "Address", "1", ""],
			["Companies", "Address Line 1", "Address Line 1", "Address", "", ""],
		]

		result = parse_mappings("fake-id", "Mapping")

		self.assertEqual(len(result), 2)
		self.assertIn("Companies:Company", result)
		self.assertIn("Companies:Address", result)

		company = result["Companies:Company"]
		self.assertEqual(company.doctype, "Company")
		self.assertEqual(company.key_field, "name")
		self.assertEqual(company.sheet_name, "Companies")
		self.assertEqual(company.column_map["Company"], "name")
		self.assertEqual(company.column_map["Abbr"], "abbr")

		address = result["Companies:Address"]
		self.assertEqual(address.doctype, "Address")
		self.assertEqual(address.key_field, "name")
		self.assertEqual(address.sheet_name, "Companies")
		self.assertEqual(address.column_map["Address ID"], "name")
		self.assertEqual(address.column_map["Address Line 1"], "address_line1")


class TestMapper(FrappeTestCase):
	def test_map_rows_produces_correct_dicts(self) -> None:
		mapping = {"UOM Name": "name", "Must Be Whole Number": "must_be_whole_number"}
		raw_data = [
			["UOM Name", "UOM Abbreviation", "Must Be Whole Number"],
			["Kilogram", "kg", "Yes"],
			["Meter", "m", "No"],
		]

		result = map_rows(raw_data, mapping, "name")

		self.assertEqual(len(result), 2)
		self.assertEqual(result[0], {"name": "Kilogram", "must_be_whole_number": "Yes"})
		self.assertEqual(result[1], {"name": "Meter", "must_be_whole_number": "No"})

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
			"Kilogram": {"name": "Kilogram", "must_be_whole_number": "No"},
		}
		expected = [{"name": "Kilogram", "must_be_whole_number": "No"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.matched, 1)
		self.assertEqual(len(result.mismatches), 0)

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_mismatch(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"Kilogram": {"name": "Kilogram", "must_be_whole_number": "No"},
		}
		expected = [{"name": "Kilogram", "must_be_whole_number": "Yes"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.matched, 0)
		self.assertEqual(len(result.mismatches), 1)
		self.assertEqual(result.mismatches[0].expected, "Yes")
		self.assertEqual(result.mismatches[0].actual, "No")

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_missing_in_db(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {}
		expected = [{"name": "Kilogram", "must_be_whole_number": "No"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.missing_in_db, ["Kilogram"])

	@patch("connect_diagnostics_core.master_data.comparator._fetch_actual_data")
	def test_compare_detects_missing_in_sheet(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"Kilogram": {"name": "Kilogram"},
			"Gram": {"name": "Gram"},
		}
		expected = [{"name": "Kilogram"}]

		result = compare_entity("Uom", _make_uom_mapping(), expected)

		self.assertEqual(result.missing_in_sheet, ["Gram"])


class TestChildComparator(FrappeTestCase):
	@patch("connect_diagnostics_core.master_data.comparator._fetch_child_data")
	def test_compare_child_detects_match(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"BUNDLE-001": [
				{"parent": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"},
				{"parent": "BUNDLE-001", "item_code": "ITEM-B", "qty": "2"},
			],
		}
		expected = [
			{"name": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"},
			{"name": "BUNDLE-001", "item_code": "ITEM-B", "qty": "2"},
		]

		result = compare_entity("Product Bundle", _make_bundle_mapping(), expected)

		self.assertEqual(result.matched, 2)
		self.assertEqual(len(result.mismatches), 0)

	@patch("connect_diagnostics_core.master_data.comparator._fetch_child_data")
	def test_compare_child_detects_mismatch(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"BUNDLE-001": [
				{"parent": "BUNDLE-001", "item_code": "ITEM-A", "qty": "5"},
			],
		}
		expected = [
			{"name": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"},
		]

		result = compare_entity("Product Bundle", _make_bundle_mapping(), expected)

		self.assertEqual(result.matched, 0)
		self.assertEqual(len(result.mismatches), 1)
		self.assertEqual(result.mismatches[0].expected, "1")
		self.assertEqual(result.mismatches[0].actual, "5")
		self.assertIn("BUNDLE-001", result.mismatches[0].key_value)

	@patch("connect_diagnostics_core.master_data.comparator._fetch_child_data")
	def test_compare_child_detects_missing_in_db(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {}
		expected = [
			{"name": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"},
		]

		result = compare_entity("Product Bundle", _make_bundle_mapping(), expected)

		self.assertEqual(result.missing_in_db, ["BUNDLE-001"])

	@patch("connect_diagnostics_core.master_data.comparator._fetch_child_data")
	def test_compare_child_detects_missing_in_sheet(self, mock_fetch: MagicMock) -> None:
		mock_fetch.return_value = {
			"BUNDLE-001": [{"parent": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"}],
			"BUNDLE-002": [{"parent": "BUNDLE-002", "item_code": "ITEM-B", "qty": "2"}],
		}
		expected = [
			{"name": "BUNDLE-001", "item_code": "ITEM-A", "qty": "1"},
		]

		result = compare_entity("Product Bundle", _make_bundle_mapping(), expected)

		self.assertEqual(result.missing_in_sheet, ["BUNDLE-002"])


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
