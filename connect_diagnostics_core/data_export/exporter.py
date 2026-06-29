# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Export every DocType to Excel, one workbook per module.

Each module workbook holds an ``_index`` sheet (DocType / Category / Sheet /
Records) followed by one sheet per DocType. The per-DocType sheets reuse Frappe's
own :class:`frappe.core.doctype.data_export.exporter.DataExporter` so the layout
(``DocType:`` / ``Column Labels:`` / ``Column Name:`` / ``Mandatory:`` / ``Type:``
/ ``Info:`` header block plus data rows) matches the standard Frappe export.
"""

from __future__ import annotations

import csv
import io
from io import BytesIO
from typing import cast

import frappe
from frappe.utils.xlsxutils import get_sanitized_sheet_name

INDEX_SHEET_NAME = "_index"
INDEX_HEADERS = ["DocType", "Category", "Sheet", "Records"]
MAX_SHEET_NAME_LENGTH = 31


def classify_doctype(*, issingle: bool, is_submittable: bool) -> str:
    """Categorize a DocType for the index sheet.

    Single DocTypes hold configuration, so they are ``Setup``; submittable
    DocTypes carry a docstatus workflow, so they are ``Transaction``; everything
    else is ``Master``.
    """
    if issingle:
        return "Setup"
    if is_submittable:
        return "Transaction"
    return "Master"


def list_target_doctypes(modules: tuple[str, ...] = ()) -> dict[str, list[dict[str, str]]]:
    """Group exportable DocTypes by module.

    Child tables are skipped because their columns are embedded in the parent
    sheet, and virtual DocTypes are skipped because they have no database table
    to export. Pass ``modules`` to limit the export to specific modules.
    """
    filters: dict[str, object] = {"istable": 0, "is_virtual": 0}
    if modules:
        filters["module"] = ["in", list(modules)]

    rows = frappe.get_all(
        "DocType",
        filters=filters,
        fields=["name", "module", "issingle", "is_submittable"],
        order_by="module asc, name asc",
    )

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        module = cast(str, row.get("module") or "Uncategorized")
        grouped.setdefault(module, []).append(
            {
                "name": cast(str, row["name"]),
                "category": classify_doctype(
                    issingle=bool(row.get("issingle")),
                    is_submittable=bool(row.get("is_submittable")),
                ),
            }
        )
    return grouped


def export_doctype_rows(doctype: str) -> list[list[str]]:
    """Return the Frappe Data Export rows (header block + data) for a DocType."""
    from frappe.core.doctype.data_export.exporter import DataExporter

    exporter = DataExporter(
        doctype=doctype,
        all_doctypes=True,
        with_data=True,
        file_type="CSV",
        template=False,
    )
    exporter.build_response()
    return list(csv.reader(io.StringIO(exporter.writer.getvalue())))


def _safe_count(doctype: str) -> int:
    """Return the record count for a DocType, or 0 if it cannot be counted."""
    try:
        return frappe.db.count(doctype)
    except Exception:
        return 0


def _unique_sheet_name(doctype: str, used: set[str]) -> str:
    """Return an Excel-safe, unique sheet name derived from ``doctype``."""
    base = get_sanitized_sheet_name(doctype) or "Sheet"
    candidate = base
    suffix = 1
    while candidate in used:
        suffix += 1
        tail = f" {suffix}"
        candidate = base[: MAX_SHEET_NAME_LENGTH - len(tail)] + tail
    used.add(candidate)
    return candidate


def build_module_workbook(doctypes: list[dict[str, str]]) -> bytes:
    """Build one xlsx (as bytes) with an ``_index`` sheet plus a sheet per DocType.

    A DocType that fails to export (for example a Single DocType with no backing
    table) is logged, listed in the index with an empty Sheet column, and skipped
    so one failure never aborts the whole workbook.
    """
    import xlsxwriter
    from frappe.utils.xlsxutils import make_xlsx

    used_names: set[str] = {INDEX_SHEET_NAME}
    index_rows: list[list[object]] = [list(INDEX_HEADERS)]
    sheets: list[tuple[str, list[list[str]]]] = []

    for entry in doctypes:
        doctype = entry["name"]
        try:
            rows = export_doctype_rows(doctype)
        except Exception:
            frappe.logger(__name__).warning(f"Data export skipped DocType {doctype!r}", exc_info=True)
            index_rows.append([doctype, entry["category"], None, 0])
            continue

        sheet_name = _unique_sheet_name(doctype, used_names)
        sheets.append((sheet_name, rows))
        index_rows.append([doctype, entry["category"], sheet_name, _safe_count(doctype)])

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"constant_memory": True})
    try:
        make_xlsx(index_rows, INDEX_SHEET_NAME, wb=workbook)
        for sheet_name, rows in sheets:
            make_xlsx(rows, sheet_name, wb=workbook)
    finally:
        workbook.close()
    return output.getvalue()
