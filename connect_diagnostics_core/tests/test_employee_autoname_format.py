from unittest.mock import patch

from frappe.exceptions import ValidationError
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.api.erpnext.employee import generate_thai_year_autoname
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
		doc = _FakeDoc({"custom_format": "C{YY}{MM}.{###}"})
		validate_employment_type_format(doc, "validate")  # type: ignore[arg-type]

	def test_accepts_legacy_pattern(self) -> None:
		doc = _FakeDoc({"custom_format": "YYYYMMDD.###"})
		validate_employment_type_format(doc, "validate")  # type: ignore[arg-type]

	def test_rejects_pattern_without_sequence(self) -> None:
		doc = _FakeDoc({"custom_format": "C{YY}{MM}"})
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")  # type: ignore[arg-type]

	def test_rejects_unknown_token(self) -> None:
		doc = _FakeDoc({"custom_format": "C{QQ}.{###}"})
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")  # type: ignore[arg-type]

	def test_blocks_format_change_after_creation(self) -> None:
		previous_doc = _FakeDoc({"custom_format": "C{YY}{MM}.{###}"})
		doc = _FakeDoc(
			{"custom_format": "C{YYYY}{MM}{DD}.{###}"},
			is_new=False,
			previous_doc=previous_doc,
		)
		with self.assertRaises(ValidationError):
			validate_employment_type_format(doc, "validate")  # type: ignore[arg-type]


class TestEmployeeAutonamePattern(FrappeTestCase):
	@patch("connect_diagnostics_core.api.erpnext.employee.make_autoname")
	@patch("connect_diagnostics_core.api.erpnext.employee.frappe.db.get_value")
	def test_generate_name_uses_brace_pattern_from_employment_type(
		self,
		mock_get_value,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
		mock_make_autoname,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
	) -> None:
		mock_get_value.return_value = "C{YY}{MM}.{###}"
		mock_make_autoname.return_value = "C6904.001"
		doc = _FakeEmployeeDoc(date_of_joining="2026-04-06", employment_type="Full-time")

		generate_thai_year_autoname(doc, "autoname")  # type: ignore[arg-type]

		mock_make_autoname.assert_called_once_with("C6904.###")  # pyright: ignore[reportUnknownMemberType]
		self.assertEqual(doc.name, "C6904.001")

	@patch("connect_diagnostics_core.api.erpnext.employee.make_autoname")
	@patch("connect_diagnostics_core.api.erpnext.employee.frappe.db.get_value")
	def test_generate_name_falls_back_to_legacy_pattern(self, mock_get_value, mock_make_autoname) -> None:  # type: ignore[no-untyped-def]
		mock_get_value.return_value = ""
		mock_make_autoname.return_value = "6904.001"
		doc = _FakeEmployeeDoc(date_of_joining="2026-04-06", employment_type="Full-time")

		generate_thai_year_autoname(doc, "autoname")  # type: ignore[arg-type]

		mock_make_autoname.assert_called_once_with("6904.###")  # pyright: ignore[reportUnknownMemberType]
		self.assertEqual(doc.name, "6904.001")
