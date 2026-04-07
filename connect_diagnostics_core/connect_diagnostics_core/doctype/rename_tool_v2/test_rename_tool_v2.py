# Copyright (c) 2026, Siwat Sroisuwan and Contributors
# See license.txt

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from .rename_tool_v2 import (
	read_csv_content_from_attached_file,
	upload,
)


def _make_file_mock(content: bytes | str) -> MagicMock:
	"""Helper: returns a mock FrappeFile whose get_content() yields *content*."""
	mock_file = MagicMock()
	mock_file.get_content.return_value = content
	return mock_file


class TestReadCsvContentFromAttachedFile(FrappeTestCase):
	def _patch_get_doc(self, content: bytes | str):
		mock_file = _make_file_mock(content)
		return patch("frappe.get_doc", return_value=mock_file)

	def _patch_db(self, file_name: str = "FILE-0001"):
		return patch("frappe.db.get_value", return_value=file_name)

	def test_plain_utf8_bytes(self):
		csv_bytes = b"ACC-001,ACC-002\nACC-003,ACC-004\n"
		with self._patch_db(), self._patch_get_doc(csv_bytes):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		self.assertEqual(rows, [["ACC-001", "ACC-002"], ["ACC-003", "ACC-004"]])

	def test_utf8_bom_bytes(self):
		"""CSV exported from Excel often has a UTF-8 BOM prefix."""
		csv_bytes = b"\xef\xbb\xbfACC-001,ACC-002\nACC-003,ACC-004\n"
		with self._patch_db(), self._patch_get_doc(csv_bytes):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		# BOM must be stripped — first value must not start with \ufeff
		self.assertEqual(rows[0][0], "ACC-001")

	def test_string_content_with_bom(self):
		"""Frappe may decode bytes to str but keep the BOM character."""
		csv_str = "\ufeffACC-001,ACC-002\nACC-003,ACC-004\n"
		with self._patch_db(), self._patch_get_doc(csv_str):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		self.assertEqual(rows[0][0], "ACC-001")

	def test_cp1252_bytes(self):
		"""Thai/Windows environments sometimes produce CP-1252 files."""
		csv_bytes = "ACC-001,ACC-002\n".encode("cp1252")
		with self._patch_db(), self._patch_get_doc(csv_bytes):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		self.assertEqual(rows[0], ["ACC-001", "ACC-002"])

	def test_strips_whitespace(self):
		csv_bytes = b"  ACC-001  ,  ACC-002  \n"
		with self._patch_db(), self._patch_get_doc(csv_bytes):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		self.assertEqual(rows[0], ["ACC-001", "ACC-002"])

	def test_skips_blank_rows(self):
		csv_bytes = b"ACC-001,ACC-002\n\n\nACC-003,ACC-004\n"
		with self._patch_db(), self._patch_get_doc(csv_bytes):
			rows = read_csv_content_from_attached_file("/files/test.csv")
		self.assertEqual(len(rows), 2)

	def test_raises_when_file_not_found(self):
		with patch("frappe.db.get_value", return_value=None):
			with self.assertRaises(Exception):
				read_csv_content_from_attached_file("/files/missing.csv")

	def test_raises_on_invalid_content(self):
		"""get_content() blowing up should re-raise via frappe.throw."""
		mock_file = MagicMock()
		mock_file.get_content.side_effect = Exception("disk error")
		with self._patch_db(), patch("frappe.get_doc", return_value=mock_file):
			with self.assertRaises(Exception):
				read_csv_content_from_attached_file("/files/bad.csv")


class TestUpload(FrappeTestCase):
	def _csv_rows(self) -> list[list[str]]:
		return [[f"OLD-{i:03d}", f"NEW-{i:03d}"] for i in range(5)]

	def test_enqueues_single_job_for_small_file(self):
		rows = self._csv_rows()  # 5 rows → 1 job
		with (
			patch(
				"connect_diagnostics_core.connect_diagnostics_core.doctype.rename_tool_v2.rename_tool_v2.read_csv_content_from_attached_file",
				return_value=rows,
			),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.enqueue") as mock_enqueue,
		):
			upload(select_doctype="Account", file_url="/files/rename.csv")
			self.assertEqual(mock_enqueue.call_count, 1)

	def test_enqueues_multiple_jobs_for_large_file(self):
		rows = [[f"OLD-{i}", f"NEW-{i}"] for i in range(1100)]  # → 3 jobs (500/500/100)
		with (
			patch(
				"connect_diagnostics_core.connect_diagnostics_core.doctype.rename_tool_v2.rename_tool_v2.read_csv_content_from_attached_file",
				return_value=rows,
			),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.enqueue") as mock_enqueue,
		):
			upload(select_doctype="Account", file_url="/files/big.csv")
			self.assertEqual(mock_enqueue.call_count, 3)

	def test_raises_on_missing_permission(self):
		with (
			patch("frappe.has_permission", return_value=False),
			self.assertRaises(frappe.PermissionError),
		):
			upload(select_doctype="Account", file_url="/files/rename.csv")


class TestRenameToolV2(FrappeTestCase):
	"""Doctype-level smoke test — just verifies the doc can be instantiated."""

	def test_doctype_exists(self):
		from frappe.model.meta import Meta

		meta = cast(Meta, frappe.get_meta("Rename Tool V2"))
		self.assertIsNotNone(meta)

	def test_required_fields_present(self):
		from frappe.model.meta import Meta

		meta: Meta = cast(Meta, frappe.get_meta("Rename Tool V2"))
		self.assertTrue(meta.has_field("select_doctype"))
		self.assertTrue(meta.has_field("file_to_rename"))
