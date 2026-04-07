# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import csv
from io import StringIO
from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe.model.rename_doc import (
	bulk_rename,
)


class RenameToolV2(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		file_to_rename: DF.Attach | None
		select_doctype: DF.Link | None
	# end: auto-generated types
	pass


@frappe.whitelist()
def get_doctypes() -> list[str]:
	return cast(
		list[str],
		frappe.db.sql_list(
			"""select name from tabDocType
		where allow_rename=1 and module!='Core' order by name"""
		),
	)


@frappe.whitelist()
def upload(select_doctype: str | None = None, file_url: str | None = None) -> None:
	if not select_doctype:
		select_doctype = cast(str, frappe.form_dict.select_doctype)
	if not file_url:
		file_url = cast(str, frappe.form_dict.file_url)

	if not frappe.has_permission(select_doctype, "write"):
		raise frappe.PermissionError

	rows = read_csv_content_from_attached_file(file_url)

	# bulk rename allows only 500 rows at a time, so we created one job per 500 rows
	for i in range(0, len(rows), 500):
		frappe.enqueue(
			method=bulk_rename,
			queue="long",
			doctype=select_doctype,
			rows=rows[i : i + 500],
		)


def read_csv_content_from_attached_file(file_url: str) -> list[list[str]]:
	from frappe.core.doctype.file.file import File as FrappeFile

	file_name = cast(str, frappe.db.get_value("File", {"file_url": file_url}, "name"))

	if not file_name:
		frappe.msgprint(frappe._("File not attached"))
		raise Exception

	try:
		_file = cast(FrappeFile, frappe.get_doc("File", file_name))
		content: Any = _file.get_content() or ""

		if isinstance(content, bytes):
			try:
				decoded_content = content.decode("utf-8-sig")
			except UnicodeDecodeError:
				try:
					decoded_content = content.decode("cp1252")
				except UnicodeDecodeError:
					decoded_content = content.decode("utf-8", errors="replace")
		else:
			decoded_content = str(content)  # pyright: ignore[reportUnknownArgumentType]
			# Remove BOM manually if Frappe already decoded it to string but kept the BOM
			if decoded_content.startswith("\ufeff"):
				decoded_content = decoded_content[1:]

		f = StringIO(decoded_content)
		reader = csv.reader(f)
		csv_rows: list[list[str]] = []

		for row in reader:
			stripped_row = [str(val).strip() for val in row if val is not None]  # pyright: ignore[reportUnnecessaryComparison]
			if any(stripped_row):
				csv_rows.append(stripped_row)

		return csv_rows
	except Exception:
		frappe.throw(
			frappe._("Unable to open attached file. Did you export it as CSV?"),
			title=frappe._("Invalid CSV Format"),
		)
		return []
