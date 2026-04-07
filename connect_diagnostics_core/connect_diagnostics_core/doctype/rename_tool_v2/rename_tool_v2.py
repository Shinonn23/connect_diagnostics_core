# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import csv
from io import StringIO
from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe.model.rename_doc import (
	bulk_rename,  # pyright: ignore[reportUnknownVariableType, reportMissingImports]
)
from frappe.utils.deprecations import deprecated  # pyright: ignore[reportUnknownVariableType]


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


@frappe.whitelist()  # pyright: ignore[reportUnknownMemberType]
@deprecated  # pyright: ignore[reportUntypedFunctionDecorator]
def get_doctypes() -> list[str]:
	return cast(
		list[str],
		frappe.db.sql_list(  # pyright: ignore[reportUnknownMemberType]
			"""select name from tabDocType
		where allow_rename=1 and module!='Core' order by name"""
		),
	)


@frappe.whitelist()  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
def upload(select_doctype: str | None = None, file_url: str | None = None) -> None:

	if not select_doctype:
		select_doctype = cast(str, frappe.form_dict.select_doctype)
	if not file_url:
		file_url = cast(str, frappe.form_dict.file_url)

	if not frappe.has_permission(select_doctype, "write"):  # pyright: ignore[reportUnknownMemberType]
		raise frappe.PermissionError

	rows = read_csv_content_from_attached_file(file_url)  # pyright: ignore[reportUnknownMemberType]

	# bulk rename allows only 500 rows at a time, so we created one job per 500 rows
	for i in range(0, len(rows), 500):
		frappe.enqueue(  # pyright: ignore[reportUnknownMemberType]
			method=bulk_rename,
			queue="long",
			doctype=select_doctype,
			rows=rows[i : i + 500],
		)


def read_csv_content_from_attached_file(file_url: str) -> list[list[str]]:
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")  # pyright: ignore[reportUnknownMemberType]

	if not file_name:
		frappe.msgprint(frappe._("File not attached"))  # pyright: ignore[reportUnknownMemberType]
		raise Exception

	try:
		_file = frappe.get_doc("File", file_name)  # pyright: ignore[reportUnknownMemberType]
		content: Any = _file.get_content() or ""  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]

		if isinstance(content, bytes):
			try:
				decoded_content = content.decode("utf-8-sig")
			except UnicodeDecodeError:
				try:
					decoded_content = content.decode("cp1252")
				except UnicodeDecodeError:
					decoded_content = content.decode("utf-8", errors="replace")
		else:
			decoded_content = str(content)
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
		frappe.throw(  # pyright: ignore[reportUnknownMemberType]
			frappe._("Unable to open attached file. Did you export it as CSV?"),
			title=frappe._("Invalid CSV Format"),
		)
		return []
