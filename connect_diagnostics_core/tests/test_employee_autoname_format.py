from typing import cast
from unittest.mock import MagicMock, patch

from erpnext.setup.doctype.employee.employee import Employee
from frappe.exceptions import ValidationError
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.api.erpnext.employee import autoname
from connect_diagnostics_core.api.erpnext.employment_type import validate_employment_type_format


class _FakeDoc:
	def __init__(
		self, values: dict[str, str], is_new: bool = True, previous_doc: "_FakeDoc | None" = None
	) -> None:
		self._values = values
		self._is_new = is_new
		self._previous_doc = previous_doc

	def get(self, key: str) -> str | None:
		return self._values.get(key)

	def is_new(self) -> bool:
		return self._is_new

	def get_doc_before_save(self) -> "_FakeDoc | None":
		return self._previous_doc


class _FakeEmployeeDoc:
	def __init__(self, date_of_joining: str, employment_type: str | None = None) -> None:
		self.date_of_joining = date_of_joining
		self._employment_type = employment_type
		self.name = ""

	def get(self, key: str) -> str | None:
		if key == "employment_type":
			return self._employment_type
		return None


class TestEmploymentTypeFormatValidation(FrappeTestCase):
	def test_accepts_brace_pattern(self) -> None:
		doc: Document = cast(Document, _FakeDoc({"custom_format": "C{YY}{MM}.{###}"}))
		validate_employment_type_format(doc, "validate")

	def test_accepts_legacy_pattern(self) -> None:
		doc: Document = cast(Document, _FakeDoc({"custom_format": "YYYYMMDD.###"}))
		validate_employment_type_format(doc, "validate")

	def test_rejects_pattern_without_sequence(self) -> None:
		doc: Document = cast(Document, _FakeDoc({"custom_format": "C{YY}{MM}"}))
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")

	def test_rejects_unknown_token(self) -> None:
		doc: Document = cast(Document, _FakeDoc({"custom_format": "C{QQ}.{###}"}))
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")

	def test_blocks_format_change_after_creation(self) -> None:
		previous_doc = _FakeDoc({"custom_format": "C{YY}{MM}.{###}"})
		doc: Document = cast(
			Document,
			_FakeDoc(
				{"custom_format": "C{YYYY}{MM}{DD}.{###}"},
				is_new=False,
				previous_doc=previous_doc,
			),
		)
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")


class TestEmployeeAutonamePattern(FrappeTestCase):
	@patch("connect_diagnostics_core.api.erpnext.employee.make_autoname")
	@patch("connect_diagnostics_core.api.erpnext.employee.frappe.db.get_value")
	def test_generate_name_uses_brace_pattern_from_employment_type(
		self,
		mock_get_value: MagicMock,
		mock_make_autoname: MagicMock,
	) -> None:
		mock_get_value.return_value = "C{YY}{MM}.{###}"
		mock_make_autoname.return_value = "C6904.001"
		doc = cast(Employee, _FakeEmployeeDoc(date_of_joining="2026-04-06", employment_type="Full-time"))

		autoname(doc, "autoname")

		mock_make_autoname.assert_called_once_with("C6904.###")
		self.assertEqual(doc.name, "C6904.001")

	@patch("connect_diagnostics_core.api.erpnext.employee.make_autoname")
	@patch("connect_diagnostics_core.api.erpnext.employee.frappe.db.get_value")
	def test_generate_name_falls_back_to_legacy_pattern(
		self, mock_get_value: MagicMock, mock_make_autoname: MagicMock
	) -> None:
		mock_get_value.return_value = ""
		mock_make_autoname.return_value = "6904.001"
		doc = cast(Employee, _FakeEmployeeDoc(date_of_joining="2026-04-06", employment_type="Full-time"))

		autoname(doc, "autoname")

		mock_make_autoname.assert_called_once_with("6904.###")
		self.assertEqual(doc.name, "6904.001")
